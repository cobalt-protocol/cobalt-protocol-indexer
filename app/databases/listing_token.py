from typing import Optional
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.configs.database import AsyncSessionLocal
from app.configs import settings
from app.models.listing_token import ListingTokenModel


class ListingTokenDatabases:
    @staticmethod
    async def add_listing_token(
        tx_hash: str,
        listing_token_id: int,
        token_address: str,
        is_active: bool = True,
        chain_id: Optional[int] = None,
        indexer_state_id: Optional[str] = None,
        contract_name: str = "CompetitionManager",
        session: Optional[AsyncSession] = None,
    ) -> ListingTokenModel:
        if chain_id is None and indexer_state_id is None:
            chain_id = settings.chain_id

        async def _impl(db: AsyncSession) -> ListingTokenModel:
            # Resolve proper FK -> indexer_state.id instead of logical chain_id
            if indexer_state_id is not None:
                resolved_state_id = indexer_state_id
            else:
                from app.databases.indexer_state import IndexerStateDatabases

                resolved_state_id = await IndexerStateDatabases.resolve_indexer_state_id(
                    db, contract_name=contract_name, chain_id=chain_id
                )

            statement = select(ListingTokenModel).where(
                ListingTokenModel.listing_token_id == listing_token_id,
                ListingTokenModel.indexer_state_id == resolved_state_id,
            )
            result = await db.exec(statement)
            existing = result.first()

            if existing:
                existing.tx_hash = tx_hash
                existing.token_address = token_address
                existing.is_active = is_active
                existing.indexer_state_id = resolved_state_id
                db.add(existing)
                await db.commit()
                await db.refresh(existing)
                return existing

            listing_token = ListingTokenModel(
                tx_hash=tx_hash,
                listing_token_id=listing_token_id,
                token_address=token_address,
                is_active=is_active,
                indexer_state_id=resolved_state_id,
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
