from datetime import datetime
from typing import Optional, List, TYPE_CHECKING
from sqlmodel import Field, SQLModel, Relationship
from sqlalchemy import Column, DateTime
from sqlalchemy.sql import func

if TYPE_CHECKING:
    from app.models.skill import SkillModel
    from app.models.skill_description import SkillDescriptionModel
    from app.models.social_media import SocialMediaModel
    from app.models.organization import OrganizationModel
    from app.models.team import TeamModel
    from app.models.team_role import TeamRoleModel


class UserModel(SQLModel, table=True):
    __tablename__ = "users"

    id: str = Field(primary_key=True)
    wallet_address: str = Field(unique=True)
    username: str = Field(unique=True)
    email: str = Field(unique=True)
    location: str
    institution: str
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

    skill: Optional["SkillModel"] = Relationship(back_populates="user")
    skill_description: Optional["SkillDescriptionModel"] = Relationship(
        back_populates="user"
    )
    social_media: Optional["SocialMediaModel"] = Relationship(back_populates="user")
    organizations: List["OrganizationModel"] = Relationship(back_populates="user")
    teams: List["TeamModel"] = Relationship(back_populates="user")
    team_roles: List["TeamRoleModel"] = Relationship(back_populates="user")



