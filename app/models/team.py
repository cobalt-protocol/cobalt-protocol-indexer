from datetime import datetime
from typing import Optional, List, TYPE_CHECKING
from sqlmodel import Field, SQLModel, Relationship
from sqlalchemy import Column, DateTime
from sqlalchemy.sql import func
from app.utils import generate_ulid

if TYPE_CHECKING:
    from app.models.competition import CompetitionModel
    from app.models.user import UserModel
    from app.models.skills_suggestion import SkillsSuggestionModel
    from app.models.team_code import TeamCodeModel
    from app.models.team_role import TeamRoleModel


class TeamModel(SQLModel, table=True):
    __tablename__ = "team"

    id: str = Field(default_factory=generate_ulid, primary_key=True)
    name: str
    visibility: bool
    description: str
    competition_id: str = Field(foreign_key="competition.id")
    user_id: str = Field(foreign_key="users.id")
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
        back_populates="teams"
    )
    user: Optional["UserModel"] = Relationship(back_populates="teams")
    skills_suggestions: List["SkillsSuggestionModel"] = Relationship(
        back_populates="team"
    )
    team_codes: List["TeamCodeModel"] = Relationship(back_populates="team")
    team_roles: List["TeamRoleModel"] = Relationship(back_populates="team")



