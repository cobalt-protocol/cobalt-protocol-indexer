from datetime import datetime
from typing import Optional
from sqlmodel import Field, SQLModel
from sqlalchemy import Column, DateTime, BigInteger
from sqlalchemy.sql import func
from app.utils import generate_ulid


class ListingTokenPrizeModel(SQLModel, table=True):
    __tablename__ = "listing_token_prize"

    id: str = Field(default_factory=generate_ulid, primary_key=True)
    tx_hash: str
    listing_token_prize_id: int = Field(sa_type=BigInteger)
    token_address: str
    is_active: bool = Field(default=True)
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

