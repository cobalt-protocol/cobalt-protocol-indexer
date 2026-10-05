from datetime import datetime
from typing import Any, Dict, List, Optional
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlalchemy import func

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
        fee: Optional[int] = None,
        fee_token_address: Optional[str] = None,
        formation: str = "",
        price_competition_fee_id: Optional[int] = None,
        winners: Optional[List[Dict[str, Any]]] = None,
        session: Optional[AsyncSession] = None,
    ) -> CompetitionModel:
        async def _impl(db: AsyncSession) -> CompetitionModel:
            statement = select(UserModel).where(
                func.lower(UserModel.wallet_address) == (wallet_address.lower() if wallet_address else "")
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

            # Jangan assign ulang `fee_token_address` di dalam closure ini:
            # Python akan menganggapnya variabel lokal _impl sehingga memicu
            # UnboundLocalError. Gunakan nama lokal terpisah.
            # Catatan: fee_token_address = token pembayaran tim
            # (Competitions.payment.tokenAddress), BUKAN token platform fee
            # (PriceCompetitionFee.tokenAddress), jadi tidak ada fallback ke
            # price_comp.token_address. Nilainya diisi oleh event
            # CompetitionPaymentConfigured (emit sebelum CompetitionCreated).
            resolved_fee_token_address = fee_token_address or ""
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
                if fee is not None:
                    existing.fee = fee
                if resolved_fee_token_address:
                    existing.fee_token_address = resolved_fee_token_address
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
                    "fee": fee,
                    "fee_token_address": resolved_fee_token_address,
                    "price_competition_id": price_competition_id,
                    "competition_id": competition_id,
                }

                competition = CompetitionModel(**kwargs)
                db.add(competition)
                await db.commit()
                await db.refresh(competition)

            if winners:
                # Baris winner yang sudah dibuat oleh event
                # CompetitionWinnerConfigured (urut sesuai winnerId on-chain).
                ordered_stmt = (
                    select(PrizeWinnerModel)
                    .where(PrizeWinnerModel.competition_id == competition.id)
                    .order_by(PrizeWinnerModel.winner_id)
                )
                ordered_existing = list((await db.exec(ordered_stmt)).all())

                for idx, w in enumerate(winners):
                    if not isinstance(w, dict):
                        continue

                    cat = str(w.get("title") or w.get("category") or "")
                    cert = str(
                        w.get("certificateCID") or w.get("certificate_cid") or ""
                    )

                    # Winner dari metadata IPFS: hanya bawa title/certificate,
                    # prizeAmount di metadata dalam satuan token (bukan wei),
                    # jadi jangan menimpa amount on-chain. Cocokkan per urutan.
                    if w.get("_from_metadata"):
                        if idx < len(ordered_existing):
                            target = ordered_existing[idx]
                            if cat:
                                target.category = cat
                            if cert and not target.certificate_cid:
                                target.certificate_cid = cert
                            db.add(target)
                        continue

                    amt = int(w.get("prizeAmount") or w.get("amount") or 0)
                    raw_w_id = (
                        w.get("id")
                        if w.get("id") is not None
                        else w.get("winnerId")
                    )
                    w_id = int(raw_w_id) if raw_w_id is not None else 0

                    existing_pw = None
                    if w_id:
                        pw_stmt = select(PrizeWinnerModel).where(
                            PrizeWinnerModel.competition_id == competition.id,
                            PrizeWinnerModel.winner_id == w_id,
                        )
                        existing_pw = (await db.exec(pw_stmt)).first()
                    if not existing_pw:
                        pw_stmt = select(PrizeWinnerModel).where(
                            PrizeWinnerModel.competition_id == competition.id,
                            PrizeWinnerModel.category == cat,
                        )
                        existing_pw = (await db.exec(pw_stmt)).first()

                    if existing_pw:
                        existing_pw.amount = amt
                        existing_pw.certificate_cid = cert
                        if cat:
                            existing_pw.category = cat
                        if w_id:
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

    @staticmethod
    async def update_competition_payment(
        competition_id: str,
        fee_token_address: Optional[str] = None,
        fee: Optional[int] = None,
        tx_hash: str = "",
        session: Optional[AsyncSession] = None,
    ) -> CompetitionModel:
        async def _impl(db: AsyncSession) -> CompetitionModel:
            comp = await CompetitionDatabases.ensure_competition_exists(
                db, competition_id, tx_hash
            )
            if fee_token_address is not None:
                comp.fee_token_address = fee_token_address
            if fee is not None:
                comp.fee = fee
            db.add(comp)
            await db.commit()
            await db.refresh(comp)
            return comp

        if session is not None:
            return await _impl(session)
        async with AsyncSessionLocal() as db:
            return await _impl(db)

    @staticmethod
    async def configure_competition_winner(
        competition_id: str,
        winner_id: int,
        prize_amount: int = 0,
        certificate_cid: str = "",
        category: str = "",
        tx_hash: str = "",
        session: Optional[AsyncSession] = None,
    ) -> PrizeWinnerModel:
        async def _impl(db: AsyncSession) -> PrizeWinnerModel:
            comp = await CompetitionDatabases.ensure_competition_exists(
                db, competition_id, tx_hash
            )

            statement = select(PrizeWinnerModel).where(
                PrizeWinnerModel.competition_id == comp.id,
                PrizeWinnerModel.winner_id == winner_id,
            )
            result = await db.exec(statement)
            prize_winner = result.first()

            if prize_winner:
                prize_winner.amount = prize_amount
                if certificate_cid:
                    prize_winner.certificate_cid = certificate_cid
                if category:
                    prize_winner.category = category
                db.add(prize_winner)
            else:
                prize_winner = PrizeWinnerModel(
                    winner_id=winner_id,
                    category=category or f"Winner #{winner_id}",
                    amount=prize_amount,
                    certificate_cid=certificate_cid,
                    competition_id=comp.id,
                )
                db.add(prize_winner)

            await db.commit()
            await db.refresh(prize_winner)
            return prize_winner

        if session is not None:
            return await _impl(session)
        async with AsyncSessionLocal() as db:
            return await _impl(db)
