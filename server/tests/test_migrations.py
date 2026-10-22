import pytest
from alembic.autogenerate import compare_metadata
from alembic.runtime.migration import MigrationContext
from sqlalchemy.ext.asyncio import AsyncEngine

import anthology.models  # noqa: F401  (registers all tables)
from anthology.core.config import Settings
from anthology.db import Base
from anthology.db.migrations import current_revisions, downgrade, head_revisions, upgrade


# Rows left by earlier tests would block the downgrade (SQLite recreates tables in batch mode).
@pytest.mark.usefixtures("clean_db")
async def test_upgrade_and_downgrade_round_trip(settings: Settings, engine: AsyncEngine) -> None:
    await downgrade(engine, settings, "base")
    assert await current_revisions(engine) == set()

    await upgrade(engine, settings, "head")
    assert await current_revisions(engine) == head_revisions(settings)


async def test_migrations_match_models(engine: AsyncEngine) -> None:
    def diff(sync_conn):
        context = MigrationContext.configure(
            sync_conn,
            opts={
                "compare_type": True,
                # like migrations/env.py: only tables of Base.metadata (not the demo table)
                "include_name": lambda name, type_, _parents: (
                    type_ != "table" or name in Base.metadata.tables
                ),
            },
        )
        return compare_metadata(context, Base.metadata)

    async with engine.connect() as connection:
        differences = await connection.run_sync(diff)

    assert differences == []
