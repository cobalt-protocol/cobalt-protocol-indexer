from datetime import datetime
from typing import Optional, TYPE_CHECKING
from sqlmodel import Field, SQLModel, Relationship
from sqlalchemy import Column, DateTime, BigInteger, Numeric
from sqlalchemy.sql import func
from app.utils import generate_ulid

if TYPE_CHECKING:
    from app.models.competition import CompetitionModel


class PrizeDepositedModel(SQLModel, table=True):
    __tablename__ = "prize_deposited"

    id: str = Field(default_factory=generate_ulid, primary_key=True)
    tx_hash: str
    treasury_prize_id: int = Field(sa_type=BigInteger)
    competition_id: str = Field(foreign_key="competition.id")
    token_address: str
    sender: str
    amount: int = Field(sa_type=Numeric(78, 0))
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
        back_populates="prize_deposits"
    )
