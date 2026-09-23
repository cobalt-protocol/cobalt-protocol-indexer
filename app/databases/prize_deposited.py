from typing import Optional
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.configs.database import AsyncSessionLocal
from app.models.prize_deposited import PrizeDepositedModel
from app.databases.competition import CompetitionDatabases


class PrizeDepositedDatabases:
    @staticmethod
    async def add_prize_deposited(
        tx_hash: str,
        treasury_prize_id: int,
        competition_id: str,
        token_address: str,
        sender: str,
        amount: int,
        session: Optional[AsyncSession] = None,
    ) -> PrizeDepositedModel:
        async def _impl(db: AsyncSession) -> PrizeDepositedModel:
            comp = await CompetitionDatabases.ensure_competition_exists(
                db, competition_id, tx_hash
            )

            statement = select(PrizeDepositedModel).where(
                PrizeDepositedModel.treasury_prize_id == treasury_prize_id
            )
            result = await db.exec(statement)
            existing = result.first()

            if existing:
                existing.tx_hash = tx_hash
                existing.competition_id = comp.id
                existing.token_address = token_address
                existing.sender = sender
                existing.amount = amount
                db.add(existing)
                await db.commit()
                await db.refresh(existing)
                return existing

            prize_deposited = PrizeDepositedModel(
                tx_hash=tx_hash,
                treasury_prize_id=treasury_prize_id,
                competition_id=comp.id,
                token_address=token_address,
                sender=sender,
                amount=amount,
            )
            db.add(prize_deposited)
            await db.commit()
            await db.refresh(prize_deposited)
            return prize_deposited

        if session is not None:
            return await _impl(session)
        else:
            async with AsyncSessionLocal() as db:
                return await _impl(db)
