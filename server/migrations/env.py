"""Alembic environment (async) for SQLite and PostgreSQL."""

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy.engine import Connection

import anthology.models  # noqa: F401  (registers all tables)
from anthology.core.config import get_settings
from anthology.db import Base, create_engine
from anthology.search.models import ENGINE_SPECIFIC

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def include_name(name, type_, parent_names) -> bool:
    """Only manage tables of ``Base.metadata`` (e.g. ignore the developer demo table) and
    leave the engine-specific search columns and indexes alone."""
    if type_ == "table":
        return name in target_metadata.tables
    return name not in ENGINE_SPECIFIC


def _database_url() -> str:
    return config.get_main_option("sqlalchemy.url") or get_settings().database_url


def run_migrations_offline() -> None:
    context.configure(
        url=_database_url(),
        target_metadata=target_metadata,
        include_name=include_name,
        literal_binds=True,
        render_as_batch=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def _run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        include_name=include_name,
        render_as_batch=connection.dialect.name == "sqlite",
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    settings = get_settings().model_copy(update={"database_url": _database_url()})
    engine = create_engine(settings)
    async with engine.connect() as connection:
        await connection.run_sync(_run_migrations)
        await connection.commit()
    await engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
elif (connection := config.attributes.get("connection")) is not None:
    _run_migrations(connection)
else:
    asyncio.run(run_migrations_online())
