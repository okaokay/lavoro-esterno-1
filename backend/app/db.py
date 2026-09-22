"""Setup del layer database asincrono (SQLAlchemy 2 + asyncpg)."""

from __future__ import annotations

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings


def _to_async_url(url: str) -> str:
    """Normalizza l'URL DB per garantire l'uso del driver asyncpg a runtime.

    Permette di configurare DATABASE_URL sia come `postgresql://` (comodo per
    tool esterni/Alembic sync) sia già come `postgresql+asyncpg://`.
    """
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+asyncpg://", 1)
    return url


engine = create_async_engine(_to_async_url(settings.DATABASE_URL), pool_pre_ping=True)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


async def get_db() -> AsyncGenerator[AsyncSession]:
    """Dependency FastAPI: fornisce una sessione async per richiesta, con chiusura garantita."""
    async with AsyncSessionLocal() as session:
        yield session
