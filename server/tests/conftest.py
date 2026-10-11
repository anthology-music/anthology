"""Test setup: SQLite by default, PostgreSQL when ANTHOLOGY_TEST_DATABASE_URL is set.

The PostgreSQL test database must be dedicated to tests: every test session migrates it
down to base and up to head, so all existing tables are dropped.
"""

import os
from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine

from anthology.api.app import create_app
from anthology.core.config import Settings
from anthology.db import create_engine
from anthology.db.migrations import downgrade, upgrade

TEST_DATABASE_URL = os.environ.get("ANTHOLOGY_TEST_DATABASE_URL", "")


@pytest.fixture(scope="session")
def settings(tmp_path_factory: pytest.TempPathFactory) -> Settings:
    data_dir = tmp_path_factory.mktemp("data")
    return Settings(data_dir=data_dir, database_url=TEST_DATABASE_URL)


@pytest.fixture(scope="session")
async def engine(settings: Settings) -> AsyncIterator[AsyncEngine]:
    engine = create_engine(settings)
    await downgrade(engine, settings, "base")
    await upgrade(engine, settings, "head")
    yield engine
    await engine.dispose()


@pytest.fixture
async def client(settings: Settings, engine: AsyncEngine) -> AsyncIterator[AsyncClient]:
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            yield client
