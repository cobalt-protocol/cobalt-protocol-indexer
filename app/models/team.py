from datetime import datetime
from typing import Optional, List, TYPE_CHECKING
from sqlmodel import Field, SQLModel, Relationship
from sqlalchemy import Column, DateTime
from sqlalchemy.sql import func
from app.utils import generate_ulid

if TYPE_CHECKING:
    from app.models.competition import CompetitionModel
    from app.models.user import UserModel
    from app.models.skills_team import SkillsTeamModel
    from app.models.requirements_team import RequirementsTeamModel
    from app.models.team_code import TeamCodeModel
    from app.models.team_role import TeamRoleModel
    from app.models.request_join import RequestJoinModel
    from app.models.submission_project import SubmissionProjectModel


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

    competition: Optional["CompetitionModel"] = Relationship(back_populates="teams")
    user: Optional["UserModel"] = Relationship(back_populates="teams")
    skills_team: List["SkillsTeamModel"] = Relationship(back_populates="team")
    requirements_team: Optional["RequirementsTeamModel"] = Relationship(
        back_populates="team"
    )
    request_join: Optional["RequestJoinModel"] = Relationship(
        back_populates="team"
    )
    team_codes: List["TeamCodeModel"] = Relationship(back_populates="team")
    team_roles: List["TeamRoleModel"] = Relationship(back_populates="team")
    submission_project: Optional["SubmissionProjectModel"] = Relationship(
        back_populates="team"
    )
