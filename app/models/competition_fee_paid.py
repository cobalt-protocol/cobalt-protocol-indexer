from datetime import datetime
from typing import Optional, TYPE_CHECKING
from sqlmodel import Field, SQLModel, Relationship
from sqlalchemy import Column, DateTime, Numeric
from sqlalchemy.sql import func
from app.utils import generate_ulid

if TYPE_CHECKING:
    from app.models.competition import CompetitionModel
    from app.models.indexer_state import IndexerStateModel


class CompetitionFeePaidModel(SQLModel, table=True):
    __tablename__ = "competition_fee_paid"

    id: str = Field(default_factory=generate_ulid, primary_key=True)
    tx_hash: str
    competition_id: str = Field(foreign_key="competition.id", unique=True)
    payer: str
    token_address: str
    amount: int = Field(sa_type=Numeric(78, 0))
    indexer_state_id: Optional[str] = Field(
        default=None, foreign_key="indexer_state.id"
    )
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
        back_populates="competition_fee_paid"
    )
    indexer_state: Optional["IndexerStateModel"] = Relationship(
        back_populates="competition_fee_paids"
    )
