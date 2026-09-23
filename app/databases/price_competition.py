from typing import Optional
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.configs.database import AsyncSessionLocal
from app.models.price_competition import PriceCompetitionModel


class PriceCompetitionDatabases:
    @staticmethod
    async def add_price_competition(
        tx_hash: str,
        price_competition_fee_id: int,
        treasury_fee: int,
        token_address: str,
        title: str,
        description: str,
        session: Optional[AsyncSession] = None,
    ) -> PriceCompetitionModel:
        async def _impl(db: AsyncSession) -> PriceCompetitionModel:
            statement = select(PriceCompetitionModel).where(
                PriceCompetitionModel.price_competition_fee_id == price_competition_fee_id
            )
            result = await db.exec(statement)
            existing = result.first()

            if existing:
                existing.tx_hash = tx_hash
                existing.treasury_fee = treasury_fee
                existing.token_address = token_address
                existing.title = title
                existing.description = description
                db.add(existing)
                await db.commit()
                await db.refresh(existing)
                return existing

            price_competition = PriceCompetitionModel(
                tx_hash=tx_hash,
                price_competition_fee_id=price_competition_fee_id,
                treasury_fee=treasury_fee,
                token_address=token_address,
                title=title,
                description=description,
            )
            db.add(price_competition)
            await db.commit()
            await db.refresh(price_competition)
            return price_competition

        if session is not None:
            return await _impl(session)
        else:
            async with AsyncSessionLocal() as db:
                return await _impl(db)
