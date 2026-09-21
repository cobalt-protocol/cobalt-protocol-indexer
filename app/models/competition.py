from datetime import datetime
from typing import Optional, List, TYPE_CHECKING
from sqlmodel import Field, SQLModel, Relationship
from sqlalchemy import Column, DateTime
from sqlalchemy.sql import func
from app.utils import generate_ulid

if TYPE_CHECKING:
    from app.models.prize_winner import PrizeWinnerModel
    from app.models.team import TeamModel
    from app.models.nonce_certificate_participant import (
        NonceCertificateParticipantModel,
    )
    from app.models.nonce_certificate_winner import (
        NonceCertificateWinnerModel,
    )


class CompetitionModel(SQLModel, table=True):
    __tablename__ = "competition"

    id: str = Field(default_factory=generate_ulid, primary_key=True)
    tx_hash: str = Field(unique=True)
    name: str
    category: str
    description: str
    requirement: str
    registration_window: datetime
    competition_window: datetime
    submission_deadline: datetime
    judging_review: datetime
    result_announcement: datetime
    pirze_certificate_claim: datetime
    certificate_cid: str
    guidebook_cid: str
    created_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(
            DateTime(timezone=True), server_default=func.now(), nullable=False
        ),
    )
    updated_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(
            DateTime(timezone=True),
            server_default=func.now(),
            onupdate=func.now(),
            nullable=True,
        ),
    )
    deleted_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
    )

    prize_winners: List["PrizeWinnerModel"] = Relationship(back_populates="competition")
    teams: List["TeamModel"] = Relationship(back_populates="competition")
    nonce_certificate_participant: Optional[
        "NonceCertificateParticipantModel"
    ] = Relationship(back_populates="competition")
    nonce_certificate_winner: Optional[
        "NonceCertificateWinnerModel"
    ] = Relationship(back_populates="competition")




