from datetime import datetime
from typing import Optional, TYPE_CHECKING
from sqlmodel import Field, SQLModel, Relationship
from sqlalchemy import Column, DateTime
from sqlalchemy.sql import func
from app.utils import generate_ulid

if TYPE_CHECKING:
    from app.models.user import UserModel
    from app.models.competition import CompetitionModel
    from app.models.team import TeamModel
    from app.models.indexer_state import IndexerStateModel


class SignatureCertificateParticipantModel(SQLModel, table=True):
    __tablename__ = "signature_certificate_participant"

    id: str = Field(default_factory=generate_ulid, primary_key=True)
    signature: str = Field()

    user_id: str = Field(foreign_key="users.id")
    competition_id: str = Field(foreign_key="competition.id")
    team_id: str = Field(foreign_key="team.id")
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

    user: Optional["UserModel"] = Relationship(
        back_populates="signature_certificate_participants"
    )
    competition: Optional["CompetitionModel"] = Relationship(
        back_populates="signature_certificate_participants"
    )
    team: Optional["TeamModel"] = Relationship(
        back_populates="signature_certificate_participants"
    )
    indexer_state: Optional["IndexerStateModel"] = Relationship(
        back_populates="signature_certificate_participants"
    )
