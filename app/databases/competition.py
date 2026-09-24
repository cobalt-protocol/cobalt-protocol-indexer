from datetime import datetime
from typing import Any, Dict, List, Optional
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.configs.database import AsyncSessionLocal
from app.models.user import UserModel
from app.models.competition import CompetitionModel
from app.models.organization import OrganizationModel
from app.models.prize_winner import PrizeWinnerModel
from app.models.price_competition import PriceCompetitionModel


class CompetitionDatabases:
    @staticmethod
    async def ensure_competition_exists(
        db: AsyncSession,
        competition_id: str,
        tx_hash: str,
    ) -> CompetitionModel:
        if tx_hash:
            statement = select(CompetitionModel).where(
                CompetitionModel.tx_hash == tx_hash
            )
            result = await db.exec(statement)
            comp = result.first()
            if comp:
                if competition_id and not comp.competition_id:
                    comp.competition_id = competition_id
                    db.add(comp)
                    await db.commit()
                    await db.refresh(comp)
                return comp

        if competition_id:
            statement = select(CompetitionModel).where(
                (CompetitionModel.competition_id == competition_id)
                | (CompetitionModel.id == competition_id)
            )
            result = await db.exec(statement)
            comp = result.first()
            if comp:
                return comp

        now = datetime.now()
        kwargs = {
            "tx_hash": tx_hash,
            "name": "",
            "category": "",
            "description": "",
            "requirement": "",
            "formation": "",
            "registration_window": now,
            "competition_window": now,
            "submission_deadline": now,
            "judging_review": now,
            "result_announcement": now,
            "pirze_certificate_claim": now,
            "certificate_cid": "",
            "guidebook_cid": "",
            "token_address": "",
            "competition_id": competition_id,
        }

        stub = CompetitionModel(**kwargs)
        db.add(stub)
        await db.commit()
        await db.refresh(stub)
        return stub

    @staticmethod
    async def add_competition(
        wallet_address: str,
        tx_hash: str,
        name: str,
        category: str,
        description: str,
        requirement: str,
        registration_window: datetime,
        competition_window: datetime,
        submission_deadline: datetime,
        judging_review: datetime,
        result_announcement: datetime,
        pirze_certificate_claim: datetime,
        certificate_cid: str,
        guidebook_cid: str,
        competition_id: str,
        formation: str = "",
        price_competition_fee_id: Optional[int] = None,
        winners: Optional[List[Dict[str, Any]]] = None,
        session: Optional[AsyncSession] = None,
    ) -> CompetitionModel:
        async def _impl(db: AsyncSession) -> CompetitionModel:
            statement = select(UserModel).where(
                UserModel.wallet_address == wallet_address
            )
            result = await db.exec(statement)
            user = result.first()

            if not user:
                user = UserModel(wallet_address=wallet_address)
                db.add(user)
                await db.commit()
                await db.refresh(user)

            org_statement = select(OrganizationModel).where(
                OrganizationModel.user_id == user.id
            )
            org_result = await db.exec(org_statement)
            organization = org_result.first()

            if not organization:
                organization = OrganizationModel(
                    tx_hash=tx_hash,
                    user_id=user.id,
                )
                db.add(organization)
                await db.commit()
                await db.refresh(organization)

            token_address = ""
            price_competition_id = None
            if price_competition_fee_id is not None:
                price_comp_stmt = select(PriceCompetitionModel).where(
                    PriceCompetitionModel.price_competition_fee_id
                    == price_competition_fee_id
                )
                price_comp_result = await db.exec(price_comp_stmt)
                price_comp = price_comp_result.first()
                if price_comp:
                    price_competition_id = price_comp.id
                    if price_comp.token_address:
                        token_address = price_comp.token_address

            existing = None
            if tx_hash:
                statement = select(CompetitionModel).where(
                    CompetitionModel.tx_hash == tx_hash
                )
                result = await db.exec(statement)
                existing = result.first()

            if not existing and competition_id:
                statement = select(CompetitionModel).where(
                    (CompetitionModel.competition_id == competition_id)
                    | (CompetitionModel.id == competition_id)
                )
                result = await db.exec(statement)
                existing = result.first()

            if existing:
                existing.tx_hash = tx_hash
                existing.user_id = user.id
                existing.name = name
                existing.category = category
                existing.description = description
                existing.requirement = requirement
                existing.formation = formation
                existing.registration_window = registration_window
                existing.competition_window = competition_window
                existing.submission_deadline = submission_deadline
                existing.judging_review = judging_review
                existing.result_announcement = result_announcement
                existing.pirze_certificate_claim = pirze_certificate_claim
                existing.certificate_cid = certificate_cid
                existing.guidebook_cid = guidebook_cid
                if token_address:
                    existing.token_address = token_address
                if price_competition_id is not None:
                    existing.price_competition_id = price_competition_id
                if competition_id is not None:
                    existing.competition_id = competition_id

                db.add(existing)
                await db.commit()
                await db.refresh(existing)
                competition = existing
            else:
                kwargs = {
                    "tx_hash": tx_hash,
                    "user_id": user.id,
                    "name": name,
                    "category": category,
                    "description": description,
                    "requirement": requirement,
                    "formation": formation,
                    "registration_window": registration_window,
                    "competition_window": competition_window,
                    "submission_deadline": submission_deadline,
                    "judging_review": judging_review,
                    "result_announcement": result_announcement,
                    "pirze_certificate_claim": pirze_certificate_claim,
                    "certificate_cid": certificate_cid,
                    "guidebook_cid": guidebook_cid,
                    "token_address": token_address,
                    "price_competition_id": price_competition_id,
                    "competition_id": competition_id,
                }

                competition = CompetitionModel(**kwargs)
                db.add(competition)
                await db.commit()
                await db.refresh(competition)

            if winners:
                for w in winners:
                    if isinstance(w, dict):
                        cat = str(w.get("title") or w.get("category") or "")
                        amt = int(w.get("prizeAmount") or w.get("amount") or 0)
                        cert = str(
                            w.get("certificateCID") or w.get("certificate_cid") or ""
                        )
                        raw_w_id = (
                            w.get("id")
                            if w.get("id") is not None
                            else w.get("winnerId")
                        )
                        w_id = int(raw_w_id) if raw_w_id is not None else 0

                        pw_stmt = select(PrizeWinnerModel).where(
                            PrizeWinnerModel.competition_id == competition.id,
                            PrizeWinnerModel.category == cat,
                        )
                        pw_res = await db.exec(pw_stmt)
                        existing_pw = pw_res.first()
                        if existing_pw:
                            existing_pw.amount = amt
                            existing_pw.certificate_cid = cert
                            if w_id is not None:
                                existing_pw.winner_id = w_id
                            db.add(existing_pw)
                        else:
                            prize_winner = PrizeWinnerModel(
                                winner_id=w_id,
                                category=cat,
                                amount=amt,
                                certificate_cid=cert,
                                competition_id=competition.id,
                            )
                            db.add(prize_winner)
                await db.commit()
                await db.refresh(competition)

            return competition

        if session is not None:
            return await _impl(session)
        else:
            async with AsyncSessionLocal() as db:
                return await _impl(db)
