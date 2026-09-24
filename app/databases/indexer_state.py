import logging
from typing import Optional
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.configs.database import AsyncSessionLocal
from app.models.indexer_state import IndexerStateModel

logger = logging.getLogger("web3_indexer")


class IndexerStateDatabases:
    @staticmethod
    async def get_last_scanned_block(
        contract_name: str, session: Optional[AsyncSession] = None
    ) -> Optional[int]:
        async def _impl(db: AsyncSession) -> Optional[int]:
            statement = select(IndexerStateModel).where(
                IndexerStateModel.contract_name == contract_name
            )
            result = await db.exec(statement)
            state = result.first()
            return state.last_scanned_block if state else None

        try:
            if session is not None:
                return await _impl(session)
            else:
                async with AsyncSessionLocal() as db:
                    return await _impl(db)
        except Exception as e:
            logger.error(f"Error fetching indexer state for {contract_name}: {e}")
            return None

    @staticmethod
    async def set_last_scanned_block(
        contract_name: str,
        last_scanned_block: int,
        session: Optional[AsyncSession] = None,
    ) -> Optional[IndexerStateModel]:
        async def _impl(db: AsyncSession) -> IndexerStateModel:
            statement = select(IndexerStateModel).where(
                IndexerStateModel.contract_name == contract_name
            )
            result = await db.exec(statement)
            existing = result.first()

            if existing:
                existing.last_scanned_block = last_scanned_block
                db.add(existing)
                await db.commit()
                await db.refresh(existing)
                return existing

            state = IndexerStateModel(
                contract_name=contract_name,
                last_scanned_block=last_scanned_block,
            )
            db.add(state)
            await db.commit()
            await db.refresh(state)
            return state

        try:
            if session is not None:
                return await _impl(session)
            else:
                async with AsyncSessionLocal() as db:
                    return await _impl(db)
        except Exception as e:
            logger.error(
                f"Error saving indexer state for {contract_name} block {last_scanned_block}: {e}"
            )
            return None
