"""A playlist with 20,000 entries (spec: personal-data, Large playlists; interaction budget)."""

import statistics
import time

import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine

from anthology.core.config import Settings
from anthology.library.seed import seed_library
from tests.users_helpers import setup_admin
from tests.ws_helpers import ws_connect

pytestmark = [pytest.mark.performance, pytest.mark.usefixtures("clean_db")]

BUDGET_SECONDS = 2.0
ENTRIES = 20_000
RUNS = 5


async def test_a_large_playlist_meets_the_budget(
    settings: Settings, app: FastAPI, client: AsyncClient, engine: AsyncEngine
) -> None:
    if settings.is_sqlite:
        pytest.skip("performance budgets are measured on PostgreSQL")
    await seed_library(engine, ENTRIES, reset=True)
    admin = await setup_admin(client)
    created = await client.post(
        "/api/v1/playlists", headers=admin.headers, json={"name": "Alles", "visibility": "shared"}
    )
    playlist = created.json()["id"]
    # Two additions of 10,000 (the most one request may add), the second at the start.
    for at_start in (False, True):
        response = await client.post(
            f"/api/v1/playlists/{playlist}/entries",
            headers=admin.headers,
            json={"rule": {"list": "tracks"}, "at_start": at_start},
        )
        assert response.json()["entries"] == 10_000

    firsts: list[float] = []
    for run in range(RUNS):
        async with ws_connect(app) as ws:
            await ws.hello(admin.access_token)
            started = time.perf_counter()
            meta = await ws.subscribe(f"e{run}", "personal.playlist.entries", playlist_id=playlist)
            await ws.rows(f"e{run}", 100)
            firsts.append(time.perf_counter() - started)
        assert meta["data"]["total"] == ENTRIES

    p95 = statistics.quantiles(firsts, n=20)[-1]
    print(f"\nplaylist of {ENTRIES}: count and first rows p95 {p95:.3f}s")
    assert p95 <= BUDGET_SECONDS
