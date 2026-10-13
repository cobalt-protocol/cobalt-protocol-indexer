from typing import Optional
from eth_utils import keccak
from sqlalchemy import func
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.configs.database import AsyncSessionLocal
from app.configs import settings
from app.models.certificate_participant_winner_minted import (
    CertificateParticipantWinnerMintedModel,
)
from app.models.user import UserModel
from app.models.team import TeamModel
from app.databases.competition import CompetitionDatabases


def _derive_numeric_team_id(team_id_str: str) -> int:
    try:
        n = int(str(team_id_str).strip())
        if n > 0:
            return n
        raise ValueError("non-positive")
    except Exception:
        h = keccak(text=str(team_id_str))
        n = int.from_bytes(h, "big")
        return n if n != 0 else 1


class CertificateParticipantWinnerMintedDatabases:
    @staticmethod
    async def add_certificate_participant_winner_minted(
        tx_hash: str,
        token_id: int,
        participant: str,
        competition_id: str,
        winner_id: int,
        uri: str,
        team_id: Optional[int] = None,
        raw_team_id: Optional[str] = None,
        chain_id: Optional[int] = None,
        indexer_state_id: Optional[str] = None,
        contract_name: str = "CompetitionManager",
        session: Optional[AsyncSession] = None,
    ) -> CertificateParticipantWinnerMintedModel:
        if chain_id is None and indexer_state_id is None:
            chain_id = settings.chain_id

        async def _impl(db: AsyncSession) -> CertificateParticipantWinnerMintedModel:
            if indexer_state_id is not None:
                resolved_state_id = indexer_state_id
            else:
                from app.databases.indexer_state import IndexerStateDatabases

                resolved_state_id = await IndexerStateDatabases.resolve_indexer_state_id(
                    db, contract_name=contract_name, chain_id=chain_id
                )

            # Resolve user_id from participant wallet (case-insensitive); create placeholder user if missing
            resolved_user_id: Optional[str] = None
            wallet = (participant or "").strip()
            if wallet:
                stmt = select(UserModel).where(
                    func.lower(UserModel.wallet_address) == wallet.lower()
                )
                res = await db.exec(stmt)
                user = res.first()
                if not user:
                    user = UserModel(wallet_address=wallet)
                    db.add(user)
                    await db.commit()
                    await db.refresh(user)
                resolved_user_id = user.id

            comp = await CompetitionDatabases.ensure_competition_exists(
                db,
                competition_id,
                tx_hash,
                chain_id=chain_id,
                indexer_state_id=resolved_state_id,
            )

            # ── Resolve team_id FK (numeric on-chain teamId -> Team ULID) ──────────
            resolved_team_id: Optional[str] = None
            numeric_team_id: Optional[int] = None
            if team_id is not None:
                try:
                    numeric_team_id = int(team_id)
                except Exception:
                    numeric_team_id = None
            if numeric_team_id is None and raw_team_id is not None:
                try:
                    if str(raw_team_id).strip().isdigit():
                        numeric_team_id = int(str(raw_team_id).strip())
                    else:
                        stmt_direct = select(TeamModel).where(TeamModel.id == str(raw_team_id).strip())
                        r_direct = await db.exec(stmt_direct)
                        first_direct = r_direct.first()
                        direct_team = first_direct[0] if isinstance(first_direct, (tuple, list)) else first_direct
                        if direct_team is not None:
                            resolved_team_id = getattr(direct_team, "id", None)
                except Exception:
                    pass
            if resolved_team_id is None and numeric_team_id is not None and numeric_team_id != 0:
                try:
                    stmt_team = select(TeamModel).where(TeamModel.competition_id == comp.id)
                    res_team = await db.exec(stmt_team)
                    rows = res_team.all()
                    for row in rows:
                        t = row[0] if isinstance(row, (tuple, list)) else row
                        if t is None:
                            continue
                        tid_str = getattr(t, "id", "") or ""
                        try:
                            derived = _derive_numeric_team_id(tid_str)
                            if derived == numeric_team_id:
                                resolved_team_id = tid_str
                                break
                        except Exception:
                            continue
                    if resolved_team_id is None:
                        for row in rows:
                            t = row[0] if isinstance(row, (tuple, list)) else row
                            if t is None:
                                continue
                            tid_str = getattr(t, "id", "") or ""
                            if tid_str.isdigit() and int(tid_str) == numeric_team_id:
                                resolved_team_id = tid_str
                                break
                except Exception:
                    pass

            statement = select(CertificateParticipantWinnerMintedModel).where(
                CertificateParticipantWinnerMintedModel.token_id == token_id,
                CertificateParticipantWinnerMintedModel.indexer_state_id == resolved_state_id,
            )
            result = await db.exec(statement)
            existing = result.first()

            if existing:
                existing.tx_hash = tx_hash
                existing.competition_id = comp.id
                existing.winner_id = winner_id
                existing.uri = uri
                existing.indexer_state_id = resolved_state_id
                if resolved_user_id is not None:
                    existing.user_id = resolved_user_id
                if resolved_team_id is not None:
                    existing.team_id = resolved_team_id
                db.add(existing)
                await db.commit()
                await db.refresh(existing)
                return existing

            record = CertificateParticipantWinnerMintedModel(
                tx_hash=tx_hash,
                token_id=token_id,
                competition_id=comp.id,
                team_id=resolved_team_id,
                winner_id=winner_id,
                uri=uri,
                user_id=resolved_user_id,
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
