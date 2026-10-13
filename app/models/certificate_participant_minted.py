from datetime import datetime
from typing import Optional, TYPE_CHECKING
from sqlmodel import Field, SQLModel, Relationship
from sqlalchemy import Column, DateTime, BigInteger
from sqlalchemy.sql import func
from app.utils import generate_ulid

if TYPE_CHECKING:
    from app.models.competition import CompetitionModel
    from app.models.indexer_state import IndexerStateModel
    from app.models.user import UserModel
    from app.models.team import TeamModel


class CertificateParticipantMintedModel(SQLModel, table=True):
    __tablename__ = "certificate_participant_minted"

    id: str = Field(default_factory=generate_ulid, primary_key=True)
    tx_hash: str
    token_id: int = Field(sa_type=BigInteger)
    competition_id: str = Field(foreign_key="competition.id")
    team_id: Optional[str] = Field(
        default=None, foreign_key="team.id", index=True
    )
    uri: str
    # FK → users.id — participant wallet resolved to users.wallet_address (case-insensitive)
    user_id: Optional[str] = Field(
        default=None, foreign_key="users.id", index=True
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
        back_populates="certificate_participant_minted"
    )
    team: Optional["TeamModel"] = Relationship(
        back_populates="certificate_participant_minteds"
    )
    indexer_state: Optional["IndexerStateModel"] = Relationship(
        back_populates="certificate_participant_minteds"
    )
    user: Optional["UserModel"] = Relationship(
        back_populates="certificate_participant_minteds"
    )

