from typing import Optional
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.configs.database import AsyncSessionLocal
from app.models.participant_winner import ParticipantWinnerModel
from app.databases.competition import CompetitionDatabases


class ParticipantWinnerDatabases:
    @staticmethod
    async def add_participant_winner(
        tx_hash: str,
        winner_id: int,
        participant: str,
        competition_id: str,
        participant_winner_id: int,
        title: str,
        session: Optional[AsyncSession] = None,
    ) -> ParticipantWinnerModel:
        async def _impl(db: AsyncSession) -> ParticipantWinnerModel:
            comp = await CompetitionDatabases.ensure_competition_exists(
                db, competition_id, tx_hash
            )

            statement = select(ParticipantWinnerModel).where(
                ParticipantWinnerModel.winner_id == winner_id,
                ParticipantWinnerModel.competition_id == comp.id,
            )
            result = await db.exec(statement)
            existing = result.first()

            if existing:
                existing.tx_hash = tx_hash
                existing.participant = participant
                existing.participant_winner_id = participant_winner_id
                existing.title = title
                db.add(existing)
                await db.commit()
                await db.refresh(existing)
                return existing

            participant_winner = ParticipantWinnerModel(
                tx_hash=tx_hash,
                winner_id=winner_id,
                participant=participant,
                competition_id=comp.id,
                participant_winner_id=participant_winner_id,
                title=title,
            )
            db.add(participant_winner)
            await db.commit()
            await db.refresh(participant_winner)
            return participant_winner

        if session is not None:
            return await _impl(session)
        else:
            async with AsyncSessionLocal() as db:
                return await _impl(db)
