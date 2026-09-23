from typing import Optional
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.configs.database import AsyncSessionLocal
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
        session: Optional[AsyncSession] = None,
    ) -> PrizeDistributedModel:
        async def _impl(db: AsyncSession) -> PrizeDistributedModel:
            comp = await CompetitionDatabases.ensure_competition_exists(
                db, competition_id, tx_hash
            )

            statement = select(PrizeDistributedModel).where(
                PrizeDistributedModel.treasury_prize_id == treasury_prize_id
            )
            result = await db.exec(statement)
            existing = result.first()

            if existing:
                existing.tx_hash = tx_hash
                existing.competition_id = comp.id
                existing.token_address = token_address
                existing.recipient = recipient
                existing.amount = amount
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
