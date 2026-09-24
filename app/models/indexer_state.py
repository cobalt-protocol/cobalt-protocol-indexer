from datetime import datetime
from typing import Optional
from sqlmodel import Field, SQLModel
from sqlalchemy import Column, DateTime
from sqlalchemy.sql import func
from app.utils import generate_ulid


class IndexerStateModel(SQLModel, table=True):
    __tablename__ = "indexer_state"

    id: str = Field(default_factory=generate_ulid, primary_key=True)
    contract_name: str = Field(unique=True, index=True)
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
