from datetime import datetime
from typing import Optional, TYPE_CHECKING
from sqlmodel import Field, SQLModel, Relationship
from sqlalchemy import Column, DateTime
from sqlalchemy.sql import func

if TYPE_CHECKING:
    from app.models.user import UserModel
    from app.models.team import TeamModel


class TeamRoleModel(SQLModel, table=True):
    __tablename__ = "team_role"

    id: str = Field(primary_key=True)
    role: str
    user_id: str = Field(foreign_key="users.id")
    team_id: str = Field(foreign_key="team.id")
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

    user: Optional["UserModel"] = Relationship(back_populates="team_roles")
    team: Optional["TeamModel"] = Relationship(back_populates="team_roles")



