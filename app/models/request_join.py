from datetime import datetime
from typing import Optional, TYPE_CHECKING
from sqlmodel import Field, SQLModel, Relationship
from sqlalchemy import Column, DateTime
from sqlalchemy.sql import func
from app.utils import generate_ulid

if TYPE_CHECKING:
    from app.models.team import TeamModel
    from app.models.user import UserModel


class RequestJoinModel(SQLModel, table=True):
    __tablename__ = "request_join"

    id: str = Field(default_factory=generate_ulid, primary_key=True)
    status: str = Field(default="pending")
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

    user: Optional["UserModel"] = Relationship(back_populates="request_joins")
    team: Optional["TeamModel"] = Relationship(back_populates="request_join")
