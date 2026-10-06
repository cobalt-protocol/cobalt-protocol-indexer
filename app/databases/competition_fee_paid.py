from typing import Optional
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.configs.database import AsyncSessionLocal
from app.configs import settings
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
        chain_id: Optional[int] = None,
        indexer_state_id: Optional[str] = None,
        contract_name: str = "CompetitionManager",
        session: Optional[AsyncSession] = None,
    ) -> CompetitionFeePaidModel:
        if chain_id is None and indexer_state_id is None:
            chain_id = settings.chain_id

        async def _impl(db: AsyncSession) -> CompetitionFeePaidModel:
            # Resolve indexer_state.id FK inside same db session
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

            statement = select(CompetitionFeePaidModel).where(
                CompetitionFeePaidModel.competition_id == comp.id,
                CompetitionFeePaidModel.indexer_state_id == resolved_state_id,
            )
            result = await db.exec(statement)
            existing = result.first()

            if existing:
                existing.tx_hash = tx_hash
                existing.payer = payer
                existing.token_address = token_address
                existing.amount = amount
                existing.indexer_state_id = resolved_state_id
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
                indexer_state_id=resolved_state_id,
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
