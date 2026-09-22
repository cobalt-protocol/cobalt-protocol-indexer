from datetime import datetime
from typing import Optional
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.configs.database import AsyncSessionLocal
from app.models.user import UserModel
from app.models.competition import CompetitionModel
from app.models.organization import OrganizationModel


class CompetitionDatabases:
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

            competition = CompetitionModel(
                tx_hash=tx_hash,
                name=name,
                category=category,
                description=description,
                requirement=requirement,
                registration_window=registration_window,
                competition_window=competition_window,
                submission_deadline=submission_deadline,
                judging_review=judging_review,
                result_announcement=result_announcement,
                pirze_certificate_claim=pirze_certificate_claim,
                certificate_cid=certificate_cid,
                guidebook_cid=guidebook_cid,
            )
            db.add(competition)
            await db.commit()
            await db.refresh(competition)
            return competition

        if session is not None:
            return await _impl(session)
        else:
            async with AsyncSessionLocal() as db:
                return await _impl(db)
