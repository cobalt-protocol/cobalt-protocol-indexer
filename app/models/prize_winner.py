from datetime import datetime
from typing import Optional, TYPE_CHECKING
from sqlmodel import Field, SQLModel, Relationship
from sqlalchemy import Column, DateTime, BigInteger, Numeric
from sqlalchemy.sql import func
from app.utils import generate_ulid

if TYPE_CHECKING:
    from app.models.competition import CompetitionModel
    from app.models.winner import WinnerModel


class PrizeWinnerModel(SQLModel, table=True):
    __tablename__ = "prize_winner"

    id: str = Field(default_factory=generate_ulid, primary_key=True)
    winner_id: int = Field(sa_type=BigInteger)
    category: str
    amount: int = Field(sa_type=Numeric(78, 0))
    certificate_cid: str
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
        back_populates="prize_winners"
    )
    winner: Optional["WinnerModel"] = Relationship(back_populates="prize_winner")






