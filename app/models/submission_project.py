from datetime import datetime
from typing import Optional, TYPE_CHECKING
from sqlmodel import Field, SQLModel, Relationship
from sqlalchemy import Column, DateTime
from sqlalchemy.sql import func
from app.utils import generate_ulid

if TYPE_CHECKING:
    from app.models.team import TeamModel


class SubmissionProjectModel(SQLModel, table=True):
    __tablename__ = "submission_project"

    id: str = Field(default_factory=generate_ulid, primary_key=True)
    title: str
    description: Optional[str] = None
    submission_link: str
    document_cid: str
    team_id: str = Field(foreign_key="team.id", unique=True)
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

    team: Optional["TeamModel"] = Relationship(back_populates="submission_project")
