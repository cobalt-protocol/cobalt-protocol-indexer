from typing import Optional
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.configs.database import AsyncSessionLocal
from app.models.listing_token import ListingTokenModel


class ListingTokenDatabases:
    @staticmethod
    async def add_listing_token(
        tx_hash: str,
        listing_token_id: int,
        token_address: str,
        is_active: bool = True,
        session: Optional[AsyncSession] = None,
    ) -> ListingTokenModel:
        async def _impl(db: AsyncSession) -> ListingTokenModel:
            statement = select(ListingTokenModel).where(
                ListingTokenModel.listing_token_id == listing_token_id
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

            listing_token = ListingTokenModel(
                tx_hash=tx_hash,
                listing_token_id=listing_token_id,
                token_address=token_address,
                is_active=is_active,
            )
            db.add(listing_token)
            await db.commit()
            await db.refresh(listing_token)
            return listing_token

        if session is not None:
            return await _impl(session)
        else:
            async with AsyncSessionLocal() as db:
                return await _impl(db)
