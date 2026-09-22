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
                await self._process_log(cfg, log)

            self.last_scanned_blocks[name] = to_block
            self.last_updated_at[name] = datetime.now(timezone.utc).isoformat()

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

            if event_name == "CompetitionCreated":
                await self._handle_competition_created(tx_hash, cleaned_args)

        except Exception as e:
            logger.error(f"Error processing log {tx_hash}:{log_index}: {e}")

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

            wallet_address = args.get("organization") or comp.get("organization") or ""
            name = comp.get("name", "")
            category = comp.get("category", "")
            description = comp.get("description", "")
            requirement = comp.get("requirements", "")
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

            saved_comp = await CompetitionDatabases.add_competition(
                wallet_address=wallet_address,
                tx_hash=tx_hash,
                name=name,
                category=category,
                description=description,
                requirement=requirement,
                registration_window=registration_window,
                competition_window=competition_window,
                submission_deadline=submission_deadline,
                judging_review=judging_review,
                result_announcement=result_announcement,
                pirze_certificate_claim=pirze_certificate_claim,
                certificate_cid=certificate_cid,
                guidebook_cid=guidebook_cid,
            )
            logger.info(
                f"Successfully saved Competition to DB with ID: {saved_comp.id} (tx: {tx_hash})"
            )
        except Exception as e:
            logger.error(
                f"Failed to save CompetitionCreated event to DB (tx: {tx_hash}): {e}"
            )

    def _print_event_details(self, event_name: str, args: Dict[str, Any]):
        if event_name == "OwnershipTransferred":
            print(f"  🔑 Ownership Transferred:")
            print(f"     Previous Owner: {args.get('previousOwner')}")
            print(f"     New Owner:      {args.get('newOwner')}")

        elif event_name == "OwnerUpdated":
            print(f"  🔑 Owner Updated:")
            print(
                f"     Address Owner:  {args.get('addressOwner') or args.get('newOwner')}"
            )

        elif event_name == "CompetitionCreated":
            comp = (
                args.get("competition")
                if isinstance(args.get("competition"), dict)
                else {}
            )
            sched = (
                comp.get("schedule") if isinstance(comp.get("schedule"), dict) else {}
            )
            print(f"  🏆 Competition Created:")
            print(f"     ID:                      {args.get('id') or comp.get('id')}")
            print(
                f"     Creator Wallet (Org):    {args.get('organization') or comp.get('organization')}"
            )
            print(f"     Name:                    {comp.get('name')}")
            print(f"     Category:                {comp.get('category')}")
            print(f"     Description:             {comp.get('description')}")
            print(f"     Requirements:            {comp.get('requirements')}")
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

        elif event_name == "CompetitionFeePaid":
            print(f"  💳 Competition Fee Paid:")
            print(f"     Competition ID: {args.get('competitionId')}")
            print(f"     Payer:          {args.get('payer')}")
            print(f"     Token Address:  {args.get('tokenAddress')}")
            print(f"     Amount:         {args.get('amount')}")

        elif event_name == "WinnerSet":
            print(f"  🥇 Winner Set:")
            print(f"     Winner ID:             {args.get('winnerId')}")
            print(f"     Participant:           {args.get('participant')}")
            print(f"     Competition ID:        {args.get('competitionId')}")
            print(f"     Participant Winner ID: {args.get('participantWinnerId')}")
            print(f"     Title:                 {args.get('title')}")

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

        elif event_name == "PriceCompetitionFeeSet":
            print(f"  💰 Price Competition Fee Set:")
            print(f"     ID:            {args.get('id')}")
            print(f"     Treasury Fee:  {args.get('treasuryFee')}")
            print(f"     Token Address: {args.get('tokenAddress')}")
            print(f"     Title:         {args.get('title')}")
            print(f"     Description:   {args.get('description')}")

        elif event_name == "PriceCompetitionFeeUpdated":
            print(f"  🔄 Price Competition Fee Updated:")
            print(f"     ID:            {args.get('id')}")
            print(f"     Treasury Fee:  {args.get('treasuryFee')}")
            print(f"     Token Address: {args.get('tokenAddress')}")
            print(f"     Title:         {args.get('title')}")
            print(f"     Description:   {args.get('description')}")

        elif event_name == "SignerAddressUpdated":
            print(f"  ✍️  Signer Address Updated:")
            print(f"     Signer Address: {args.get('signerAddress')}")

        elif event_name == "TreasuryAdded":
            print(f"  🏦 Treasury Added:")
            print(f"     Token Address: {args.get('tokenAddress')}")
            print(f"     Sender:        {args.get('sender')}")
            print(f"     Amount:        {args.get('amount')}")

        elif event_name == "PrizeDeposited":
            print(f"  💰 Prize Deposited:")
            print(f"     Treasury Prize ID: {args.get('treasuryPrizeId')}")
            print(f"     Competition ID:    {args.get('competitionId')}")
            print(f"     Token Address:     {args.get('tokenAddress')}")
            print(f"     Sender:            {args.get('sender')}")
            print(f"     Amount:            {args.get('amount')}")

        elif event_name == "PrizeDistributed":
            print(f"  🎁 Prize Distributed:")
            print(f"     Treasury Prize ID: {args.get('treasuryPrizeId')}")
            print(f"     Competition ID:    {args.get('competitionId')}")
            print(f"     Token Address:     {args.get('tokenAddress')}")
            print(f"     Recipient:         {args.get('recipient')}")
            print(f"     Amount:            {args.get('amount')}")

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
