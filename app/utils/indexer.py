import asyncio
import json
import logging
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from eth_utils import event_abi_to_log_topic
from hexbytes import HexBytes
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


def _clean_args(args: Any) -> Any:
    if isinstance(args, (bytes, HexBytes)):
        return args.hex()
    elif isinstance(args, (dict, Mapping)):
        return {str(k): _clean_args(v) for k, v in args.items()}
    elif isinstance(args, (list, tuple, set)):
        return [_clean_args(x) for x in args]
    return args


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

    def _load_abi(self, filename: str) -> List[Dict[str, Any]]:
        abi_path = Path(__file__).parent.parent / "abi" / filename
        with open(abi_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def _setup_contracts(self):
        mapping = [
            (
                "CertificateCompetition",
                settings.certificate_competition_contract,
                "CertificateCompetition.json",
            ),
            (
                "CompetitionManager",
                settings.competition_contract,
                "CompetitionManager.json",
            ),
            (
                "TreasuryPlatform",
                settings.treasury_platform_contract,
                "TreasuryPlatform.json",
            ),
            (
                "TreasuryPrize",
                settings.treasury_prize_contract,
                "TreasuryPrize.json",
            ),
            (
                "ListingTokenPrize",
                settings.listing_token_prize_contract,
                "ListingTokenPrizeContract.json",
            ),
            (
                "PriceCompetitionManager",
                settings.price_competition_manager_contract,
                "PriceCompetitionManager.json",
            ),
            (
                "SignerManager",
                settings.signer_manager_contract,
                "SignerManager.json",
            ),
            (
                "SignerManagerCertificate",
                settings.signer_manager_certificate_contract,
                "SignerManager.json",
            ),
            (
                "CertificateManager",
                settings.certificate_manager_contract,
                "CertificateManager.json",
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
            db_block = await IndexerStateDatabases.get_last_scanned_block(name)
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
            await IndexerStateDatabases.set_last_scanned_block(name, to_block)

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

        tx_hash = HexBytes(log["transactionHash"]).hex()
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

            self._print_event_details(event_name, cleaned_args, tx_hash)

            if event_name == "CompetitionCreated":
                await self._handle_competition_created(tx_hash, cleaned_args)
            elif event_name == "CompetitionFeePaid":
                await self._handle_competition_fee_paid(tx_hash, cleaned_args)
            elif event_name == "WinnerSet":
                await self._handle_winner_set(tx_hash, cleaned_args)
            elif event_name in (
                "ListingTokenPrizeAdded",
                "ListingTokenPrizeDeactivated",
            ):
                await self._handle_listing_token_prize_added(tx_hash, cleaned_args)
            elif event_name == "PrizeDeposited":
                await self._handle_prize_deposited(tx_hash, cleaned_args)
            elif event_name == "PrizeDistributed":
                await self._handle_prize_distributed(tx_hash, cleaned_args)
            elif event_name in (
                "PriceCompetitionFeeSet",
                "PriceCompetitionFeeUpdated",
            ):
                await self._handle_price_competition_fee_set(tx_hash, cleaned_args)

        except Exception as e:
            logger.error(f"Error processing log {tx_hash}:{log_index}: {e}")

    async def _handle_listing_token_prize_added(
        self, tx_hash: str, args: Dict[str, Any]
    ):
        try:
            from app.databases.listing_token_prize import ListingTokenPrizeDatabases

            listing_token_prize_id = int(args.get("listingTokenPrizeId") or 0)
            token_address = str(args.get("tokenAddress") or "")
            is_active = bool(args.get("isActive", True))

            saved = await ListingTokenPrizeDatabases.add_listing_token_prize(
                tx_hash=tx_hash,
                listing_token_prize_id=listing_token_prize_id,
                token_address=token_address,
                is_active=is_active,
            )
            logger.info(
                f"Successfully saved ListingTokenPrize to DB with ULID: {saved.id} (listing_token_prize_id: {listing_token_prize_id})"
            )
        except Exception as e:
            logger.error(f"Failed to save ListingTokenPrize event to DB: {e}")

    async def _handle_prize_deposited(self, tx_hash: str, args: Dict[str, Any]):
        try:
            from app.databases.prize_deposited import PrizeDepositedDatabases

            treasury_prize_id = int(args.get("treasuryPrizeId") or 0)
            competition_id = str(args.get("competitionId") or "")
            token_address = str(args.get("tokenAddress") or "")
            sender = str(args.get("sender") or "")
            amount = int(args.get("amount") or 0)

            saved = await PrizeDepositedDatabases.add_prize_deposited(
                tx_hash=tx_hash,
                treasury_prize_id=treasury_prize_id,
                competition_id=competition_id,
                token_address=token_address,
                sender=sender,
                amount=amount,
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

            saved = await PrizeDistributedDatabases.add_prize_distributed(
                tx_hash=tx_hash,
                treasury_prize_id=treasury_prize_id,
                competition_id=competition_id,
                token_address=token_address,
                recipient=recipient,
                amount=amount,
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

            price_competition_fee_id = int(
                args.get("id") or args.get("priceCompetitionFeeId") or 0
            )
            treasury_fee = int(args.get("treasuryFee") or 0)
            token_address = str(args.get("tokenAddress") or "")
            title = str(args.get("title") or "")
            description = str(args.get("description") or "")

            saved = await PriceCompetitionDatabases.add_price_competition(
                tx_hash=tx_hash,
                price_competition_fee_id=price_competition_fee_id,
                treasury_fee=treasury_fee,
                token_address=token_address,
                title=title,
                description=description,
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

            saved = await CompetitionFeePaidDatabases.add_competition_fee_paid(
                tx_hash=tx_hash,
                competition_id=competition_id,
                payer=payer,
                token_address=token_address,
                amount=amount,
            )
            logger.info(
                f"Successfully saved CompetitionFeePaid to DB with ULID: {saved.id} (event competition_id: {competition_id})"
            )
        except Exception as e:
            logger.error(f"Failed to save CompetitionFeePaid event to DB: {e}")

    async def _handle_winner_set(self, tx_hash: str, args: Dict[str, Any]):
        try:
            from app.databases.participant_winner import ParticipantWinnerDatabases

            winner_id = int(args.get("winnerId") or 0)
            participant = str(args.get("participant") or "")
            competition_id = str(args.get("competitionId") or "")
            participant_winner_id = int(args.get("participantWinnerId") or 0)
            title = str(args.get("title") or "")

            saved = await ParticipantWinnerDatabases.add_participant_winner(
                tx_hash=tx_hash,
                winner_id=winner_id,
                participant=participant,
                competition_id=competition_id,
                participant_winner_id=participant_winner_id,
                title=title,
            )
            logger.info(
                f"Successfully saved ParticipantWinner to DB with ULID: {saved.id} (winner_id: {winner_id}, participant_winner_id: {participant_winner_id})"
            )
        except Exception as e:
            logger.error(f"Failed to save WinnerSet event to DB: {e}")

    async def _handle_competition_created(self, tx_hash: str, args: Dict[str, Any]):
        try:
            from app.databases.competition import CompetitionDatabases

            comp = (
                args.get("competition")
                if isinstance(args.get("competition"), dict)
                else {}
            )
            sched = (
                comp.get("schedule") if isinstance(comp.get("schedule"), dict) else {}
            )
            winners = (
                args.get("winners") if isinstance(args.get("winners"), list) else []
            )

            wallet_address = args.get("organization") or comp.get("organization") or ""
            name = comp.get("name", "")
            category = comp.get("category", "")
            description = comp.get("description", "")
            requirement = comp.get("requirements") or comp.get("requirement") or ""
            formation = comp.get("formation", "")
            certificate_cid = comp.get("certificateCID", "")
            guidebook_cid = comp.get("guideBookCID", "")

            registration_window = _parse_timestamp(sched.get("registrationWindow"))
            competition_window = _parse_timestamp(sched.get("competitionWindow"))
            submission_deadline = _parse_timestamp(sched.get("submissionDeadline"))
            judging_review = _parse_timestamp(sched.get("judgingReview"))
            result_announcement = _parse_timestamp(sched.get("resultAnnouncement"))
            pirze_certificate_claim = _parse_timestamp(
                sched.get("prizeCertificateClaim")
            )

            raw_fee_id = args.get("priceCompetitionFeeId")
            price_competition_fee_id = (
                int(raw_fee_id) if raw_fee_id is not None else None
            )

            raw_comp_id = (
                args.get("id")
                if args.get("id") is not None
                else (comp.get("id") if isinstance(comp, dict) else None)
            )
            competition_id = str(raw_comp_id or "")

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
            )
            logger.info(
                f"Successfully saved Competition to DB with ULID: {saved_comp.id} (competition_id: {saved_comp.competition_id}, tx: {tx_hash})"
            )
        except Exception as e:
            logger.error(
                f"Failed to save CompetitionCreated event to DB (tx: {tx_hash}): {e}"
            )

    def _print_event_details(self, event_name: str, args: Dict[str, Any], tx_hash: str):
        if event_name == "CompetitionCreated":
            comp = (
                args.get("competition")
                if isinstance(args.get("competition"), dict)
                else {}
            )
            sched = (
                comp.get("schedule") if isinstance(comp.get("schedule"), dict) else {}
            )
            winners = (
                args.get("winners") if isinstance(args.get("winners"), list) else []
            )
            token_addr = ""
            if winners and isinstance(winners[0], dict):
                token_addr = str(
                    winners[0].get("prizeToken") or winners[0].get("prize_token") or ""
                )
            print(f"  🏆 Competition Created:")
            print(f"     Tx Hash:                 {tx_hash}")
            print(f"     ID:                      {args.get('id') or comp.get('id')}")
            print(
                f"     Creator Wallet (Org):    {args.get('organization') or comp.get('organization')}"
            )
            print(f"     Price Competition Fee ID:{args.get('priceCompetitionFeeId')}")
            print(f"     Token Address:           {token_addr}")
            print(f"     Name:                    {comp.get('name')}")
            print(f"     Category:                {comp.get('category')}")
            print(f"     Description:             {comp.get('description')}")
            print(f"     Requirements:            {comp.get('requirements') or comp.get('requirement')}")
            print(f"     Formation:               {comp.get('formation')}")
            print(f"     Schedule:")
            print(f"       Registration Window:   {sched.get('registrationWindow')}")
            print(f"       Competition Window:    {sched.get('competitionWindow')}")
            print(f"       Submission Deadline:   {sched.get('submissionDeadline')}")
            print(f"       Judging Review:        {sched.get('judgingReview')}")
            print(f"       Result Announcement:   {sched.get('resultAnnouncement')}")
            print(
                f"       Prize Certificate Claim: {sched.get('prizeCertificateClaim')}"
            )
            print(f"     Certificate CID:         {comp.get('certificateCID')}")
            print(f"     Guidebook CID:           {comp.get('guideBookCID')}")
            if winners:
                print(f"     Winners ({len(winners)}):")
                for i, w in enumerate(winners, 1):
                    if isinstance(w, dict):
                        print(f"       - Winner #{i}:")
                        print(
                            f"           Winner ID:       {w.get('id') or w.get('winnerId')}"
                        )
                        print(f"           Competition ID:  {w.get('competitionId')}")
                        print(f"           Title:           {w.get('title')}")
                        print(f"           Prize Token:     {w.get('prizeToken')}")
                        print(f"           Prize Amount:    {w.get('prizeAmount')}")
                        print(f"           Certificate CID: {w.get('certificateCID')}")

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
            print(f"     Participant Winner ID: {args.get('participantWinnerId')}")
            print(f"     Title:                 {args.get('title')}")

        elif event_name == "ListingTokenPrizeAdded":
            print(f"  📌 ListingTokenPrize Added:")
            print(f"     Tx Hash:       {tx_hash}")
            print(f"     ID:            {args.get('listingTokenPrizeId')}")
            print(f"     Token Address: {args.get('tokenAddress')}")
            print(f"     Is Active:     {args.get('isActive')}")

        elif event_name == "ListingTokenPrizeDeactivated":
            print(f"  ❌ ListingTokenPrize Deactivated:")
            print(f"     Tx Hash:       {tx_hash}")
            print(f"     ID:            {args.get('listingTokenPrizeId')}")
            print(f"     Token Address: {args.get('tokenAddress')}")
            print(f"     Is Active:     {args.get('isActive')}")

        elif event_name == "PriceCompetitionFeeSet":
            print(f"  💰 Price Competition Fee Set:")
            print(f"     Tx Hash:       {tx_hash}")
            print(f"     ID:            {args.get('id')}")
            print(f"     Treasury Fee:  {args.get('treasuryFee')}")
            print(f"     Token Address: {args.get('tokenAddress')}")
            print(f"     Title:         {args.get('title')}")
            print(f"     Description:   {args.get('description')}")

        elif event_name == "PriceCompetitionFeeUpdated":
            print(f"  🔄 Price Competition Fee Updated:")
            print(f"     Tx Hash:       {tx_hash}")
            print(f"     ID:            {args.get('id')}")
            print(f"     Treasury Fee:  {args.get('treasuryFee')}")
            print(f"     Token Address: {args.get('tokenAddress')}")
            print(f"     Title:         {args.get('title')}")
            print(f"     Description:   {args.get('description')}")

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

        elif event_name == "CertificateParticipantAdded":
            print(f"  📜 Certificate Participant Added:")
            print(f"     Tx Hash:        {tx_hash}")
            print(f"     ID:             {args.get('id')}")
            print(f"     Competition ID: {args.get('competitionId')}")
            print(f"     Participant:    {args.get('participant')}")

        elif event_name == "CertificateParticipantWinnerAdded":
            print(f"  🏅 Certificate Participant Winner Added:")
            print(f"     Tx Hash:        {tx_hash}")
            print(f"     ID:             {args.get('id')}")
            print(f"     Competition ID: {args.get('competitionId')}")
            print(f"     Participant:    {args.get('participant')}")
            print(f"     Winner ID:      {args.get('winnerId')}")

        elif event_name == "CertificateParticipantMinted":
            print(f"  🎖️  Certificate Participant Minted:")
            print(f"     Tx Hash:        {tx_hash}")
            print(f"     Token ID:       {args.get('tokenId')}")
            print(f"     Participant:    {args.get('participant')}")
            print(f"     Competition ID: {args.get('competitionId')}")
            print(f"     URI:            {args.get('uri')}")

        elif event_name == "CertificateParticipantWinnerMinted":
            print(f"  🏆 Certificate Participant Winner Minted:")
            print(f"     Tx Hash:        {tx_hash}")
            print(f"     Token ID:       {args.get('tokenId')}")
            print(f"     Participant:    {args.get('participant')}")
            print(f"     Competition ID: {args.get('competitionId')}")
            print(f"     Winner ID:      {args.get('winnerId')}")
            print(f"     URI:            {args.get('uri')}")

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
