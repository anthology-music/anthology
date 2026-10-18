"""Library list budget with 500,000 generated tracks (spec: library, Library list budget)."""

import statistics
import time

import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncEngine

from anthology.core.config import Settings
from anthology.library.seed import seed_library
from tests.users_helpers import setup_admin
from tests.ws_helpers import ws_connect

pytestmark = [pytest.mark.performance, pytest.mark.usefixtures("clean_db")]

BUDGET_SECONDS = 2.0
TRACKS = 500_000
RUNS = 5


STREAMS = ("library.artists", "library.releases", "library.tracks")


async def test_library_lists_meet_the_interaction_budget(
    settings: Settings, app: FastAPI, client: AsyncClient, engine: AsyncEngine
) -> None:
    if settings.is_sqlite:
        pytest.skip("performance budgets are measured on PostgreSQL")
    counters = await seed_library(engine, TRACKS, reset=True)
    admin = await setup_admin(client)

    statements: list[str] = []

    def capture(_conn, _cursor, statement, _parameters, _context, _executemany) -> None:
        statements.append(statement)

    event.listen(app.state.engine.sync_engine, "before_cursor_execute", capture)
    try:
        for stream in STREAMS:
            total = counters[stream.removeprefix("library.")]
            await _measure(app, admin.access_token, stream, total)
    finally:
        event.remove(app.state.engine.sync_engine, "before_cursor_execute", capture)

    assert statements
    assert not [statement for statement in statements if "OFFSET" in statement.upper()]


async def _measure(app: FastAPI, token: str, stream: str, total: int) -> None:
    """Totals and first rows, then a jump to the middle; both within the budget (p95)."""
    middle = total // 2
    first_window: list[float] = []
    jumps: list[float] = []
    for _ in range(RUNS):
        async with ws_connect(app) as ws:
            await ws.hello(token)

            started = time.perf_counter()
            meta = await ws.subscribe("s", stream, start=0, end=100)
            await ws.rows("s", 100)
            first_window.append(time.perf_counter() - started)

            started = time.perf_counter()
            await ws.send("window", "s", start=middle, end=middle + 100)
            chunk = await ws.recv_type("chunk", "s", wait=10)
            jumps.append(time.perf_counter() - started)

        assert meta["data"]["total"] == total
        assert chunk["data"]["start"] == middle

    p95_first = statistics.quantiles(first_window, n=20)[-1]
    p95_jump = statistics.quantiles(jumps, n=20)[-1]
    print(f"\n{stream}: first window p95 {p95_first:.3f}s, jump p95 {p95_jump:.3f}s")
    assert p95_first <= BUDGET_SECONDS, stream
    assert p95_jump <= BUDGET_SECONDS, stream
