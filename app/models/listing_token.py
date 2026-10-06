from datetime import datetime
from typing import Optional, TYPE_CHECKING
from sqlmodel import Field, SQLModel, Relationship
from sqlalchemy import Column, DateTime, BigInteger
from sqlalchemy.sql import func
from app.utils import generate_ulid

if TYPE_CHECKING:
    from app.models.indexer_state import IndexerStateModel


class ListingTokenModel(SQLModel, table=True):
    __tablename__ = "listing_token"

    id: str = Field(default_factory=generate_ulid, primary_key=True)
    tx_hash: str
    listing_token_id: int = Field(sa_type=BigInteger)
    token_address: str
    is_active: bool = Field(default=True)
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

    indexer_state: Optional["IndexerStateModel"] = Relationship(
        back_populates="listing_tokens"
    )

