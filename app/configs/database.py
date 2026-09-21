from sqlmodel import SQLModel, create_engine
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.orm import sessionmaker
from app.configs.settings import settings
from typing import Annotated, AsyncGenerator
from fastapi import Depends

SQLALCHEMY_DATABASE_URL = settings.database_url

if SQLALCHEMY_DATABASE_URL.startswith("postgresql://"):
    ASYNC_SQLALCHEMY_DATABASE_URL = SQLALCHEMY_DATABASE_URL.replace(
        "postgresql://", "postgresql+asyncpg://", 1
    )
elif SQLALCHEMY_DATABASE_URL.startswith("sqlite://"):
    ASYNC_SQLALCHEMY_DATABASE_URL = SQLALCHEMY_DATABASE_URL.replace(
        "sqlite://", "sqlite+aiosqlite://", 1
    )
else:
    ASYNC_SQLALCHEMY_DATABASE_URL = SQLALCHEMY_DATABASE_URL

sync_engine = create_engine(SQLALCHEMY_DATABASE_URL)
engine = create_async_engine(ASYNC_SQLALCHEMY_DATABASE_URL, future=True, echo=False)

SyncSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=sync_engine)
AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


def create_db_and_tables() -> None:
    import app.models  # noqa: F401
    SQLModel.metadata.create_all(sync_engine)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise


SessionDep = Annotated[AsyncSession, Depends(get_session)]
