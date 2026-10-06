from typing import Optional
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.configs.database import AsyncSessionLocal
from app.configs import settings
from app.models.certificate_participant_minted import CertificateParticipantMintedModel
from app.databases.competition import CompetitionDatabases


class CertificateParticipantMintedDatabases:
    @staticmethod
    async def add_certificate_participant_minted(
        tx_hash: str,
        token_id: int,
        participant: str,
        competition_id: str,
        uri: str,
        chain_id: Optional[int] = None,
        indexer_state_id: Optional[str] = None,
        contract_name: str = "CompetitionManager",
        session: Optional[AsyncSession] = None,
    ) -> CertificateParticipantMintedModel:
        if chain_id is None and indexer_state_id is None:
            chain_id = settings.chain_id

        async def _impl(db: AsyncSession) -> CertificateParticipantMintedModel:
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

            statement = select(CertificateParticipantMintedModel).where(
                CertificateParticipantMintedModel.token_id == token_id,
                CertificateParticipantMintedModel.indexer_state_id == resolved_state_id,
            )
            result = await db.exec(statement)
            existing = result.first()

            if existing:
                existing.tx_hash = tx_hash
                existing.participant = participant
                existing.competition_id = comp.id
                existing.uri = uri
                existing.indexer_state_id = resolved_state_id
                db.add(existing)
                await db.commit()
                await db.refresh(existing)
                return existing

            record = CertificateParticipantMintedModel(
                tx_hash=tx_hash,
                token_id=token_id,
                participant=participant,
                competition_id=comp.id,
                uri=uri,
                indexer_state_id=resolved_state_id,
            )
            db.add(record)
            await db.commit()
            await db.refresh(record)
            return record

        if session is not None:
            return await _impl(session)
        else:
            async with AsyncSessionLocal() as db:
                return await _impl(db)
