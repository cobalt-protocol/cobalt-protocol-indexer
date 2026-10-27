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

    try:
        from sqlalchemy import text

        with sync_engine.connect() as conn:
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector;"))
            conn.commit()
    except Exception:
        pass

    SQLModel.metadata.create_all(sync_engine)

    # Ensure participant_winner.participant and team_id are not unique (allow multiple participant_winner per participant and per team)
    try:
        from sqlalchemy import text

        with sync_engine.connect() as conn:
            conn.execute(
                text("""
                DO $$
                BEGIN
                    IF EXISTS (
                        SELECT 1 FROM information_schema.columns 
                        WHERE table_name = 'indexer_state' AND column_name = 'contract_name'
                    ) THEN
                        ALTER TABLE indexer_state DROP CONSTRAINT IF EXISTS indexer_state_contract_name_chain_id_key;
                        DROP INDEX IF EXISTS ix_indexer_state_contract_name;
                        ALTER TABLE indexer_state RENAME COLUMN contract_name TO contract_address;
                        ALTER TABLE indexer_state ADD CONSTRAINT indexer_state_contract_address_chain_id_key UNIQUE (contract_address, chain_id);
                        CREATE INDEX IF NOT EXISTS ix_indexer_state_contract_address ON indexer_state (contract_address);
                    END IF;
                END $$;
            """)
            )
            conn.execute(text("DROP INDEX IF EXISTS ix_participant_winner_participant;"))
            conn.execute(text("ALTER TABLE participant_winner DROP CONSTRAINT IF EXISTS ix_participant_winner_participant;"))
            conn.execute(text("ALTER TABLE participant_winner DROP CONSTRAINT IF EXISTS participant_winner_participant_key;"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_participant_winner_participant ON participant_winner (participant);"))

            conn.execute(text("DROP INDEX IF EXISTS ix_participant_winner_team_id;"))
            conn.execute(text("ALTER TABLE participant_winner DROP CONSTRAINT IF EXISTS ix_participant_winner_team_id;"))
            conn.execute(text("ALTER TABLE participant_winner DROP CONSTRAINT IF EXISTS participant_winner_team_id_key;"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_participant_winner_team_id ON participant_winner (team_id);"))

            # Pastikan tipe kolom requirement di requirements_team dan content di recomendation_team bertipe TEXT
            conn.execute(text("ALTER TABLE requirements_team ALTER COLUMN requirement TYPE TEXT;"))
            conn.execute(text("ALTER TABLE recomendation_team ALTER COLUMN content TYPE TEXT;"))
            conn.commit()
    except Exception:
        pass


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise


SessionDep = Annotated[AsyncSession, Depends(get_session)]
