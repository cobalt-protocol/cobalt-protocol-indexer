from datetime import datetime
from typing import Optional, TYPE_CHECKING
from sqlmodel import Field, SQLModel, Relationship
from sqlalchemy import Column, DateTime, BigInteger
from sqlalchemy.sql import func
from app.utils import generate_ulid

if TYPE_CHECKING:
    from app.models.competition import CompetitionModel
    from app.models.indexer_state import IndexerStateModel
    from app.models.prize_winner import PrizeWinnerModel
    from app.models.user import UserModel


class ParticipantWinnerModel(SQLModel, table=True):
    __tablename__ = "participant_winner"

    id: str = Field(default_factory=generate_ulid, primary_key=True)
    tx_hash: str
    # FK 1:N to users.wallet_address — each row references the winning user.
    # wallet_address is @unique in users, so it can be FK target.
    # One wallet may win multiple competitions/categories.
    participant: str = Field(
        foreign_key="users.wallet_address",
        index=True,
        nullable=False,
    )
    title: str
    competition_id: str = Field(foreign_key="competition.id")
    # Direct FK to prize_winner.winner_id (BigInt, global UNIQUE uint256 on-chain).
    # This is the logical 1:N join; no separate winner_id column needed.
    # prize_winner.winner_id has UniqueConstraint so it can be referenced.
    prize_winner_id: Optional[int] = Field(
        default=None, sa_type=BigInteger, foreign_key="prize_winner.winner_id", index=True
    )
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
        back_populates="participant_winners"
    )
    indexer_state: Optional["IndexerStateModel"] = Relationship(
        back_populates="participant_winners"
    )
    prize_winner: Optional["PrizeWinnerModel"] = Relationship(
        back_populates="participant_winners"
    )
    # 1:N from users via wallet_address — each row references the winning user.
    user: Optional["UserModel"] = Relationship(back_populates="participant_winners")

