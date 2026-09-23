from datetime import datetime
from typing import Optional, List, TYPE_CHECKING
from sqlmodel import Field, SQLModel, Relationship
from sqlalchemy import Column, DateTime, BigInteger, Numeric
from sqlalchemy.sql import func
from app.utils import generate_ulid

if TYPE_CHECKING:
    from app.models.competition import CompetitionModel


class PriceCompetitionModel(SQLModel, table=True):
    __tablename__ = "price_competition"

    id: str = Field(default_factory=generate_ulid, primary_key=True)
    tx_hash: str
    price_competition_fee_id: int = Field(unique=True, sa_type=BigInteger)
    treasury_fee: int = Field(sa_type=Numeric(78, 0))
    token_address: str
    title: str
    description: str
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

    competitions: List["CompetitionModel"] = Relationship(
        back_populates="price_competition"
    )


