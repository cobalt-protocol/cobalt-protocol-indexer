from datetime import datetime
from typing import Optional, List, TYPE_CHECKING
from sqlmodel import Field, SQLModel, Relationship
from sqlalchemy import Column, DateTime
from sqlalchemy.sql import func
from app.utils import generate_ulid

if TYPE_CHECKING:
    from app.models.user import UserModel
    from app.models.prize_winner import PrizeWinnerModel
    from app.models.team import TeamModel
    from app.models.nonce_certificate_participant import (
        NonceCertificateParticipantModel,
    )
    from app.models.nonce_certificate_winner import (
        NonceCertificateWinnerModel,
    )
    from app.models.prize_deposited import PrizeDepositedModel
    from app.models.price_competition import PriceCompetitionModel
    from app.models.competition_fee_paid import CompetitionFeePaidModel
    from app.models.participant_winner import ParticipantWinnerModel
    from app.models.prize_distributed import PrizeDistributedModel
    from app.models.certificate_participant_minted import (
        CertificateParticipantMintedModel,
    )
    from app.models.certificate_participant_winner_minted import (
        CertificateParticipantWinnerMintedModel,
    )


class CompetitionModel(SQLModel, table=True):
    __tablename__ = "competition"

    id: str = Field(default_factory=generate_ulid, primary_key=True)
    tx_hash: str = Field(unique=True)
    name: str
    category: str
    description: str
    requirement: str
    formation: str
    registration_window: datetime = Field(
        sa_column=Column(DateTime(timezone=True), nullable=False)
    )
    competition_window: datetime = Field(
        sa_column=Column(DateTime(timezone=True), nullable=False)
    )
    submission_deadline: datetime = Field(
        sa_column=Column(DateTime(timezone=True), nullable=False)
    )
    judging_review: datetime = Field(
        sa_column=Column(DateTime(timezone=True), nullable=False)
    )
    result_announcement: datetime = Field(
        sa_column=Column(DateTime(timezone=True), nullable=False)
    )
    pirze_certificate_claim: datetime = Field(
        sa_column=Column(DateTime(timezone=True), nullable=False)
    )
    certificate_cid: str
    guidebook_cid: str
    token_address: str
    user_id: Optional[str] = Field(
        default=None, foreign_key="users.id"
    )
    price_competition_id: Optional[str] = Field(
        default=None, foreign_key="price_competition.id"
    )
    competition_id: str
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
    user: Optional["UserModel"] = Relationship(back_populates="competitions")
    teams: List["TeamModel"] = Relationship(back_populates="competition")
    nonce_certificate_participant: Optional["NonceCertificateParticipantModel"] = (
        Relationship(back_populates="competition")
    )
    nonce_certificate_winner: Optional["NonceCertificateWinnerModel"] = Relationship(
        back_populates="competition"
    )
    prize_deposits: List["PrizeDepositedModel"] = Relationship(
        back_populates="competition"
    )
    price_competition: Optional["PriceCompetitionModel"] = Relationship(
        back_populates="competitions"
    )
    competition_fee_paid: Optional["CompetitionFeePaidModel"] = Relationship(
        back_populates="competition"
    )
    participant_winners: List["ParticipantWinnerModel"] = Relationship(
        back_populates="competition"
    )
    prize_distributions: List["PrizeDistributedModel"] = Relationship(
        back_populates="competition"
    )
    certificate_participant_minted: List["CertificateParticipantMintedModel"] = (
        Relationship(back_populates="competition")
    )
    certificate_participant_winner_minted: List[
        "CertificateParticipantWinnerMintedModel"
    ] = Relationship(back_populates="competition")
