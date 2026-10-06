from typing import Optional
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.configs.database import AsyncSessionLocal
from app.configs import settings
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
        chain_id: Optional[int] = None,
        indexer_state_id: Optional[str] = None,
        contract_name: str = "CompetitionManager",
        session: Optional[AsyncSession] = None,
    ) -> PriceCompetitionModel:
        if chain_id is None and indexer_state_id is None:
            chain_id = settings.chain_id

        async def _impl(db: AsyncSession) -> PriceCompetitionModel:
            if indexer_state_id is not None:
                resolved_state_id = indexer_state_id
            else:
                from app.databases.indexer_state import IndexerStateDatabases

                resolved_state_id = await IndexerStateDatabases.resolve_indexer_state_id(
                    db, contract_name=contract_name, chain_id=chain_id
                )

            statement = select(PriceCompetitionModel).where(
                PriceCompetitionModel.price_competition_fee_id
                == price_competition_fee_id,
                PriceCompetitionModel.indexer_state_id == resolved_state_id,
            )
            result = await db.exec(statement)
            existing = result.first()

            if existing:
                existing.tx_hash = tx_hash
                existing.treasury_fee = treasury_fee
                existing.token_address = token_address
                existing.title = title
                existing.description = description
                existing.indexer_state_id = resolved_state_id
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
                indexer_state_id=resolved_state_id,
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
