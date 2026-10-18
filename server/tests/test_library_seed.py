"""Seeding a development database with the test library generator (spec: library)."""

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncEngine

from anthology.cli import seed_library as seed_library_command
from anthology.core.changes import ChangeLog
from anthology.core.config import Settings
from anthology.db import create_sessionmaker
from anthology.library.models import Artist
from anthology.library.seed import LibraryNotEmptyError, seed_library
from tests.library_helpers import album, assert_consistent

pytestmark = pytest.mark.usefixtures("clean_db")


def test_seeding_is_refused_without_the_flag(settings: Settings) -> None:
    command_settings = settings.model_copy(update={"dev_demo": False})
    assert seed_library_command(command_settings, 10, reset=False) == 1


async def test_seeded_library_is_consistent(engine: AsyncEngine) -> None:
    counters = await seed_library(engine, 1000)

    async with create_sessionmaker(engine)() as session:
        await assert_consistent(session)
        changes = await session.scalar(select(func.count()).select_from(ChangeLog))
    assert counters["tracks"] == 1000
    assert counters["recordings"] < 1000  # editions and compilations reuse recordings
    assert changes == 0  # offline developer action


async def test_non_empty_library_is_refused_without_reset(engine: AsyncEngine) -> None:
    sessionmaker = create_sessionmaker(engine)
    async with sessionmaker() as session, session.begin():
        await album(session, "Glas", "Kalt", ["Eisfeld"])

    with pytest.raises(LibraryNotEmptyError):
        await seed_library(engine, 100)
    async with sessionmaker() as session:
        names = list(await session.scalars(select(Artist.name)))
    assert names == ["Glas"]

    counters = await seed_library(engine, 100, reset=True)
    async with sessionmaker() as session:
        await assert_consistent(session)
        assert await session.scalar(select(Artist).where(Artist.name == "Glas")) is None
    assert counters["tracks"] == 100
