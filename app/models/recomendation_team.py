from datetime import datetime
from typing import Optional, List, Dict, Any, TYPE_CHECKING
from sqlmodel import Field, SQLModel, Relationship
from sqlalchemy import Column, DateTime, Text, JSON
from sqlalchemy.sql import func
from app.utils import generate_ulid

try:
    from pgvector.sqlalchemy import Vector
except ImportError:
    from sqlalchemy.types import UserDefinedType

    class Vector(UserDefinedType):
        cache_ok = True

        def __init__(self, dim=None):
            super().__init__()
            self.dim = dim

        def get_col_spec(self, **kw):
            if self.dim is None:
                return "VECTOR"
            return f"VECTOR({self.dim})"


if TYPE_CHECKING:
    from app.models.team import TeamModel


class RecomendationTeamModel(SQLModel, table=True):
    __tablename__ = "recomendation_team"

    id: str = Field(default_factory=generate_ulid, primary_key=True)
    content: str = Field(sa_column=Column(Text, nullable=False))
    embedding: Optional[List[float]] = Field(
        default=None, sa_column=Column(Vector(), nullable=True)
    )
    metadata_: Optional[Dict[str, Any]] = Field(
        default=None,
        alias="metadata",
        sa_column=Column("metadata", JSON, nullable=True),
    )
    team_id: str = Field(unique=True, foreign_key="team.id")

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

    team: Optional["TeamModel"] = Relationship(back_populates="recomendation_team")
