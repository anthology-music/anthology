import logging

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine

from anthology import __version__
from anthology.core.config import Settings
from anthology.db.migrations import downgrade, upgrade


async def test_health_reports_version(client: AsyncClient) -> None:
    response = await client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "version": __version__}


async def test_ready_with_current_migrations(client: AsyncClient) -> None:
    response = await client.get("/api/v1/ready")

    body = response.json()
    assert response.status_code == 200
    assert {key: body[key] for key in ("status", "database", "migrations")} == {
        "status": "ready",
        "database": "ok",
        "migrations": "current",
    }
    assert body["services"] in ({}, {"tagger": "unavailable"})  # monitor may not have run yet


async def test_ready_does_not_log_migration_details(
    client: AsyncClient, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.INFO):
        await client.get("/api/v1/ready")

    assert not [record for record in caplog.records if record.name.startswith("alembic")]


@pytest.mark.usefixtures("clean_db")  # a downgrade to base needs empty tables
async def test_not_ready_when_migrations_are_behind(
    client: AsyncClient, settings: Settings, engine: AsyncEngine
) -> None:
    await downgrade(engine, settings, "base")
    try:
        response = await client.get("/api/v1/ready")
    finally:
        await upgrade(engine, settings, "head")

    assert response.status_code == 503
    assert response.json() == {
        "status": "not_ready",
        "database": "ok",
        "migrations": "behind",
        "services": {},
    }
