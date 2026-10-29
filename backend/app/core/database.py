import logging
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.core.config import settings

logger = logging.getLogger(__name__)

engine = create_async_engine(settings.database_url, echo=settings.debug)
async_session_factory = async_sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with async_session_factory() as session:
        yield session


async def check_db_connection() -> None:
    """Verify database connectivity. Raises ConnectionError with a clear message on failure."""
    from sqlalchemy import text

    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception as e:
        db_url = settings.database_url
        # Mask password in log output
        safe_url = db_url
        if "@" in db_url:
            prefix, rest = db_url.split("@", 1)
            safe_url = prefix.rsplit(":", 1)[0] + ":***@" + rest
        logger.error(
            "Failed to connect to PostgreSQL at %s — %s. "
            "Check that the database is running and connection settings are correct.",
            safe_url,
            e,
        )
        raise ConnectionError(
            f"Cannot connect to PostgreSQL ({safe_url}). "
            f"Check that the database is running and "
            f"OPENCOLAB_DATABASE_URL or POSTGRES_* settings are correct."
        ) from e
