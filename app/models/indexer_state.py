from datetime import datetime
from typing import Optional, List, TYPE_CHECKING
from sqlmodel import Field, SQLModel, Relationship
from sqlalchemy import Column, DateTime, UniqueConstraint
from sqlalchemy.sql import func
from app.utils import generate_ulid

if TYPE_CHECKING:
    from app.models.competition import CompetitionModel
    from app.models.listing_token import ListingTokenModel
    from app.models.price_competition import PriceCompetitionModel
    from app.models.prize_deposited import PrizeDepositedModel
    from app.models.prize_distributed import PrizeDistributedModel
    from app.models.competition_fee_paid import CompetitionFeePaidModel
    from app.models.participant_winner import ParticipantWinnerModel
    from app.models.certificate_participant_minted import (
        CertificateParticipantMintedModel,
    )
    from app.models.certificate_participant_winner_minted import (
        CertificateParticipantWinnerMintedModel,
    )
    from app.models.signature_certificate_participant import (
        SignatureCertificateParticipantModel,
    )
    from app.models.signature_certificate_winner import SignatureCertificateWinnerModel


class IndexerStateModel(SQLModel, table=True):
    __tablename__ = "indexer_state"
    __table_args__ = (UniqueConstraint("contract_name", "chain_id"),)

    id: str = Field(default_factory=generate_ulid, primary_key=True)
    contract_name: str = Field(index=True)
    chain_id: int
    last_scanned_block: int
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

    # One-to-many via indexer_state.id (proper FK)
    competitions: List["CompetitionModel"] = Relationship(
        back_populates="indexer_state"
    )
    listing_tokens: List["ListingTokenModel"] = Relationship(
        back_populates="indexer_state"
    )
    price_competitions: List["PriceCompetitionModel"] = Relationship(
        back_populates="indexer_state"
    )
    prize_deposits: List["PrizeDepositedModel"] = Relationship(
        back_populates="indexer_state"
    )
    prize_distributions: List["PrizeDistributedModel"] = Relationship(
        back_populates="indexer_state"
    )
    competition_fee_paids: List["CompetitionFeePaidModel"] = Relationship(
        back_populates="indexer_state"
    )
    participant_winners: List["ParticipantWinnerModel"] = Relationship(
        back_populates="indexer_state"
    )
    certificate_participant_minteds: List["CertificateParticipantMintedModel"] = (
        Relationship(
            back_populates="indexer_state"
        )
    )
    certificate_participant_winner_minteds: List[
        "CertificateParticipantWinnerMintedModel"
    ] = Relationship(
        back_populates="indexer_state"
    )
    signature_certificate_participants: List["SignatureCertificateParticipantModel"] = (
        Relationship(back_populates="indexer_state")
    )
    signature_certificate_winners: List["SignatureCertificateWinnerModel"] = (
        Relationship(back_populates="indexer_state")
    )

