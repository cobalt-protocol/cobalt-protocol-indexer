from typing import Optional
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.configs.database import AsyncSessionLocal
from app.models.competition_fee_paid import CompetitionFeePaidModel
from app.databases.competition import CompetitionDatabases


class CompetitionFeePaidDatabases:
    @staticmethod
    async def add_competition_fee_paid(
        tx_hash: str,
        competition_id: str,
        payer: str,
        token_address: str,
        amount: int,
        session: Optional[AsyncSession] = None,
    ) -> CompetitionFeePaidModel:
        async def _impl(db: AsyncSession) -> CompetitionFeePaidModel:
            comp = await CompetitionDatabases.ensure_competition_exists(
                db, competition_id, tx_hash
            )

            statement = select(CompetitionFeePaidModel).where(
                CompetitionFeePaidModel.competition_id == comp.id
            )
            result = await db.exec(statement)
            existing = result.first()

            if existing:
                existing.tx_hash = tx_hash
                existing.payer = payer
                existing.token_address = token_address
                existing.amount = amount
                db.add(existing)
                await db.commit()
                await db.refresh(existing)
                return existing

            fee_paid = CompetitionFeePaidModel(
                tx_hash=tx_hash,
                competition_id=comp.id,
                payer=payer,
                token_address=token_address,
                amount=amount,
            )
            db.add(fee_paid)
            await db.commit()
            await db.refresh(fee_paid)
            return fee_paid

        if session is not None:
            return await _impl(session)
        else:
            async with AsyncSessionLocal() as db:
                return await _impl(db)
