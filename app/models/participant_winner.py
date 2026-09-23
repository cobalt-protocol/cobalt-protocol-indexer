from datetime import datetime
from typing import Optional, TYPE_CHECKING
from sqlmodel import Field, SQLModel, Relationship
from sqlalchemy import Column, DateTime, BigInteger
from sqlalchemy.sql import func
from app.utils import generate_ulid

if TYPE_CHECKING:
    from app.models.competition import CompetitionModel


class ParticipantWinnerModel(SQLModel, table=True):
    __tablename__ = "participant_winner"

    id: str = Field(default_factory=generate_ulid, primary_key=True)
    tx_hash: str
    winner_id: int = Field(sa_type=BigInteger)
    participant: str
    participant_winner_id: int = Field(sa_type=BigInteger)
    title: str
    competition_id: str = Field(foreign_key="competition.id")

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

    competition: Optional["CompetitionModel"] = Relationship(
        back_populates="participant_winners"
    )

