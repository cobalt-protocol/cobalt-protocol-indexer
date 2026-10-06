from typing import Optional
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.configs.database import AsyncSessionLocal
from app.configs import settings
from app.models.prize_distributed import PrizeDistributedModel
from app.databases.competition import CompetitionDatabases


class PrizeDistributedDatabases:
    @staticmethod
    async def add_prize_distributed(
        tx_hash: str,
        treasury_prize_id: int,
        competition_id: str,
        token_address: str,
        recipient: str,
        amount: int,
        chain_id: Optional[int] = None,
        indexer_state_id: Optional[str] = None,
        contract_name: str = "CompetitionManager",
        session: Optional[AsyncSession] = None,
    ) -> PrizeDistributedModel:
        if chain_id is None and indexer_state_id is None:
            chain_id = settings.chain_id

        async def _impl(db: AsyncSession) -> PrizeDistributedModel:
            if indexer_state_id is not None:
                resolved_state_id = indexer_state_id
            else:
                from app.databases.indexer_state import IndexerStateDatabases

                resolved_state_id = await IndexerStateDatabases.resolve_indexer_state_id(
                    db, contract_name=contract_name, chain_id=chain_id
                )

            comp = await CompetitionDatabases.ensure_competition_exists(
                db,
                competition_id,
                tx_hash,
                chain_id=chain_id,
                indexer_state_id=resolved_state_id,
            )

            statement = select(PrizeDistributedModel).where(
                PrizeDistributedModel.treasury_prize_id == treasury_prize_id,
                PrizeDistributedModel.indexer_state_id == resolved_state_id,
            )
            result = await db.exec(statement)
            existing = result.first()

            if existing:
                existing.tx_hash = tx_hash
                existing.competition_id = comp.id
                existing.token_address = token_address
                existing.recipient = recipient
                existing.amount = amount
                existing.indexer_state_id = resolved_state_id
                db.add(existing)
                await db.commit()
                await db.refresh(existing)
                return existing

            prize_distributed = PrizeDistributedModel(
                tx_hash=tx_hash,
                treasury_prize_id=treasury_prize_id,
                competition_id=comp.id,
                token_address=token_address,
                recipient=recipient,
                amount=amount,
                indexer_state_id=resolved_state_id,
            )
            db.add(prize_distributed)
            await db.commit()
            await db.refresh(prize_distributed)
            return prize_distributed

        if session is not None:
            return await _impl(session)
        else:
            async with AsyncSessionLocal() as db:
                return await _impl(db)
