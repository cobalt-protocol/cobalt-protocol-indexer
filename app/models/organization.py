from datetime import datetime
from typing import Optional, TYPE_CHECKING
from sqlmodel import Field, SQLModel, Relationship
from sqlalchemy import Column, DateTime
from sqlalchemy.sql import func
from app.utils import generate_ulid

if TYPE_CHECKING:
    from app.models.user import UserModel


class OrganizationModel(SQLModel, table=True):
    __tablename__ = "organization"

    id: str = Field(default_factory=generate_ulid, primary_key=True)
    tx_hash: str = Field(unique=True)

    avatar_url: Optional[str] = Field(default=None, unique=True)
    name: Optional[str] = Field(default=None, unique=True)
    description: Optional[str] = Field(default=None, unique=True)

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

    user: Optional["UserModel"] = Relationship(back_populates="organizations")
