"""Test setup: SQLite by default, PostgreSQL when ANTHOLOGY_TEST_DATABASE_URL is set.

The PostgreSQL test database must be dedicated to tests: every test session migrates it
down to base and up to head, so all existing tables are dropped.
"""

import gc
import os
from collections.abc import AsyncIterator, Iterator

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine

import anthology.models  # noqa: F401  (registers all tables)
from anthology.api import app as app_module
from anthology.api.app import create_app
from anthology.core.config import Settings
from anthology.db import Base, create_engine
from anthology.db.migrations import downgrade, upgrade

TEST_DATABASE_URL = os.environ.get("ANTHOLOGY_TEST_DATABASE_URL", "")


@pytest.fixture(scope="session")
def settings(tmp_path_factory: pytest.TempPathFactory) -> Settings:
    data_dir = tmp_path_factory.mktemp("data")
    # Port 9 (discard) is closed: the tagger is unavailable unless a test brings its own.
    # No SSDP search: tests never reach real speakers.
    return Settings(
        data_dir=data_dir,
        database_url=TEST_DATABASE_URL,
        tagger_url="http://127.0.0.1:9",
        output_discovery=False,
    )


@pytest.fixture(autouse=True, scope="session")
def offline_lookups() -> Iterator[None]:
    """Apps created in tests never reach the real MusicBrainz: their lookups use a closed port
    (9). Tests of the lookups build their own ``LookupService`` with a mock transport."""
    original = app_module._lookups

    def offline(settings: Settings, sessionmaker):
        closed = settings.model_copy(update={"musicbrainz_public_url": "http://127.0.0.1:9"})
        return original(closed, sessionmaker)

    app_module._lookups = offline
    yield
    app_module._lookups = original


@pytest.fixture(scope="session")
async def engine(settings: Settings) -> AsyncIterator[AsyncEngine]:
    engine = create_engine(settings)
    await downgrade(engine, settings, "base")
    await upgrade(engine, settings, "head")
    yield engine
    await engine.dispose()


@pytest.fixture
async def clean_db(engine: AsyncEngine) -> None:
    """Delete all rows so that a test starts from an empty installation."""
    # A task cancelled during a write (e.g. a job item when the previous test's app shut down)
    # can leave its SQLite connection checked out with the transaction open; the pool closes
    # it only when the connection is garbage-collected. Until then the database stays locked,
    # so collect first.
    gc.collect()
    async with engine.begin() as connection:
        for table in reversed(Base.metadata.sorted_tables):
            await connection.execute(table.delete())


@pytest.fixture
async def app(settings: Settings, engine: AsyncEngine) -> AsyncIterator[FastAPI]:
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        yield app


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
