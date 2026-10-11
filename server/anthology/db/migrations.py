"""Alembic helpers: configuration and migration state of a database."""

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy.ext.asyncio import AsyncEngine

from anthology.core.config import Settings


def alembic_config(settings: Settings) -> Config:
    config = Config()
    config.set_main_option("script_location", str(settings.migrations_dir))
    config.set_main_option("sqlalchemy.url", settings.database_url)
    return config


def head_revisions(settings: Settings) -> set[str]:
    return set(ScriptDirectory.from_config(alembic_config(settings)).get_heads())


async def upgrade(engine: AsyncEngine, settings: Settings, revision: str = "head") -> None:
    await _run_command(engine, settings, "upgrade", revision)


async def downgrade(engine: AsyncEngine, settings: Settings, revision: str = "base") -> None:
    await _run_command(engine, settings, "downgrade", revision)


async def _run_command(engine: AsyncEngine, settings: Settings, name: str, revision: str) -> None:
    def run(sync_conn) -> None:
        config = alembic_config(settings)
        config.attributes["connection"] = sync_conn
        getattr(command, name)(config, revision)

    async with engine.begin() as connection:
        await connection.run_sync(run)


async def current_revisions(engine: AsyncEngine) -> set[str]:
    async with engine.connect() as connection:
        return await connection.run_sync(
            lambda sync_conn: set(MigrationContext.configure(sync_conn).get_current_heads())
        )
