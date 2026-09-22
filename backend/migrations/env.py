"""Configurazione Alembic per SQLAlchemy 2 async.

Supporta sia la modalità "offline" (genera SQL senza connettersi al DB) sia
quella "online": quest'ultima usa un engine ASYNC (asyncpg, lo stesso driver
di runtime) eseguito tramite `asyncio.run`, secondo il pattern raccomandato
da SQLAlchemy per Alembic + async.
"""

from __future__ import annotations

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

# Importiamo tutti i modelli (via app.models) così che Base.metadata sia
# completo: è quello che permette all'autogenerate di vedere l'intero schema.
from app.config import settings
from app.models import Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

# Sovrascriviamo l'URL configurato staticamente in alembic.ini con quello
# derivato da app.config.settings, per avere un'unica fonte di verità
# (variabili d'ambiente) sia per il runtime FastAPI sia per le migrazioni.
config.set_main_option("sqlalchemy.url", settings.DATABASE_URL)


def run_migrations_offline() -> None:
    """Genera SQL senza connettersi al database (modalità offline di Alembic)."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    """Esegue le migrazioni contro un database reale, usando un engine async."""
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
