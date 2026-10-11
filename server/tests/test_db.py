import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from anthology.core.config import Settings
from anthology.db import create_sessionmaker


async def test_session_executes_query(engine: AsyncEngine) -> None:
    async with create_sessionmaker(engine)() as session:
        result = await session.execute(text("SELECT 1"))

    assert result.scalar_one() == 1


async def test_sqlite_runs_with_wal_and_foreign_keys(
    settings: Settings, engine: AsyncEngine
) -> None:
    if not settings.is_sqlite:
        pytest.skip("SQLite only")

    async with engine.connect() as connection:
        journal_mode = (await connection.execute(text("PRAGMA journal_mode"))).scalar_one()
        foreign_keys = (await connection.execute(text("PRAGMA foreign_keys"))).scalar_one()

    assert journal_mode == "wal"
    assert foreign_keys == 1
