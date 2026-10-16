import asyncio
import json
import logging
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from eth_utils import event_abi_to_log_topic
from hexbytes import HexBytes
import httpx
from web3 import AsyncHTTPProvider, AsyncWeb3
from web3.contract import AsyncContract
from app.configs import settings
from app.databases.indexer_state import IndexerStateDatabases

logger = logging.getLogger("web3_indexer")
logger.setLevel(logging.INFO)

if not logger.handlers:
    _handler = logging.StreamHandler()
    _formatter = logging.Formatter(
        "[%(asctime)s] [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    _handler.setFormatter(_formatter)
    logger.addHandler(_handler)

IGNORED_EVENTS = {
    "Approval",
    "ApprovalForAll",
    "BatchMetadataUpdate",
    "MetadataUpdate",
    "OwnershipTransferred",
    "OwnerUpdated",
    "Transfer",
}


def _ensure_0x_hash(val: Any) -> str:
    """Pastikan hash hex diawali '0x' (lowercase).

    Handle bytes, HexBytes, dan str. Jika sudah ada prefix 0x, normalisasi ke lowercase.
    Jika belum, tambahkan '0x'. Untuk string kosong / None kembalikan apa adanya.
    Digunakan untuk filter semua hash yang dihasilkan handler (tx_hash, signature, dll).
    """
    if val is None:
        return ""
    if isinstance(val, (bytes, HexBytes)):
        # HexBytes.to_0x_hex() sudah include 0x, bytes.hex() tidak
        if isinstance(val, HexBytes):
            try:
                return val.to_0x_hex().lower()
            except Exception:
                h = val.hex()
                return (
                    ("0x" + h).lower() if not h.lower().startswith("0x") else h.lower()
                )
        h = val.hex()
        return ("0x" + h).lower() if not h.lower().startswith("0x") else h.lower()
    s = str(val).strip()
    if not s:
        return s
    if s.lower().startswith("0x"):
        return s.lower()
    return "0x" + s.lower()


def _clean_args(args: Any) -> Any:
    if isinstance(args, (bytes, HexBytes)):
        return _ensure_0x_hash(args)
    elif isinstance(args, (dict, Mapping)):
        return {str(k): _clean_args(v) for k, v in args.items()}
    elif isinstance(args, (list, tuple, set)):
        return [_clean_args(x) for x in args]
    return args


ZERO_ADDRESS = "0x0000000000000000000000000000000000000000"


def _normalize_address(val: Any) -> Optional[str]:
    """Kembalikan None jika alamat kosong atau zero address (default Solidity)."""
    if val is None:
        return None
    addr = str(val).strip()
    if not addr or addr.lower() == ZERO_ADDRESS:
        return None
    return addr


def _parse_timestamp(val: Any) -> datetime:
    if isinstance(val, (int, float)):
        return datetime.fromtimestamp(val, tz=timezone.utc)
    elif isinstance(val, str) and val.isdigit():
        return datetime.fromtimestamp(int(val), tz=timezone.utc)
    elif isinstance(val, datetime):
        if val.tzinfo is None:
            return val.replace(tzinfo=timezone.utc)
        return val
    return datetime.now(timezone.utc)


class Web3Indexer:
    def __init__(self):
        self.w3 = AsyncWeb3(AsyncHTTPProvider(settings.web3_rpc_url))
        self.is_running = False
        self._task: Optional[asyncio.Task] = None
        self.contract_configs: List[Dict[str, Any]] = []
        self.last_scanned_blocks: Dict[str, int] = {}
        self.last_updated_at: Dict[str, str] = {}
        self._ipfs_cache: Dict[str, Dict[str, Any]] = {}

    async def _resolve_indexer_state_id(self) -> str:
        """Resolve chain_id via indexer_state.id (proper FK).

        Semua child table (competition, listing_token, dst) tidak lagi
        menyimpan `chain_id` mentah. Chain di-query via relasi
        `indexer_state.id` -> `indexer_state.chain_id`.
        Helper ini fetch/create baris `indexer_state` untuk
        (contract_name="CompetitionManager", chain_id=settings.chain_id)
        dan kembalikan PK `id` (ULID) untuk dipakai sebagai FK
        `indexer_state_id` saat insert.
        """
        from app.databases.indexer_state import IndexerStateDatabases

        return await IndexerStateDatabases.get_or_create_indexer_state_id(
            contract_name="CompetitionManager",
            chain_id=settings.chain_id,
        )

    async def _fetch_from_ipfs(self, cid: str) -> Dict[str, Any]:
        if not cid or not isinstance(cid, str):
            return {}
        cid = cid.strip()
        if cid.startswith("ipfs://"):
            cid = cid[7:]
        if not cid:
            return {}

        if cid in self._ipfs_cache:
            return self._ipfs_cache[cid]

        candidates = []
        raw_api = settings.kubo_api_url or "http://localhost:5001"
        base_api = raw_api.split("/api/v0")[0].rstrip("/")
        candidates.append(("POST", f"{base_api}/api/v0/cat?arg={cid}"))

        if "kubo" in base_api:
            candidates.append(("POST", f"http://localhost:5001/api/v0/cat?arg={cid}"))

        gw_url = (settings.kubo_gateway_url or "http://localhost:8082").rstrip("/")
        candidates.append(("GET", f"{gw_url}/ipfs/{cid}"))
        if "localhost" not in gw_url:
            candidates.append(("GET", f"http://localhost:8082/ipfs/{cid}"))

        unique_candidates = []
        seen = set()
        for method, url in candidates:
            if url not in seen:
                seen.add(url)
                unique_candidates.append((method, url))

        last_error = None
        async with httpx.AsyncClient() as client:
            for method, url in unique_candidates:
                try:
                    if method == "POST":
                        res = await client.post(url, timeout=5.0)
                    else:
                        res = await client.get(url, timeout=5.0)
                    if res.status_code == 200:
                        try:
                            data = res.json()
                            if isinstance(data, dict):
                                self._ipfs_cache[cid] = data
                                return data
                            return {}
                        except Exception as parse_err:
                            logger.debug(
                                f"IPFS CID {cid} response from {url} is not JSON: {parse_err}"
                            )
                            return {}
                except Exception as e:
                    last_error = e

        logger.warning(
            f"Failed to fetch IPFS CID {cid} from configured endpoint and fallbacks: {last_error}"
        )
        self._ipfs_cache[cid] = {}
        return {}

    def _load_abi(self, filename: str) -> List[Dict[str, Any]]:
        abi_path = Path(__file__).parent.parent / "abi" / filename
        if not abi_path.exists():
            logger.warning(f"ABI file {filename} does not exist at {abi_path}.")
            return []
        with open(abi_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def _setup_contracts(self):
        mapping = [
            (
                "CompetitionManager",
                settings.competition_contract
                or settings.certificate_competition_contract,
                "CompetitionManager.json",
            ),
        ]

        self.contract_configs = []
        for name, address, abi_file in mapping:
            if not address or not address.strip():
                logger.warning(f"Contract {name} has no address configured, skipping.")
                continue
            try:
                checksum_addr = AsyncWeb3.to_checksum_address(address.strip())
                abi = self._load_abi(abi_file)
                if not abi:
                    logger.warning(
                        f"ABI for contract {name} ({abi_file}) is empty or missing, skipping."
                    )
                    continue
                contract = self.w3.eth.contract(address=checksum_addr, abi=abi)

                topic_map = {}
                for item in abi:
                    if item.get("type") == "event":
                        event_name = item["name"]
                        if event_name in IGNORED_EVENTS:
                            continue
                        topic0 = event_abi_to_log_topic(item).hex()
                        topic_map[topic0] = event_name

                self.contract_configs.append(
                    {
                        "name": name,
                        "address": checksum_addr,
                        "contract": contract,
                        "topic_map": topic_map,
                    }
                )
            except Exception as e:
                logger.error(
                    f"Failed to setup contract {name} at address {address}: {e}"
                )

    async def start(self):
        if self.is_running:
            return
        self.is_running = True
        self._setup_contracts()
        self._task = asyncio.create_task(self._run_loop())
        logger.info("Web3 Indexer service started.")

    async def stop(self):
        if not self.is_running:
            return
        self.is_running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("Web3 Indexer service stopped.")

    async def _run_loop(self):
        while self.is_running:
            try:
                connected = await self.w3.is_connected()
                if not connected:
                    logger.warning(
                        f"RPC not connected to {settings.web3_rpc_url}. Retrying..."
                    )
                    await asyncio.sleep(settings.web3_poll_interval)
                    continue

                latest_block = await self.w3.eth.block_number
                for cfg in self.contract_configs:
                    await self._index_contract(cfg, latest_block)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in indexer loop: {e}", exc_info=True)

            await asyncio.sleep(settings.web3_poll_interval)

    async def _index_contract(self, cfg: Dict[str, Any], latest_block: int):
        name = cfg["name"]
        address = cfg["address"]

        if name not in self.last_scanned_blocks:
            db_block = await IndexerStateDatabases.get_last_scanned_block(
                name, chain_id=settings.chain_id
            )
            if db_block is not None:
                self.last_scanned_blocks[name] = db_block
                logger.info(
                    f"Restored last_scanned_block for {name} from DB: {db_block}"
                )
            elif settings.web3_start_block is not None:
                from_block = settings.web3_start_block
                self.last_scanned_blocks[name] = max(0, from_block - 1)
            else:
                from_block = max(0, latest_block - 100)
                self.last_scanned_blocks[name] = max(0, from_block - 1)

        from_block = self.last_scanned_blocks[name] + 1
        if from_block > latest_block:
            return

        batch_size = 1000
        to_block = min(latest_block, from_block + batch_size - 1)

        try:
            logs = await self.w3.eth.get_logs(
                {
                    "address": address,
                    "fromBlock": from_block,
                    "toBlock": to_block,
                }
            )

            for log in logs:
                await self._process_log(cfg, log)

            self.last_scanned_blocks[name] = to_block
            self.last_updated_at[name] = datetime.now(timezone.utc).isoformat()
            await IndexerStateDatabases.set_last_scanned_block(
                name, to_block, chain_id=settings.chain_id
            )

        except Exception as e:
            logger.error(
                f"Error indexing {name} from block {from_block} to {to_block}: {e}"
            )

    async def _process_log(self, cfg: Dict[str, Any], log: Any):
        name = cfg["name"]
        address = cfg["address"]
        contract: AsyncContract = cfg["contract"]
        topic_map = cfg["topic_map"]

        topics = log.get("topics", [])
        if not topics:
            return

        topic0 = HexBytes(topics[0]).hex()
        event_name = topic_map.get(topic0)
        if not event_name or event_name in IGNORED_EVENTS:
            return

        tx_hash = _ensure_0x_hash(log["transactionHash"])
        log_index = int(log["logIndex"])
        block_number = int(log["blockNumber"])

        try:
            event_obj = getattr(contract.events, event_name)().process_log(log)
            raw_args = dict(event_obj.args)
            cleaned_args = _clean_args(raw_args)

            print("\n" + "=" * 60)
            print("🎉 WEB3 EVENT DETECTED!")
            print(f"  Contract:  {name} ({address})")
            print(f"  Event:     {event_name}")
            print(f"  Block:     {block_number}")
            print(f"  Tx Hash:   {tx_hash}")
            print(f"  Log Index: {log_index}")
            print(f"  Args:      {json.dumps(cleaned_args, indent=4)}")
            print("=" * 60)

            await self._print_event_details(event_name, cleaned_args, tx_hash)

            if event_name in (
                "CompetitionCreated",
                "CompetitionPaymentConfigured",
                "CompetitionWinnerConfigured",
            ):
                await self._handle_competition_event(event_name, tx_hash, cleaned_args)
            elif event_name == "CompetitionFeePaid":
                await self._handle_competition_fee_paid(tx_hash, cleaned_args)
            elif event_name == "WinnerSet":
                await self._handle_winner_set(tx_hash, cleaned_args)
            elif event_name in (
                "ListingTokenAdded",
                "ListingTokenDeactivated",
            ):
                await self._handle_listing_token_added(tx_hash, cleaned_args)
            elif event_name == "PrizeDeposited":
                await self._handle_prize_deposited(tx_hash, cleaned_args)
            elif event_name == "PrizeDistributed":
                await self._handle_prize_distributed(tx_hash, cleaned_args)
            elif event_name in (
                "PriceCompetitionFeeSet",
                "PriceCompetitionFeeUpdated",
            ):
                await self._handle_price_competition_fee_set(tx_hash, cleaned_args)
            elif event_name == "CertificateParticipantMinted":
                await self._handle_certificate_participant_minted(tx_hash, cleaned_args)
            elif event_name == "CertificateParticipantWinnerMinted":
                await self._handle_certificate_participant_winner_minted(
                    tx_hash, cleaned_args
                )
            elif event_name == "TeamPaymentCreated":
                await self._handle_team_payment_created(tx_hash, cleaned_args)

        except Exception as e:
            logger.error(f"Error processing log {tx_hash}:{log_index}: {e}")

    async def _handle_listing_token_added(self, tx_hash: str, args: Dict[str, Any]):
        try:
            from app.databases.listing_token import ListingTokenDatabases

            listing_token_id = int(args.get("listingTokenId") or 0)
            token_address = str(args.get("tokenAddress") or "")
            is_active = bool(args.get("isActive", True))

            indexer_state_id = await self._resolve_indexer_state_id()
            saved = await ListingTokenDatabases.add_listing_token(
                tx_hash=tx_hash,
                listing_token_id=listing_token_id,
                token_address=token_address,
                is_active=is_active,
                indexer_state_id=indexer_state_id,
            )
            logger.info(
                f"Successfully saved ListingToken to DB with ULID: {saved.id} (listing_token_id: {listing_token_id})"
            )
        except Exception as e:
            logger.error(f"Failed to save ListingToken event to DB: {e}")

    async def _handle_prize_deposited(self, tx_hash: str, args: Dict[str, Any]):
        try:
            from app.databases.prize_deposited import PrizeDepositedDatabases

            treasury_prize_id = int(args.get("treasuryPrizeId") or 0)
            competition_id = str(args.get("competitionId") or "")
            token_address = str(args.get("tokenAddress") or "")
            sender = str(args.get("sender") or "")
            amount = int(args.get("amount") or 0)

            indexer_state_id = await self._resolve_indexer_state_id()
            saved = await PrizeDepositedDatabases.add_prize_deposited(
                tx_hash=tx_hash,
                treasury_prize_id=treasury_prize_id,
                competition_id=competition_id,
                token_address=token_address,
                sender=sender,
                amount=amount,
                indexer_state_id=indexer_state_id,
            )
            logger.info(
                f"Successfully saved PrizeDeposited to DB with ULID: {saved.id} (treasury_prize_id: {treasury_prize_id})"
            )
        except Exception as e:
            logger.error(f"Failed to save PrizeDeposited event to DB: {e}")

    async def _handle_prize_distributed(self, tx_hash: str, args: Dict[str, Any]):
        try:
            from app.databases.prize_distributed import (
                PrizeDistributedDatabases,
            )

            treasury_prize_id = int(args.get("treasuryPrizeId") or 0)
            competition_id = str(args.get("competitionId") or "")
            token_address = str(args.get("tokenAddress") or "")
            recipient = str(args.get("recipient") or "")
            amount = int(args.get("amount") or 0)

            indexer_state_id = await self._resolve_indexer_state_id()
            saved = await PrizeDistributedDatabases.add_prize_distributed(
                tx_hash=tx_hash,
                treasury_prize_id=treasury_prize_id,
                competition_id=competition_id,
                token_address=token_address,
                recipient=recipient,
                amount=amount,
                indexer_state_id=indexer_state_id,
            )
            logger.info(
                f"Successfully saved PrizeDistributed to DB with ULID: {saved.id} (treasury_prize_id: {treasury_prize_id})"
            )
        except Exception as e:
            logger.error(f"Failed to save PrizeDistributed event to DB: {e}")

    async def _handle_price_competition_fee_set(
        self, tx_hash: str, args: Dict[str, Any]
    ):
        try:
            from app.databases.price_competition import PriceCompetitionDatabases

            price_competition_fee_id = int(args.get("id") or 0)
            treasury_fee = int(args.get("treasuryFee") or 0)
            token_address = str(args.get("tokenAddress") or "")
            cid = str(args.get("cid") or "")

            title = cid
            description = cid

            if cid:
                fee_meta = await self._fetch_from_ipfs(cid)
                if isinstance(fee_meta, dict):
                    title = str(fee_meta.get("name") or fee_meta.get("title") or title)
                    description = str(fee_meta.get("description") or description)

            indexer_state_id = await self._resolve_indexer_state_id()
            saved = await PriceCompetitionDatabases.add_price_competition(
                tx_hash=tx_hash,
                price_competition_fee_id=price_competition_fee_id,
                treasury_fee=treasury_fee,
                token_address=token_address,
                title=title,
                description=description,
                indexer_state_id=indexer_state_id,
            )
            logger.info(
                f"Successfully saved PriceCompetition to DB with ULID: {saved.id} (price_competition_fee_id: {price_competition_fee_id})"
            )
        except Exception as e:
            logger.error(f"Failed to save PriceCompetitionFeeSet event to DB: {e}")

    async def _handle_competition_fee_paid(self, tx_hash: str, args: Dict[str, Any]):
        try:
            from app.databases.competition_fee_paid import (
                CompetitionFeePaidDatabases,
            )

            competition_id = str(args.get("competitionId") or "")
            payer = str(args.get("payer") or "")
            token_address = str(args.get("tokenAddress") or "")
            amount = int(args.get("amount") or 0)

            indexer_state_id = await self._resolve_indexer_state_id()
            saved = await CompetitionFeePaidDatabases.add_competition_fee_paid(
                tx_hash=tx_hash,
                competition_id=competition_id,
                payer=payer,
                token_address=token_address,
                amount=amount,
                indexer_state_id=indexer_state_id,
            )
            logger.info(
                f"Successfully saved CompetitionFeePaid to DB with ULID: {saved.id} (event competition_id: {competition_id})"
            )
        except Exception as e:
            logger.error(f"Failed to save CompetitionFeePaid event to DB: {e}")

    async def _handle_winner_set(self, tx_hash: str, args: Dict[str, Any]):
        try:
            from app.databases.participant_winner import ParticipantWinnerDatabases
            from app.configs.database import AsyncSessionLocal
            from sqlmodel import select
            from app.models.prize_winner import PrizeWinnerModel
            from app.databases.competition import CompetitionDatabases

            winner_id = int(args.get("winnerId") or 0)
            participant = str(args.get("participant") or "")
            competition_id = str(args.get("competitionId") or "")

            title = ""
            # prize_winner_id is BigInt FK -> prize_winner.winner_id (global @unique)
            # No separate winner_id column on participant_winner; winner_id == prize_winner_id
            prize_winner_id: int | None = winner_id if winner_id else None
            indexer_state_id = await self._resolve_indexer_state_id()

            try:
                async with AsyncSessionLocal() as db:
                    comp = await CompetitionDatabases.ensure_competition_exists(
                        db,
                        competition_id,
                        tx_hash,
                        indexer_state_id=indexer_state_id,
                    )
                    # winner_id is globally UNIQUE on prize_winner, so lookup by winner_id only
                    stmt = select(PrizeWinnerModel).where(
                        PrizeWinnerModel.winner_id == winner_id,
                    )
                    res = await db.exec(stmt)
                    _first = res.first()
                    prize_winner = (
                        _first[0] if isinstance(_first, (tuple, list)) else _first
                    )
                    if prize_winner:
                        if getattr(prize_winner, "category", None):
                            title = str(prize_winner.category)
                        # keep prize_winner_id as winner_id (BigInt) — FK to prize_winner.winner_id
                        try:
                            prize_winner_id = int(
                                getattr(prize_winner, "winner_id", winner_id)
                            )
                        except Exception:
                            prize_winner_id = winner_id
            except Exception as db_e:
                logger.warning(
                    f"Failed to query PrizeWinner category for title: {db_e}"
                )

            if not title:
                title = f"Winner #{winner_id}"

            saved = await ParticipantWinnerDatabases.add_participant_winner(
                tx_hash=tx_hash,
                participant=participant,
                competition_id=competition_id,
                title=title,
                prize_winner_id=prize_winner_id,
                indexer_state_id=indexer_state_id,
            )
            logger.info(
                f"Successfully saved ParticipantWinner to DB with ULID: {saved.id} (prize_winner_id(BigInt FK->prize_winner.winner_id): {prize_winner_id})"
            )
        except Exception as e:
            logger.error(f"Failed to save WinnerSet event to DB: {e}")

    async def _handle_certificate_participant_minted(
        self, tx_hash: str, args: Dict[str, Any]
    ):
        try:
            from app.databases.certificate_participant_minted import (
                CertificateParticipantMintedDatabases,
            )

            token_id = int(args.get("tokenId") or 0)
            participant = str(args.get("participant") or "")
            competition_id = str(args.get("competitionId") or "")
            uri = str(args.get("uri") or "")

            # ── Resolve team_id via IPFS uri (ipfs://<CID>) ──────────────────
            # URI example: ipfs://QmZhYcERutv3RBU57x2s1CgkHESpL6McmzZc6aWWZXyA2q
            # CID extracted -> fetch via Kubo (_fetch_from_ipfs) -> JSON must contain team_id
            # team_id from IPFS is ULID of team table, used as FK for certificate_participant_minted.team_id
            # ── Resolve team_id: Prioritaskan on-chain args.get("teamId") (ULID dari smart contract) ──
            onchain_team_id_arg = args.get("teamId")
            onchain_team_id: Optional[str] = (
                str(onchain_team_id_arg).strip()
                if onchain_team_id_arg is not None
                and str(onchain_team_id_arg).strip() != ""
                else None
            )

            # Fallback jika on-chain teamId kosong: resolve via IPFS uri (ipfs://<CID>)
            ipfs_team_id: Optional[str] = None
            if not onchain_team_id and uri:
                cid_raw = uri.strip()
                if cid_raw.startswith("ipfs://"):
                    cid_raw = cid_raw[7:]
                cid_raw = cid_raw.split("/")[0].split("?")[0].strip()
                if cid_raw:
                    try:
                        ipfs_data = await self._fetch_from_ipfs(cid_raw)
                        if isinstance(ipfs_data, dict) and ipfs_data:
                            candidate = (
                                ipfs_data.get("team_id")
                                or ipfs_data.get("teamId")
                                or ipfs_data.get("teamID")
                                or ipfs_data.get("team")
                            )
                            if candidate is None and isinstance(
                                ipfs_data.get("data"), dict
                            ):
                                candidate = (
                                    ipfs_data["data"].get("team_id")
                                    or ipfs_data["data"].get("teamId")
                                    or ipfs_data["data"].get("team")
                                )

                            # Jika candidate bertipe dict (misal {id: "...", name: "..."}), ekstrak ID-nya
                            if isinstance(candidate, dict):
                                candidate = (
                                    candidate.get("id")
                                    or candidate.get("team_id")
                                    or candidate.get("teamId")
                                )

                            if candidate is not None and str(candidate).strip():
                                ipfs_team_id = str(candidate).strip()
                                logger.info(
                                    f"Resolved team_id={ipfs_team_id} from IPFS uri={uri} (CID={cid_raw}) for CertificateParticipantMinted token_id={token_id}"
                                )
                    except Exception as e:
                        logger.warning(
                            f"Failed to fetch team_id from IPFS CID {cid_raw} (uri={uri}): {e}",
                            exc_info=True,
                        )

            raw_team_id: Optional[str] = onchain_team_id or ipfs_team_id
            team_id_int: Optional[int] = None
            if raw_team_id and raw_team_id.isdigit():
                try:
                    team_id_int = int(raw_team_id)
                except Exception:
                    team_id_int = None

            indexer_state_id = await self._resolve_indexer_state_id()
            saved = await CertificateParticipantMintedDatabases.add_certificate_participant_minted(
                tx_hash=tx_hash,
                token_id=token_id,
                participant=participant,
                competition_id=competition_id,
                uri=uri,
                team_id=team_id_int,
                raw_team_id=raw_team_id,
                indexer_state_id=indexer_state_id,
            )
            logger.info(
                f"Successfully saved CertificateParticipantMinted to DB with ULID: {saved.id} (token_id: {token_id}, competition_id: {competition_id})"
            )

            # Hapus signature single-use setelah mint sukses (user_id + signature)
            try:
                raw_sig = args.get("signature")
                if isinstance(raw_sig, (bytes, HexBytes)):
                    sig_str = raw_sig.hex()
                elif raw_sig is None:
                    sig_str = ""
                else:
                    sig_str = str(raw_sig).strip()

                if sig_str:
                    sig_norm = sig_str.lower().strip()
                    if not sig_norm.startswith("0x"):
                        sig_norm = "0x" + sig_norm
                    sig_no0x = sig_norm[2:]

                    user_id = getattr(saved, "user_id", None)
                    # fallback resolve user_id via participant wallet bila saved.user_id None
                    if not user_id and participant:
                        try:
                            from sqlmodel import select as _select_fallback
                            from sqlalchemy import func as _func_fallback
                            from app.configs.database import (
                                AsyncSessionLocal as _AsyncSessionLocalFallback,
                            )
                            from app.models.user import UserModel as _UserModelFallback

                            async with _AsyncSessionLocalFallback() as _db_fb:
                                _stmt_fb = _select_fallback(_UserModelFallback).where(
                                    _func_fallback.lower(
                                        _UserModelFallback.wallet_address
                                    )
                                    == participant.lower()
                                )
                                _res_fb = await _db_fb.exec(_stmt_fb)
                                _first = _res_fb.first()
                                _user_fb = (
                                    _first[0]
                                    if isinstance(_first, (tuple, list))
                                    else _first
                                )
                                if _user_fb is not None:
                                    user_id = getattr(_user_fb, "id", None)
                        except Exception as _fb_e:
                            logger.debug(
                                f"Fallback user_id resolve failed for {participant}: {_fb_e}"
                            )

                    if user_id and sig_norm:
                        from sqlalchemy import (
                            delete as _delete,
                            func as _func2,
                            or_ as _or,
                        )
                        from app.configs.database import (
                            AsyncSessionLocal as _AsyncSessionLocal2,
                        )
                        from app.models.signature_certificate_participant import (
                            SignatureCertificateParticipantModel,
                        )

                        async with _AsyncSessionLocal2() as _db2:
                            # hard delete via WHERE user_id + (signature with/without 0x, case-insensitive)
                            _del = _delete(SignatureCertificateParticipantModel).where(
                                SignatureCertificateParticipantModel.user_id == user_id,
                                _or(
                                    _func2.lower(
                                        SignatureCertificateParticipantModel.signature
                                    )
                                    == sig_norm,
                                    _func2.lower(
                                        SignatureCertificateParticipantModel.signature
                                    )
                                    == sig_no0x,
                                ),
                            )
                            _result = await _db2.exec(_del)
                            await _db2.commit()
                            try:
                                _count = getattr(_result, "rowcount", 0) or 0
                            except Exception:
                                _count = 0
                            if _count:
                                logger.info(
                                    f"Deleted { _count} signature_certificate_participant row(s) for user_id={user_id} sig={sig_norm[:10]}... after CertificateParticipantMinted token_id={token_id}"
                                )
                            else:
                                # fallback: coba select+delete manual (untuk sqlite/edge)
                                from sqlmodel import select as _select2

                                _stmt2 = _select2(
                                    SignatureCertificateParticipantModel
                                ).where(
                                    SignatureCertificateParticipantModel.user_id
                                    == user_id,
                                    _or(
                                        _func2.lower(
                                            SignatureCertificateParticipantModel.signature
                                        )
                                        == sig_norm,
                                        _func2.lower(
                                            SignatureCertificateParticipantModel.signature
                                        )
                                        == sig_no0x,
                                    ),
                                )
                                _res2 = await _db2.exec(_stmt2)
                                _rows = _res2.all()
                                if _rows:
                                    for _row in _rows:
                                        _obj = (
                                            _row[0]
                                            if isinstance(_row, (tuple, list))
                                            else _row
                                        )
                                        await _db2.delete(_obj)
                                    await _db2.commit()
                                    logger.info(
                                        f"Deleted {len(_rows)} signature_certificate_participant row(s) (fallback) for user_id={user_id} sig={sig_norm[:10]}... token_id={token_id}"
                                    )
                                else:
                                    logger.debug(
                                        f"No matching signature_certificate_participant found to delete for user_id={user_id} sig={sig_norm[:10]}... (token_id={token_id})"
                                    )
                    else:
                        logger.debug(
                            f"Skip signature cleanup: user_id={user_id} sig_present={bool(sig_str)} token_id={token_id}"
                        )
                else:
                    logger.debug(
                        f"No signature in CertificateParticipantMinted args, skip cleanup (token_id={token_id})"
                    )
            except Exception as _e:
                logger.warning(
                    f"Failed to delete signature_certificate_participant after mint (token_id={token_id}): {_e}"
                )
        except Exception as e:
            logger.error(
                f"Failed to save CertificateParticipantMinted event to DB: {e}"
            )

    async def _handle_certificate_participant_winner_minted(
        self, tx_hash: str, args: Dict[str, Any]
    ):
        try:
            from app.databases.certificate_participant_winner_minted import (
                CertificateParticipantWinnerMintedDatabases,
            )

            token_id = int(args.get("tokenId") or 0)
            participant = str(args.get("participant") or "")
            competition_id = str(args.get("competitionId") or "")
            winner_id = int(args.get("winnerId") or 0)
            uri = str(args.get("uri") or "")
            raw_team_id_w = args.get("teamId")
            team_id_int_w = None
            try:
                if raw_team_id_w is not None and str(raw_team_id_w).strip() != "":
                    team_id_int_w = int(str(raw_team_id_w).strip())
            except Exception:
                team_id_int_w = None

            indexer_state_id = await self._resolve_indexer_state_id()
            saved = await CertificateParticipantWinnerMintedDatabases.add_certificate_participant_winner_minted(
                tx_hash=tx_hash,
                token_id=token_id,
                participant=participant,
                competition_id=competition_id,
                winner_id=winner_id,
                uri=uri,
                team_id=team_id_int_w,
                raw_team_id=str(raw_team_id_w) if raw_team_id_w is not None else None,
                indexer_state_id=indexer_state_id,
            )
            logger.info(
                f"Successfully saved CertificateParticipantWinnerMinted to DB with ULID: {saved.id} (token_id: {token_id}, winner_id: {winner_id}, competition_id: {competition_id})"
            )

            # Hapus signature single-use setelah winner mint sukses (user_id + signature) -> signature_certificate_winner
            try:
                raw_sig = args.get("signature")
                if isinstance(raw_sig, (bytes, HexBytes)):
                    sig_str = raw_sig.hex()
                elif raw_sig is None:
                    sig_str = ""
                else:
                    sig_str = str(raw_sig).strip()

                if sig_str:
                    sig_norm = sig_str.lower().strip()
                    if not sig_norm.startswith("0x"):
                        sig_norm = "0x" + sig_norm
                    sig_no0x = sig_norm[2:]

                    user_id = getattr(saved, "user_id", None)
                    if not user_id and participant:
                        try:
                            from sqlmodel import select as _select_fallback_w
                            from sqlalchemy import func as _func_fallback_w
                            from app.configs.database import (
                                AsyncSessionLocal as _AsyncSessionLocalFallbackW,
                            )
                            from app.models.user import UserModel as _UserModelFallbackW

                            async with _AsyncSessionLocalFallbackW() as _db_fb_w:
                                _stmt_fb_w = _select_fallback_w(
                                    _UserModelFallbackW
                                ).where(
                                    _func_fallback_w.lower(
                                        _UserModelFallbackW.wallet_address
                                    )
                                    == participant.lower()
                                )
                                _res_fb_w = await _db_fb_w.exec(_stmt_fb_w)
                                _first_w = _res_fb_w.first()
                                _user_fb_w = (
                                    _first_w[0]
                                    if isinstance(_first_w, (tuple, list))
                                    else _first_w
                                )
                                if _user_fb_w is not None:
                                    user_id = getattr(_user_fb_w, "id", None)
                        except Exception as _fb_e_w:
                            logger.debug(
                                f"Fallback user_id resolve failed for winner {participant}: {_fb_e_w}"
                            )

                    if user_id and sig_norm:
                        from sqlalchemy import (
                            delete as _delete_w,
                            func as _func2_w,
                            or_ as _or_w,
                        )
                        from app.configs.database import (
                            AsyncSessionLocal as _AsyncSessionLocal2W,
                        )
                        from app.models.signature_certificate_winner import (
                            SignatureCertificateWinnerModel,
                        )

                        async with _AsyncSessionLocal2W() as _db2_w:
                            _del_w = _delete_w(SignatureCertificateWinnerModel).where(
                                SignatureCertificateWinnerModel.user_id == user_id,
                                _or_w(
                                    _func2_w.lower(
                                        SignatureCertificateWinnerModel.signature
                                    )
                                    == sig_norm,
                                    _func2_w.lower(
                                        SignatureCertificateWinnerModel.signature
                                    )
                                    == sig_no0x,
                                ),
                            )
                            _result_w = await _db2_w.exec(_del_w)
                            await _db2_w.commit()
                            try:

                                _count_w = getattr(_result_w, "rowcount", 0) or 0
                            except Exception:
                                _count_w = 0
                            if _count_w:
                                logger.info(
                                    f"Deleted {_count_w} signature_certificate_winner row(s) for user_id={user_id} sig={sig_norm[:10]}... after CertificateParticipantWinnerMinted token_id={token_id} winner_id={winner_id}"
                                )
                            else:
                                from sqlmodel import select as _select2_w

                                _stmt2_w = _select2_w(
                                    SignatureCertificateWinnerModel
                                ).where(
                                    SignatureCertificateWinnerModel.user_id == user_id,
                                    _or_w(
                                        _func2_w.lower(
                                            SignatureCertificateWinnerModel.signature
                                        )
                                        == sig_norm,
                                        _func2_w.lower(
                                            SignatureCertificateWinnerModel.signature
                                        )
                                        == sig_no0x,
                                    ),
                                )
                                _res2_w = await _db2_w.exec(_stmt2_w)
                                _rows_w = _res2_w.all()
                                if _rows_w:
                                    for _row_w in _rows_w:
                                        _obj_w = (
                                            _row_w[0]
                                            if isinstance(_row_w, (tuple, list))
                                            else _row_w
                                        )
                                        await _db2_w.delete(_obj_w)
                                    await _db2_w.commit()
                                    logger.info(
                                        f"Deleted {len(_rows_w)} signature_certificate_winner row(s) (fallback) for user_id={user_id} sig={sig_norm[:10]}... token_id={token_id} winner_id={winner_id}"
                                    )
                                else:
                                    logger.debug(
                                        f"No matching signature_certificate_winner found to delete for user_id={user_id} sig={sig_norm[:10]}... (token_id={token_id} winner_id={winner_id})"
                                    )
                    else:
                        logger.debug(
                            f"Skip winner signature cleanup: user_id={user_id} sig_present={bool(sig_str)} token_id={token_id} winner_id={winner_id}"
                        )
                else:
                    logger.debug(
                        f"No signature in CertificateParticipantWinnerMinted args, skip cleanup (token_id={token_id} winner_id={winner_id})"
                    )
            except Exception as _e_w:
                logger.warning(
                    f"Failed to delete signature_certificate_winner after winner mint (token_id={token_id} winner_id={winner_id}): {_e_w}"
                )
        except Exception as e:
            logger.error(
                f"Failed to save CertificateParticipantWinnerMinted event to DB: {e}"
            )

    async def _handle_team_payment_created(self, tx_hash: str, args: Dict[str, Any]):
        try:
            from app.configs.database import AsyncSessionLocal
            from sqlmodel import select
            from sqlalchemy import func
            from app.models.user import UserModel
            from app.models.competition import CompetitionModel
            from app.models.team import TeamModel
            from app.models.team_role import TeamRoleModel
            from app.models.team_code import TeamCodeModel
            from app.models.skills_team import SkillsTeamModel
            from app.models.requirements_team import RequirementsTeamModel
            import secrets

            competition_id = str(args.get("competitionId") or "")
            cid = str(args.get("cid") or "")
            wallet_address = str(args.get("from") or "")
            if not wallet_address:
                logger.warning("Missing 'from' address in TeamPaymentCreated event")
                return

            indexer_state_id = await self._resolve_indexer_state_id()

            async with AsyncSessionLocal() as db:
                # 0. Anti double insert check by tx_hash (idempotency early exit)
                stmt_existing = select(TeamModel).where(TeamModel.tx_hash == tx_hash)
                res_existing = await db.exec(stmt_existing)
                existing_team = res_existing.first()
                if existing_team:
                    if isinstance(existing_team, (tuple, list)):
                        existing_team = existing_team[0]
                    logger.info(
                        f"Team already created for tx_hash={tx_hash} (team_id: {existing_team.id}), skipping duplicate insert."
                    )
                    return

                ipfs_data = await self._fetch_from_ipfs(cid) if cid else {}

                # 1. User
                wallet_lower = wallet_address.lower()
                stmt_user = select(UserModel).where(
                    func.lower(UserModel.wallet_address) == wallet_lower
                )
                res_user = await db.exec(stmt_user)
                user = res_user.first()
                if not user:
                    user = UserModel(wallet_address=wallet_address)
                    db.add(user)
                    await db.commit()
                    await db.refresh(user)
                elif isinstance(user, (tuple, list)):
                    user = user[0]

                # 2. Competition
                stmt_comp = select(CompetitionModel).where(
                    (CompetitionModel.competition_id == competition_id)
                    | (CompetitionModel.id == competition_id),
                    CompetitionModel.indexer_state_id == indexer_state_id,
                )
                res_comp = await db.exec(stmt_comp)
                competition = res_comp.first()
                if not competition:
                    logger.warning(
                        f"Competition {competition_id} not found for TeamPaymentCreated"
                    )
                    return
                elif isinstance(competition, (tuple, list)):
                    competition = competition[0]

                # 3. Check if team was already created for this user & competition (via API or previous event)
                stmt_existing_user_team = select(TeamModel).where(
                    TeamModel.competition_id == competition.id,
                    (TeamModel.user_id == user.id)
                    | (
                        TeamModel.id.in_(
                            select(TeamRoleModel.team_id).where(
                                TeamRoleModel.user_id == user.id
                            )
                        )
                    ),
                    TeamModel.deleted_at.is_(None),
                )
                res_user_team = await db.exec(stmt_existing_user_team)
                existing_user_team = res_user_team.first()
                if existing_user_team:
                    if isinstance(existing_user_team, (tuple, list)):
                        existing_user_team = existing_user_team[0]
                    if not existing_user_team.tx_hash or existing_user_team.tx_hash != tx_hash:
                        existing_user_team.tx_hash = tx_hash
                        db.add(existing_user_team)
                        await db.commit()
                        await db.refresh(existing_user_team)
                    logger.info(
                        f"Successfully linked tx_hash={tx_hash} to existing team (team_id: {existing_user_team.id}), prevented duplicate team insert."
                    )
                    return

                # 4. Process IPFS data
                name = str(ipfs_data.get("name") or "").strip()
                if not name:
                    name = f"Team {secrets.token_hex(3).upper()}"

                visibility = bool(ipfs_data.get("visibility", True))
                description = str(ipfs_data.get("description") or "").strip()

                skills = ipfs_data.get("skills_team") or ipfs_data.get("skills")
                if not isinstance(skills, list):
                    skills = []
                skills_list = [str(s).strip() for s in skills if str(s).strip()]

                # 5. Create Team with tx_hash
                team = TeamModel(
                    name=name,
                    visibility=visibility,
                    description=description,
                    competition_id=competition.id,
                    user_id=user.id,
                    tx_hash=tx_hash,
                )
                db.add(team)
                await db.commit()
                await db.refresh(team)

                # 5. Create TeamRole
                team_role = TeamRoleModel(user_id=user.id, team_id=team.id, role="LEAD")
                db.add(team_role)

                # 6. Create RequirementsTeam
                req_team = RequirementsTeamModel(
                    requirement=description, team_id=team.id
                )
                db.add(req_team)

                # 7. Create SkillsTeam
                for skill_name in skills_list:
                    skill_team = SkillsTeamModel(name=skill_name, team_id=team.id)
                    db.add(skill_team)

                # 8. Create TeamCode if private
                if not visibility:
                    team_code_str = f"COBALT-{secrets.token_hex(5).upper()}"
                    team_code = TeamCodeModel(code=team_code_str, team_id=team.id)
                    db.add(team_code)

                await db.commit()

            logger.info(
                f"Successfully saved TeamPaymentCreated to DB (team_id: {team.id}, competition_id: {competition_id})"
            )

        except Exception as e:
            logger.error(f"Failed to save TeamPaymentCreated event to DB: {e}")

    async def _handle_competition_event(
        self, event_name: str, tx_hash: str, args: Dict[str, Any]
    ):
        try:
            from app.databases.competition import CompetitionDatabases

            if event_name == "CompetitionPaymentConfigured":
                raw_comp_id = args.get("competitionId")
                competition_id = str(raw_comp_id) if raw_comp_id is not None else ""
                fee_token_address = _normalize_address(args.get("tokenAddress"))
                raw_fee = args.get("fee")
                fee = int(raw_fee) if raw_fee is not None else None
                # Payment tidak dikonfigurasi (zero address + fee 0) -> biarkan kosong
                if fee_token_address is None and not fee:
                    fee = None

                indexer_state_id = await self._resolve_indexer_state_id()
                await CompetitionDatabases.update_competition_payment(
                    competition_id=competition_id,
                    fee_token_address=fee_token_address,
                    fee=fee,
                    tx_hash=tx_hash,
                    indexer_state_id=indexer_state_id,
                )
                logger.info(
                    f"Successfully saved CompetitionPaymentConfigured to DB (competition_id: {competition_id}, fee_token_address: {fee_token_address}, fee: {fee})"
                )
                return

            if event_name == "CompetitionWinnerConfigured":
                raw_comp_id = args.get("competitionId")
                competition_id = str(raw_comp_id) if raw_comp_id is not None else ""
                raw_winner_id = args.get("winnerId")
                winner_id = int(raw_winner_id) if raw_winner_id is not None else 0
                prize_token = str(args.get("prizeToken") or "")
                raw_amount = args.get("prizeAmount")
                prize_amount = int(raw_amount) if raw_amount is not None else 0
                certificate_cid = str(args.get("certificateCID") or "")

                category = ""
                if certificate_cid:
                    cert_meta = await self._fetch_from_ipfs(certificate_cid)
                    if isinstance(cert_meta, dict):
                        category = str(
                            cert_meta.get("title")
                            or cert_meta.get("name")
                            or cert_meta.get("category")
                            or ""
                        )

                indexer_state_id = await self._resolve_indexer_state_id()
                await CompetitionDatabases.configure_competition_winner(
                    competition_id=competition_id,
                    winner_id=winner_id,
                    prize_amount=prize_amount,
                    certificate_cid=certificate_cid,
                    category=category,
                    tx_hash=tx_hash,
                    indexer_state_id=indexer_state_id,
                )
                logger.info(
                    f"Successfully saved CompetitionWinnerConfigured to DB (competition_id: {competition_id}, winner_id: {winner_id}, prize_token: {prize_token}, prize_amount: {prize_amount})"
                )
                return

            # CompetitionCreated event args: id, organization, cid, formation,
            # prizeCertificateClaim, certificateCID, priceCompetitionFeeId
            comp_cid = str(args.get("cid") or "")
            certificate_cid = str(args.get("certificateCID") or "")
            formation = str(args.get("formation") or "")
            wallet_address = str(args.get("organization") or "")
            competition_id = str(args.get("id") or "")

            raw_fee_id = args.get("priceCompetitionFeeId")
            price_competition_fee_id = (
                int(raw_fee_id) if raw_fee_id is not None else None
            )

            ipfs_data = await self._fetch_from_ipfs(comp_cid) if comp_cid else {}

            name = str(ipfs_data.get("name") or "")
            category = str(ipfs_data.get("category") or "")
            description = str(ipfs_data.get("description") or "")
            requirement = str(
                ipfs_data.get("requirements") or ipfs_data.get("requirement") or ""
            )
            guidebook_cid = str(
                ipfs_data.get("guideBookCID")
                or ipfs_data.get("guideBookCid")
                or ipfs_data.get("guidebook_cid")
                or ipfs_data.get("guidebookCid")
                or comp_cid
            )

            sched = (
                ipfs_data.get("schedule")
                if isinstance(ipfs_data.get("schedule"), dict)
                else {}
            )

            registration_window = _parse_timestamp(
                sched.get("registrationWindow") or sched.get("registration_window")
            )
            competition_window = _parse_timestamp(
                sched.get("competitionWindow") or sched.get("competition_window")
            )
            submission_deadline = _parse_timestamp(
                sched.get("submissionDeadline") or sched.get("submission_deadline")
            )
            judging_review = _parse_timestamp(
                sched.get("judgingReview") or sched.get("judging_review")
            )
            result_announcement = _parse_timestamp(
                sched.get("resultAnnouncement") or sched.get("result_announcement")
            )
            pirze_certificate_claim = _parse_timestamp(
                args.get("prizeCertificateClaim")
                or sched.get("prizeCertificateClaim")
                or sched.get("prize_certificate_claim")
            )

            # Event CompetitionCreated tidak membawa daftar winners on-chain (winner
            # dikonfigurasi lewat CompetitionWinnerConfigured yang di-emit
            # lebih dulu). Gunakan winners dari metadata IPFS agar title
            # (mis. "1st Place") bisa diterapkan ke baris winner yang sudah
            # ada, dicocokkan berdasarkan urutan.
            ipfs_winners = (
                ipfs_data.get("winners")
                if isinstance(ipfs_data.get("winners"), list)
                else []
            )

            winners = []
            for i, w in enumerate(ipfs_winners):
                if not isinstance(w, dict):
                    continue
                w_title = w.get("title") or w.get("category")
                w_cert_cid = w.get("certificateCID")
                if not w_title and w_cert_cid:
                    w_cert_meta = await self._fetch_from_ipfs(str(w_cert_cid))
                    if isinstance(w_cert_meta, dict):
                        w_title = (
                            w_cert_meta.get("title")
                            or w_cert_meta.get("name")
                            or w_cert_meta.get("category")
                        )
                winners.append(
                    {
                        "title": str(w_title or f"Winner #{i + 1}"),
                        "certificateCID": str(w_cert_cid or ""),
                        "_from_metadata": True,
                    }
                )

            saved_comp = await CompetitionDatabases.add_competition(
                wallet_address=wallet_address,
                tx_hash=tx_hash,
                name=name,
                category=category,
                description=description,
                requirement=requirement,
                formation=formation,
                registration_window=registration_window,
                competition_window=competition_window,
                submission_deadline=submission_deadline,
                judging_review=judging_review,
                result_announcement=result_announcement,
                pirze_certificate_claim=pirze_certificate_claim,
                certificate_cid=certificate_cid,
                guidebook_cid=guidebook_cid,
                competition_id=competition_id,
                price_competition_fee_id=price_competition_fee_id,
                winners=winners,
                indexer_state_id=await self._resolve_indexer_state_id(),
            )
            logger.info(
                f"Successfully saved Competition to DB with ULID: {saved_comp.id} (competition_id: {saved_comp.competition_id}, tx: {tx_hash})"
            )
        except Exception as e:
            logger.error(
                f"Failed to save {event_name} event to DB (tx: {tx_hash}): {e}"
            )

    async def _print_event_details(
        self, event_name: str, args: Dict[str, Any], tx_hash: str
    ):
        if event_name in (
            "CompetitionCreated",
            "CompetitionPaymentConfigured",
            "CompetitionWinnerConfigured",
        ):
            competition_id = args.get("competitionId") or args.get("id")
            print(f"  🏆 Competition Event ({event_name}):")
            print(f"     Tx Hash:        {tx_hash}")
            print(f"     Competition ID: {competition_id}")

            if event_name == "CompetitionCreated":
                comp_cid = str(args.get("cid") or "")
                ipfs_data = await self._fetch_from_ipfs(comp_cid) if comp_cid else {}
                sched = (
                    ipfs_data.get("schedule")
                    if isinstance(ipfs_data.get("schedule"), dict)
                    else {}
                )

                print(f"     Creator Wallet (Org):    {args.get('organization')}")
                print(
                    f"     Price Competition Fee ID:{args.get('priceCompetitionFeeId')}"
                )
                print(f"     Competition CID:         {comp_cid}")
                print(f"     Name:                    {ipfs_data.get('name')}")
                print(f"     Category:                {ipfs_data.get('category')}")
                print(f"     Description:             {ipfs_data.get('description')}")
                print(
                    f"     Requirements:            {ipfs_data.get('requirements') or ipfs_data.get('requirement')}"
                )
                print(f"     Formation:               {args.get('formation')}")
                print(f"     Schedule:")
                print(
                    f"       Registration Window:   {sched.get('registrationWindow') or sched.get('registration_window')}"
                )
                print(
                    f"       Competition Window:    {sched.get('competitionWindow') or sched.get('competition_window')}"
                )
                print(
                    f"       Submission Deadline:   {sched.get('submissionDeadline') or sched.get('submission_deadline')}"
                )
                print(
                    f"       Judging Review:        {sched.get('judgingReview') or sched.get('judging_review')}"
                )
                print(
                    f"       Result Announcement:   {sched.get('resultAnnouncement') or sched.get('result_announcement')}"
                )
                print(
                    f"       Prize Certificate Claim: {args.get('prizeCertificateClaim')}"
                )
                print(f"     Certificate CID:         {args.get('certificateCID')}")
                print(
                    f"     Guidebook CID:           {ipfs_data.get('guideBookCID') or ipfs_data.get('guidebook_cid') or comp_cid}"
                )

            elif event_name == "CompetitionPaymentConfigured":
                print(f"     Token Address:  {args.get('tokenAddress')}")
                print(f"     Fee:            {args.get('fee')}")

            elif event_name == "CompetitionWinnerConfigured":
                print(f"     Winner ID:       {args.get('winnerId')}")
                print(f"     Prize Token:     {args.get('prizeToken')}")
                print(f"     Prize Amount:    {args.get('prizeAmount')}")
                print(f"     Certificate CID: {args.get('certificateCID')}")
                print(f"     Team ID:         {args.get('teamId')}")

        elif event_name == "CompetitionFeePaid":
            print(f"  💳 Competition Fee Paid:")
            print(f"     Tx Hash:        {tx_hash}")
            print(f"     Competition ID: {args.get('competitionId')}")
            print(f"     Payer:          {args.get('payer')}")
            print(f"     Token Address:  {args.get('tokenAddress')}")
            print(f"     Amount:         {args.get('amount')}")

        elif event_name == "WinnerSet":
            print(f"  🥇 Winner Set:")
            print(f"     Tx Hash:               {tx_hash}")
            print(f"     Winner ID:             {args.get('winnerId')}")
            print(f"     Participant:           {args.get('participant')}")
            print(f"     Competition ID:        {args.get('competitionId')}")
            print(f"     Signature:             {args.get('signature')}")

        elif event_name == "ListingTokenAdded":
            print(f"  📌 ListingToken Added:")
            print(f"     Tx Hash:       {tx_hash}")
            print(f"     ID:            {args.get('listingTokenId')}")
            print(f"     Token Address: {args.get('tokenAddress')}")
            print(f"     Is Active:     {args.get('isActive')}")

        elif event_name == "ListingTokenDeactivated":
            print(f"  ❌ ListingToken Deactivated:")
            print(f"     Tx Hash:       {tx_hash}")
            print(f"     ID:            {args.get('listingTokenId')}")
            print(f"     Token Address: {args.get('tokenAddress')}")
            print(f"     Is Active:     {args.get('isActive')}")

        elif event_name in (
            "PriceCompetitionFeeSet",
            "PriceCompetitionFeeUpdated",
        ):
            cid = str(args.get("cid") or "")
            title = cid
            description = cid
            if cid:
                fee_meta = await self._fetch_from_ipfs(cid)
                if isinstance(fee_meta, dict):
                    title = fee_meta.get("name") or fee_meta.get("title") or title
                    description = fee_meta.get("description") or description

            print(f"  💰 Price Competition Fee Set/Updated:")
            print(f"     Tx Hash:       {tx_hash}")
            print(f"     ID:            {args.get('id')}")
            print(f"     Treasury Fee:  {args.get('treasuryFee')}")
            print(f"     Token Address: {args.get('tokenAddress')}")
            print(f"     Title:         {title}")
            print(f"     Description:   {description}")

        elif event_name == "SignerAddressUpdated":
            print(f"  ✍️  Signer Address Updated:")
            print(f"     Tx Hash:        {tx_hash}")
            print(f"     Signer Address: {args.get('signerAddress')}")

        elif event_name == "TreasuryAdded":
            print(f"  🏦 Treasury Added:")
            print(f"     Tx Hash:       {tx_hash}")
            print(f"     Token Address: {args.get('tokenAddress')}")
            print(f"     Sender:        {args.get('sender')}")
            print(f"     Amount:        {args.get('amount')}")

        elif event_name == "PrizeDeposited":
            print(f"  💰 Prize Deposited:")
            print(f"     Tx Hash:           {tx_hash}")
            print(f"     Treasury Prize ID: {args.get('treasuryPrizeId')}")
            print(f"     Competition ID:    {args.get('competitionId')}")
            print(f"     Token Address:     {args.get('tokenAddress')}")
            print(f"     Sender:            {args.get('sender')}")
            print(f"     Amount:            {args.get('amount')}")

        elif event_name == "PrizeDistributed":
            print(f"  🎁 Prize Distributed:")
            print(f"     Tx Hash:           {tx_hash}")
            print(f"     Treasury Prize ID: {args.get('treasuryPrizeId')}")
            print(f"     Competition ID:    {args.get('competitionId')}")
            print(f"     Token Address:     {args.get('tokenAddress')}")
            print(f"     Recipient:         {args.get('recipient')}")
            print(f"     Amount:            {args.get('amount')}")

        elif event_name == "NativeReceived":
            print(f"  💎 Native Received:")
            print(f"     Tx Hash: {tx_hash}")
            print(f"     Sender:  {args.get('sender')}")
            print(f"     Amount:  {args.get('amount')}")

        elif event_name == "CertificateParticipantMinted":
            print(f"  🎖️  Certificate Participant Minted:")
            print(f"     Tx Hash:        {tx_hash}")
            print(f"     Token ID:       {args.get('tokenId')}")
            print(f"     Participant:    {args.get('participant')}")
            print(f"     Competition ID: {args.get('competitionId')}")
            print(f"     Team ID:        {args.get('teamId')}")
            print(f"     Signature:      {args.get('signature')}")
            print(f"     URI:            {args.get('uri')}")

        elif event_name == "CertificateParticipantWinnerMinted":
            print(f"  🏆 Certificate Participant Winner Minted:")
            print(f"     Tx Hash:        {tx_hash}")
            print(f"     Token ID:       {args.get('tokenId')}")
            print(f"     Participant:    {args.get('participant')}")
            print(f"     Competition ID: {args.get('competitionId')}")
            print(f"     Winner ID:      {args.get('winnerId')}")
            print(f"     Team ID:        {args.get('teamId')}")
            print(f"     Signature:      {args.get('signature')}")
            print(f"     URI:            {args.get('uri')}")

        elif event_name == "TeamPaymentCreated":
            cid = args.get("cid") or ""
            ipfs_data = await self._fetch_from_ipfs(cid) if cid else {}

            print(f"  💸 Team Payment Created:")
            print(f"     Tx Hash:        {tx_hash}")
            print(f"     Competition ID: {args.get('competitionId')}")
            print(f"     CID:            {cid}")
            if ipfs_data:
                print(f"     IPFS Data:      {json.dumps(ipfs_data)}")
            print(f"     Token:          {args.get('token')}")
            print(f"     From:           {args.get('from')}")
            print(f"     To:             {args.get('to')}")
            print(f"     Amount:         {args.get('amount')}")

        print()

    def get_status(self) -> Dict[str, Any]:
        status_data = {
            "is_running": self.is_running,
            "rpc_url": settings.web3_rpc_url,
            "contracts": [],
        }
        for cfg in self.contract_configs:
            name = cfg["name"]
            addr = cfg["address"]
            status_data["contracts"].append(
                {
                    "contract_name": name,
                    "contract_address": addr,
                    "last_scanned_block": self.last_scanned_blocks.get(name, 0),
                    "updated_at": self.last_updated_at.get(name),
                }
            )
        return status_data


indexer_service = Web3Indexer()
