from typing import Optional
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.configs.database import AsyncSessionLocal
from app.models.listing_token_prize import ListingTokenPrizeModel


class ListingTokenPrizeDatabases:
    @staticmethod
    async def add_listing_token_prize(
        tx_hash: str,
        listing_token_prize_id: int,
        token_address: str,
        is_active: bool = True,
        session: Optional[AsyncSession] = None,
    ) -> ListingTokenPrizeModel:
        async def _impl(db: AsyncSession) -> ListingTokenPrizeModel:
            statement = select(ListingTokenPrizeModel).where(
                ListingTokenPrizeModel.listing_token_prize_id == listing_token_prize_id
            )
            result = await db.exec(statement)
            existing = result.first()

            if existing:
                existing.tx_hash = tx_hash
                existing.token_address = token_address
                existing.is_active = is_active
                db.add(existing)
                await db.commit()
                await db.refresh(existing)
                return existing

            token_prize = ListingTokenPrizeModel(
                tx_hash=tx_hash,
                listing_token_prize_id=listing_token_prize_id,
                token_address=token_address,
                is_active=is_active,
            )
            db.add(token_prize)
            await db.commit()
            await db.refresh(token_prize)
            return token_prize

        if session is not None:
            return await _impl(session)
        else:
            async with AsyncSessionLocal() as db:
                return await _impl(db)
