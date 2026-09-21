from datetime import datetime
from typing import Optional, TYPE_CHECKING
from sqlmodel import Field, SQLModel, Relationship
from sqlalchemy import Column, DateTime
from sqlalchemy.sql import func
from app.utils import generate_ulid

if TYPE_CHECKING:
    from app.models.user import UserModel
    from app.models.prize_winner import PrizeWinnerModel


class WinnerModel(SQLModel, table=True):
    __tablename__ = "winner"

    id: str = Field(default_factory=generate_ulid, primary_key=True)
    wallet_address: str
    user_id: str = Field(unique=True, foreign_key="users.id")
    prize_winner_id: str = Field(unique=True, foreign_key="prize_winner.id")
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

    user: Optional["UserModel"] = Relationship(back_populates="winner")
    prize_winner: Optional["PrizeWinnerModel"] = Relationship(back_populates="winner")


