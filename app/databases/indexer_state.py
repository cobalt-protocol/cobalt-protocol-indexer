import logging
from typing import Optional
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.configs import settings
from app.configs.database import AsyncSessionLocal
from app.models.indexer_state import IndexerStateModel

logger = logging.getLogger("web3_indexer")


class IndexerStateDatabases:
    @staticmethod
    async def get_state(
        contract_name: str,
        chain_id: Optional[int] = None,
        session: Optional[AsyncSession] = None,
    ) -> Optional[IndexerStateModel]:
        if chain_id is None:
            chain_id = settings.chain_id

        async def _impl(db: AsyncSession) -> Optional[IndexerStateModel]:
            statement = select(IndexerStateModel).where(
                IndexerStateModel.contract_name == contract_name,
                IndexerStateModel.chain_id == chain_id,
            )
            result = await db.exec(statement)
            return result.first()

        if session is not None:
            return await _impl(session)
        async with AsyncSessionLocal() as db:
            return await _impl(db)

    @staticmethod
    async def ensure_state_exists(
        db: AsyncSession,
        contract_name: str,
        chain_id: Optional[int] = None,
    ) -> IndexerStateModel:
        if chain_id is None:
            chain_id = settings.chain_id
        statement = select(IndexerStateModel).where(
            IndexerStateModel.contract_name == contract_name,
            IndexerStateModel.chain_id == chain_id,
        )
        result = await db.exec(statement)
        existing = result.first()
        if existing:
            return existing
        state = IndexerStateModel(
            contract_name=contract_name,
            chain_id=chain_id,
            last_scanned_block=0,
        )
        db.add(state)
        await db.commit()
        await db.refresh(state)
        return state

    @staticmethod
    async def ensure_state(
        contract_name: str,
        chain_id: Optional[int] = None,
        session: Optional[AsyncSession] = None,
    ) -> IndexerStateModel:
        if chain_id is None:
            chain_id = settings.chain_id

        async def _impl(db: AsyncSession) -> IndexerStateModel:
            return await IndexerStateDatabases.ensure_state_exists(
                db, contract_name, chain_id
            )

        if session is not None:
            return await _impl(session)
        async with AsyncSessionLocal() as db:
            return await _impl(db)

    @staticmethod
    async def resolve_indexer_state_id(
        db: AsyncSession,
        contract_name: str = "CompetitionManager",
        chain_id: Optional[int] = None,
    ) -> str:
        state = await IndexerStateDatabases.ensure_state_exists(
            db, contract_name, chain_id
        )
        return state.id

    @staticmethod
    async def get_or_create_indexer_state_id(
        contract_name: str = "CompetitionManager",
        chain_id: Optional[int] = None,
        session: Optional[AsyncSession] = None,
    ) -> str:
        state = await IndexerStateDatabases.ensure_state(
            contract_name, chain_id, session=session
        )
        return state.id

    @staticmethod
    async def get_last_scanned_block(
        contract_name: str,
        chain_id: Optional[int] = None,
        session: Optional[AsyncSession] = None,
    ) -> Optional[int]:
        if chain_id is None:
            chain_id = settings.chain_id

        async def _impl(db: AsyncSession) -> Optional[int]:
            statement = select(IndexerStateModel).where(
                IndexerStateModel.contract_name == contract_name,
                IndexerStateModel.chain_id == chain_id,
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
        chain_id: Optional[int] = None,
        session: Optional[AsyncSession] = None,
    ) -> Optional[IndexerStateModel]:
        if chain_id is None:
            chain_id = settings.chain_id

        async def _impl(db: AsyncSession) -> IndexerStateModel:
            statement = select(IndexerStateModel).where(
                IndexerStateModel.contract_name == contract_name,
                IndexerStateModel.chain_id == chain_id,
            )
            result = await db.exec(statement)
            existing = result.first()

            if existing:
                existing.last_scanned_block = last_scanned_block
                existing.chain_id = chain_id
                db.add(existing)
                await db.commit()
                await db.refresh(existing)
                return existing

            state = IndexerStateModel(
                contract_name=contract_name,
                chain_id=chain_id,
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
