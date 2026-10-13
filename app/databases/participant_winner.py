from typing import Optional
from sqlalchemy import func
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession
from app.configs.database import AsyncSessionLocal
from app.configs import settings
from app.models.participant_winner import ParticipantWinnerModel
from app.models.user import UserModel
from app.databases.competition import CompetitionDatabases


class ParticipantWinnerDatabases:
    @staticmethod
    async def add_participant_winner(
        tx_hash: str,
        participant: str,
        competition_id: str,
        title: str,
        prize_winner_id: Optional[int] = None,
        # deprecated alias: winner_id == prize_winner_id (uint256 PrizeWinner.winner_id, global UNIQUE)
        winner_id: Optional[int] = None,
        chain_id: Optional[int] = None,
        indexer_state_id: Optional[str] = None,
        contract_name: str = "CompetitionManager",
        session: Optional[AsyncSession] = None,
    ) -> ParticipantWinnerModel:
        if chain_id is None and indexer_state_id is None:
            chain_id = settings.chain_id

        async def _impl(db: AsyncSession) -> ParticipantWinnerModel:
            if indexer_state_id is not None:
                resolved_state_id = indexer_state_id
            else:
                from app.databases.indexer_state import IndexerStateDatabases

                resolved_state_id = (
                    await IndexerStateDatabases.resolve_indexer_state_id(
                        db, contract_name=contract_name, chain_id=chain_id
                    )
                )

            comp = await CompetitionDatabases.ensure_competition_exists(
                db,
                competition_id,
                tx_hash,
                chain_id=chain_id,
                indexer_state_id=resolved_state_id,
            )

            # Ensure User exists for FK participant -> users.wallet_address (1:1 strict, @unique)
            # Normalize wallet for lookup (lower-case compare) but store as-is from event (checksummed)
            wallet = (participant or "").strip()
            if not wallet:
                raise ValueError("participant wallet_address is empty — FK to users.wallet_address requires non-empty value")
            # case-insensitive lookup (wallet_address uniqueness is logically case-insensitive for EVM)
            stmt_user = select(UserModel).where(
                func.lower(UserModel.wallet_address) == wallet.lower()
            )
            res_user = await db.exec(stmt_user)
            _u_first = res_user.first()
            _user = _u_first[0] if isinstance(_u_first, (tuple, list)) else _u_first
            if _user is None:
                _user = UserModel(wallet_address=wallet)
                db.add(_user)
                await db.flush()  # ensure FK target exists before inserting participant_winner
                # handle race: if flush fails due to concurrent insert, reload
                try:
                    await db.refresh(_user)
                except Exception:
                    res_retry = await db.exec(stmt_user)
                    _r = res_retry.first()
                    _user = _r[0] if isinstance(_r, (tuple, list)) else _r
            # Keep participant exactly as users.wallet_address value (use canonical stored value if differ by case)
            # Prefer stored lower-cased compare: keep event string but ensure it matches existing user's wallet_address case
            # If existing user's wallet_address differs in case, use stored value for FK consistency
            try:
                if _user is not None and getattr(_user, "wallet_address", None):
                    # if event wallet differs only by case, align to stored wallet_address for FK
                    if str(_user.wallet_address).lower() == wallet.lower() and str(_user.wallet_address) != wallet:
                        participant = str(_user.wallet_address)
            except Exception:
                pass

            # Normalize: winner_id is deprecated alias for prize_winner_id (uint256 -> prize_winner.winner_id @unique)
            if prize_winner_id is None and winner_id is not None:
                prize_winner_id = winner_id
            resolved_prize_winner_id: Optional[int] = None
            if prize_winner_id is not None:
                try:
                    resolved_prize_winner_id = int(prize_winner_id)
                except Exception:
                    resolved_prize_winner_id = prize_winner_id  # type: ignore

            # Optional verify prize_winner exists (global UNIQUE winner_id); keep title fallback if needed
            if resolved_prize_winner_id is not None:
                try:
                    from app.models.prize_winner import PrizeWinnerModel

                    pw_stmt = select(PrizeWinnerModel).where(
                        PrizeWinnerModel.winner_id == resolved_prize_winner_id
                    )
                    pw_res = await db.exec(pw_stmt)
                    _first = pw_res.first()
                    _pw = (
                        _first[0] if isinstance(_first, (tuple, list)) else _first
                    )
                    # if not found, keep resolved value — FK will enforce if DB has constraint
                    if _pw is not None and not title:
                        try:
                            if getattr(_pw, "category", None):
                                title = str(_pw.category)
                        except Exception:
                            pass
                except Exception:
                    pass

            # Dedup on (prize_winner_id BigInt FK -> prize_winner.winner_id, participant, competition, chain)
            # prize_winner_id is the 1:N join (one prize_winner : many participant_winner)
            if resolved_prize_winner_id is None:
                # No winner FK — dedup on participant+competition+chain only
                statement = select(ParticipantWinnerModel).where(
                    ParticipantWinnerModel.prize_winner_id.is_(None),  # type: ignore
                    ParticipantWinnerModel.participant == participant.lower()
                    if participant
                    else ParticipantWinnerModel.participant == participant,
                    ParticipantWinnerModel.competition_id == comp.id,
                    ParticipantWinnerModel.indexer_state_id == resolved_state_id,
                )
            else:
                statement = select(ParticipantWinnerModel).where(
                    ParticipantWinnerModel.prize_winner_id == resolved_prize_winner_id,
                    ParticipantWinnerModel.participant == participant.lower()
                    if participant
                    else ParticipantWinnerModel.participant == participant,
                    ParticipantWinnerModel.competition_id == comp.id,
                    ParticipantWinnerModel.indexer_state_id == resolved_state_id,
                )
            result = await db.exec(statement)
            _existing_first = result.first()
            existing = (
                _existing_first[0]
                if isinstance(_existing_first, (tuple, list))
                else _existing_first
            )

            if existing:
                existing.tx_hash = tx_hash
                existing.participant = participant
                existing.title = title
                if resolved_prize_winner_id is not None:
                    existing.prize_winner_id = resolved_prize_winner_id
                existing.indexer_state_id = resolved_state_id
                db.add(existing)
                await db.commit()
                await db.refresh(existing)
                return existing

            participant_winner = ParticipantWinnerModel(
                tx_hash=tx_hash,
                participant=participant,
                competition_id=comp.id,
                title=title,
                prize_winner_id=resolved_prize_winner_id,
                indexer_state_id=resolved_state_id,
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
