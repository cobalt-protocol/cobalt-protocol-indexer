from datetime import datetime
from typing import Optional, List, TYPE_CHECKING
from sqlmodel import Field, SQLModel, Relationship
from sqlalchemy import Column, DateTime
from sqlalchemy.sql import func
from app.utils import generate_ulid

if TYPE_CHECKING:
    from app.models.skills_user import SkillUserModel
    from app.models.skill_description_user import SkillDescriptionUserModel
    from app.models.social_media_user import SocialMediaUserModel
    from app.models.organization import OrganizationModel
    from app.models.team import TeamModel
    from app.models.team_role import TeamRoleModel
    from app.models.winner import WinnerModel
    from app.models.nonce_connect import NonceConnectModel
    from app.models.signature_certificate_participant import (
        SignatureCertificateParticipantModel,
    )
    from app.models.signature_certificate_winner import SignatureCertificateWinnerModel
    from app.models.competition import CompetitionModel
    from app.models.request_join import RequestJoinModel


class UserModel(SQLModel, table=True):
    __tablename__ = "users"

    id: str = Field(default_factory=generate_ulid, primary_key=True)
    wallet_address: str = Field(unique=True)

    username: Optional[str] = Field(default=None, unique=True)
    email: Optional[str] = Field(default=None, unique=True)
    location: Optional[str] = None
    institution: Optional[str] = None

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

    skills: List["SkillUserModel"] = Relationship(back_populates="user")
    skill_description: Optional["SkillDescriptionUserModel"] = Relationship(
        back_populates="user"
    )
    social_media: Optional["SocialMediaUserModel"] = Relationship(back_populates="user")
    organizations: List["OrganizationModel"] = Relationship(back_populates="user")
    teams: List["TeamModel"] = Relationship(back_populates="user")
    team_roles: List["TeamRoleModel"] = Relationship(back_populates="user")
    request_joins: List["RequestJoinModel"] = Relationship(back_populates="user")
    winner: Optional["WinnerModel"] = Relationship(back_populates="user")
    nonce_connect: Optional["NonceConnectModel"] = Relationship(back_populates="user")
    signature_certificate_participants: List["SignatureCertificateParticipantModel"] = (
        Relationship(back_populates="user")
    )
    signature_certificate_winners: List["SignatureCertificateWinnerModel"] = Relationship(
        back_populates="user"
    )
    competitions: List["CompetitionModel"] = Relationship(back_populates="user")
