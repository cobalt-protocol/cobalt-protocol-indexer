from typing import Optional
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.configs.database import AsyncSessionLocal
from app.models.certificate_participant_winner_minted import (
    CertificateParticipantWinnerMintedModel,
)
from app.databases.competition import CompetitionDatabases


class CertificateParticipantWinnerMintedDatabases:
    @staticmethod
    async def add_certificate_participant_winner_minted(
        tx_hash: str,
        token_id: int,
        participant: str,
        competition_id: str,
        winner_id: int,
        uri: str,
        session: Optional[AsyncSession] = None,
    ) -> CertificateParticipantWinnerMintedModel:
        async def _impl(db: AsyncSession) -> CertificateParticipantWinnerMintedModel:
            comp = await CompetitionDatabases.ensure_competition_exists(
                db, competition_id, tx_hash
            )

            statement = select(CertificateParticipantWinnerMintedModel).where(
                CertificateParticipantWinnerMintedModel.token_id == token_id
            )
            result = await db.exec(statement)
            existing = result.first()

            if existing:
                existing.tx_hash = tx_hash
                existing.participant = participant
                existing.competition_id = comp.id
                existing.winner_id = winner_id
                existing.uri = uri
                db.add(existing)
                await db.commit()
                await db.refresh(existing)
                return existing

            record = CertificateParticipantWinnerMintedModel(
                tx_hash=tx_hash,
                token_id=token_id,
                participant=participant,
                competition_id=comp.id,
                winner_id=winner_id,
                uri=uri,
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
