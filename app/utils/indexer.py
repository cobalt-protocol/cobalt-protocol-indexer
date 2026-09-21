import asyncio
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from hexbytes import HexBytes
from web3 import AsyncHTTPProvider, AsyncWeb3
from web3.contract import AsyncContract

from app.configs import settings

logger = logging.getLogger("web3_indexer")
logger.setLevel(logging.INFO)


def _clean_args(args: Any) -> Any:
    if isinstance(args, (bytes, HexBytes)):
        return args.hex()
    elif isinstance(args, dict):
        return {k: _clean_args(v) for k, v in args.items()}
    elif isinstance(args, (list, tuple)):
        return [_clean_args(x) for x in args]
    return args


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
                "ListingTokenPrize",
                settings.listing_token_prize_contract,
                "ListingTokenPrizeContract.json",
            ),
            ("FeeManager", settings.fee_manager_contract, "FeeManager.json"),
            (
                "FeeManagerCompetition",
                settings.fee_manager_competition_contract,
                "FeeManagerCompetition.json",
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
                        inputs = ",".join(
                            [inp["type"] for inp in item.get("inputs", [])]
                        )
                        sig = f"{event_name}({inputs})"
                        topic0 = self.w3.keccak(text=sig).hex()
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
            if settings.web3_start_block is not None:
                from_block = settings.web3_start_block
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
                self._process_log(cfg, log)

            self.last_scanned_blocks[name] = to_block
            self.last_updated_at[name] = datetime.now(timezone.utc).isoformat()

        except Exception as e:
            logger.error(
                f"Error indexing {name} from block {from_block} to {to_block}: {e}"
            )

    def _process_log(self, cfg: Dict[str, Any], log: Any):
        name = cfg["name"]
        address = cfg["address"]
        contract: AsyncContract = cfg["contract"]
        topic_map = cfg["topic_map"]

        topics = log.get("topics", [])
        if not topics:
            return

        topic0 = HexBytes(topics[0]).hex()
        event_name = topic_map.get(topic0)
        if not event_name:
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

            self._print_event_details(event_name, cleaned_args)

        except Exception as e:
            logger.error(f"Error processing log {tx_hash}:{log_index}: {e}")

    def _print_event_details(self, event_name: str, args: Dict[str, Any]):
        if event_name == "OwnershipTransferred":
            print(f"  🔑 Ownership Transferred:")
            print(f"     Previous Owner: {args.get('previousOwner')}")
            print(f"     New Owner:      {args.get('newOwner')}")

        elif event_name == "CompetitionCreated":
            print(f"  🏆 Competition Created:")
            print(f"     ID:              {args.get('id')}")
            print(f"     Organization:    {args.get('organization')}")
            print(f"     Name:            {args.get('name')}")
            print(f"     Category:        {args.get('category')}")
            print(f"     End At:          {args.get('endAt')}")
            print(f"     Certificate CID: {args.get('certificateCID')}")

        elif event_name == "WinnerSet":
            print(f"  🥇 Winner Set:")
            print(f"     Winner ID:            {args.get('winnerId')}")
            print(f"     Participant:           {args.get('participant')}")
            print(f"     Competition ID:        {args.get('competitionId')}")
            print(f"     Participant Winner ID: {args.get('participantWinnerId')}")

        elif event_name == "ListingTokenPrizeAdded":
            print(f"  📌 ListingTokenPrize Added:")
            print(f"     ID:            {args.get('listingTokenPrizeId')}")
            print(f"     Token Address: {args.get('tokenAddress')}")
            print(f"     Is Active:     {args.get('isActive')}")

        elif event_name == "ListingTokenPrizeDeactivated":
            print(f"  ❌ ListingTokenPrize Deactivated:")
            print(f"     ID:            {args.get('listingTokenPrizeId')}")
            print(f"     Token Address: {args.get('tokenAddress')}")
            print(f"     Is Active:     {args.get('isActive')}")

        elif event_name == "FeesSet":
            print(f"  💰 Fees Set:")
            print(f"     ID:           {args.get('id')}")
            print(f"     Treasury Fee: {args.get('treasuryFee')}")
            print(f"     Title:        {args.get('title')}")
            print(f"     Description:  {args.get('description')}")

        elif event_name == "SignerAddressSet":
            print(f"  ✍️  Signer Address Set:")
            print(f"     Signer Address: {args.get('signerAddress')}")

        elif event_name == "TreasuryAdded":
            print(f"  🏦 Treasury Added:")
            print(f"     Token Address: {args.get('tokenAddress')}")
            print(f"     Sender:        {args.get('sender')}")
            print(f"     Amount:        {args.get('amount')}")

        elif event_name == "NativeReceived":
            print(f"  💎 Native Received:")
            print(f"     Sender: {args.get('sender')}")
            print(f"     Amount: {args.get('amount')}")

        elif event_name == "CertificateParticipantAdded":
            print(f"  📜 Certificate Participant Added:")
            print(f"     ID:             {args.get('id')}")
            print(f"     Competition ID: {args.get('competitionId')}")
            print(f"     Participant:    {args.get('participant')}")

        elif event_name == "CertificateParticipantWinnerAdded":
            print(f"  🏅 Certificate Participant Winner Added:")
            print(f"     ID:             {args.get('id')}")
            print(f"     Competition ID: {args.get('competitionId')}")
            print(f"     Participant:    {args.get('participant')}")
            print(f"     Winner ID:      {args.get('winnerId')}")

        elif event_name == "CertificateParticipantMinted":
            print(f"  🎖️  Certificate Participant Minted:")
            print(f"     Token ID:       {args.get('tokenId')}")
            print(f"     Participant:    {args.get('participant')}")
            print(f"     Competition ID: {args.get('competitionId')}")
            print(f"     URI:            {args.get('uri')}")

        elif event_name == "CertificateParticipantWinnerMinted":
            print(f"  🏆 Certificate Participant Winner Minted:")
            print(f"     Token ID:       {args.get('tokenId')}")
            print(f"     Participant:    {args.get('participant')}")
            print(f"     Competition ID: {args.get('competitionId')}")
            print(f"     Winner ID:      {args.get('winnerId')}")
            print(f"     URI:            {args.get('uri')}")

        elif event_name == "Transfer":
            print(f"  ➡️  Transfer:")
            print(f"     From:     {args.get('from')}")
            print(f"     To:       {args.get('to')}")
            print(f"     Token ID: {args.get('tokenId')}")

        elif event_name == "Approval":
            print(f"  ✅ Approval:")
            print(f"     Owner:    {args.get('owner')}")
            print(f"     Approved: {args.get('approved')}")
            print(f"     Token ID: {args.get('tokenId')}")

        elif event_name == "ApprovalForAll":
            print(f"  ✅ Approval For All:")
            print(f"     Owner:    {args.get('owner')}")
            print(f"     Operator: {args.get('operator')}")
            print(f"     Approved: {args.get('approved')}")

        elif event_name == "MetadataUpdate":
            print(f"  📝 Metadata Update:")
            print(f"     Token ID: {args.get('_tokenId')}")

        elif event_name == "BatchMetadataUpdate":
            print(f"  📝 Batch Metadata Update:")
            print(f"     From Token ID: {args.get('_fromTokenId')}")
            print(f"     To Token ID:   {args.get('_toTokenId')}")

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
