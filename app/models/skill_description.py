from datetime import datetime
from typing import Optional, TYPE_CHECKING
from sqlmodel import Field, SQLModel, Relationship
from sqlalchemy import Column, DateTime
from sqlalchemy.sql import func

if TYPE_CHECKING:
    from app.models.user import UserModel


class SkillDescriptionModel(SQLModel, table=True):
    __tablename__ = "skill_description"

    id: str = Field(primary_key=True)
    description: str
    user_id: str = Field(unique=True, foreign_key="users.id")
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
    deleted_at: Optional[int] = Field(default=None)

    user: Optional["UserModel"] = Relationship(back_populates="skill_description")



