from datetime import datetime
from typing import Optional, TYPE_CHECKING
from sqlmodel import Field, SQLModel, Relationship
from sqlalchemy import Column, DateTime
from sqlalchemy.sql import func
from app.utils import generate_ulid

if TYPE_CHECKING:
    from app.models.user import UserModel
    from app.models.competition import CompetitionModel


class NonceCertificateParticipantModel(SQLModel, table=True):
    __tablename__ = "nonce_certificate_participant"

    id: str = Field(default_factory=generate_ulid, primary_key=True)
    nonce: str = Field(unique=True)

    user_id: str = Field(foreign_key="users.id")
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

    user: Optional["UserModel"] = Relationship(
        back_populates="nonce_certificate_participants"
    )
    competition: Optional["CompetitionModel"] = Relationship(
        back_populates="nonce_certificate_participant"
    )
