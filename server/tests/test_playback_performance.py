"""Starting playback of a large list with 500,000 generated tracks (spec: playback, Long list;
interaction budget)."""

import statistics
import time

import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine

from anthology.core.config import Settings
from anthology.library.models import Track
from anthology.library.seed import seed_library
from tests.users_helpers import setup_admin
from tests.ws_helpers import ws_connect

pytestmark = [pytest.mark.performance, pytest.mark.usefixtures("clean_db")]

BUDGET_SECONDS = 2.0
TRACKS = 500_000
RUNS = 5


async def test_playing_all_tracks_meets_the_budget(
    settings: Settings, app: FastAPI, client: AsyncClient, engine: AsyncEngine
) -> None:
    if settings.is_sqlite:
        pytest.skip("performance budgets are measured on PostgreSQL")
    await seed_library(engine, TRACKS, reset=True)
    admin = await setup_admin(client)
    async with app.state.sessionmaker() as session:
        # A track in the middle of the list: the queue holds the 10,000 from there on.
        middle = await session.scalar(
            select(Track.id)
            .order_by(Track.sort_artist, Track.sort_title, Track.sort_album, Track.id)
            .offset(TRACKS // 2)
            .limit(1)
        )

    starts: list[float] = []
    firsts: list[float] = []
    for run in range(RUNS):
        started = time.perf_counter()
        response = await client.post(
            "/api/v1/playback/queue",
            headers=admin.headers,
            json={"rule": {"list": "tracks"}, "start": str(middle)},
        )
        starts.append(time.perf_counter() - started)
        assert response.json() == {"entries": 10_000, "shortened": True}

        async with ws_connect(app) as ws:
            await ws.hello(admin.access_token)
            started = time.perf_counter()
            state = await ws.subscribe(f"s{run}", "playback.state")
            [row] = await ws.rows(f"s{run}", 1)
            await ws.subscribe(f"q{run}", "playback.queue", generation=row["generation"])
            await ws.rows(f"q{run}", 100)
            firsts.append(time.perf_counter() - started)
        assert state["data"]["total"] == 1 and row["current"]["id"] == str(middle)

    p95_start = statistics.quantiles(starts, n=20)[-1]
    p95_first = statistics.quantiles(firsts, n=20)[-1]
    print(f"\nplay all: start p95 {p95_start:.3f}s, first queue rows p95 {p95_first:.3f}s")
    assert p95_start <= BUDGET_SECONDS
    assert p95_first <= BUDGET_SECONDS
