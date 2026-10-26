"""Search budget with 500,000 generated tracks (spec: search, Search performance)."""

import statistics
import time

import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine

from anthology.core.config import Settings
from anthology.library.seed import seed_library
from tests.users_helpers import setup_admin
from tests.ws_helpers import Ws, ws_connect

pytestmark = [pytest.mark.performance, pytest.mark.usefixtures("clean_db")]

FIRST_RESULTS_SECONDS = 0.3
INTERACTIVE_SECONDS = 2.0
TRACKS = 500_000
RUNS = 10
FIRST_ROWS = 20
STREAMS = ("search.artists", "search.releases", "search.tracks")
# A common title word, a two-letter prefix, a typo, filters with and without words.
QUERIES = ("polka", "po", "Walzr", "format:flac", "polka year:>2000 format:flac")


async def _first_results(ws: Ws, q: str, run: int) -> tuple[float, dict[str, int]]:
    """Subscribe to the three result types at once like the client; time until every count
    and the first rows arrived."""
    started = time.perf_counter()
    subs = {f"{stream}-{run}": stream for stream in STREAMS}
    for sub, stream in subs.items():
        data = {"stream": stream, "params": {"q": q}, "start": 0, "end": FIRST_ROWS}
        await ws.send("subscribe", sub, **data)
    totals: dict[str, int] = {}
    rows = dict.fromkeys(subs, 0)
    while len(totals) < len(subs) or any(
        rows[sub] < min(FIRST_ROWS, totals[subs[sub]]) for sub in subs
    ):
        message = await ws.recv()
        sub = message.get("sub")
        if message["type"] == "snapshot_meta" and sub in subs:
            totals[subs[sub]] = message["data"]["total"]
        elif message["type"] == "chunk" and sub in subs:
            rows[sub] += len(message["data"]["rows"])
            await ws.send("ack", sub, chunk=message["data"]["chunk"])
    return time.perf_counter() - started, totals


async def test_search_meets_the_budget(
    settings: Settings, app: FastAPI, client: AsyncClient, engine: AsyncEngine
) -> None:
    if settings.is_sqlite:
        pytest.skip("performance budgets are measured on PostgreSQL")
    await seed_library(engine, TRACKS, reset=True)
    admin = await setup_admin(client)

    async with ws_connect(app) as ws:
        await ws.hello(admin.access_token)
        for q in QUERIES:
            first: list[float] = []
            scrolls: list[float] = []
            for run in range(RUNS):
                elapsed, totals = await _first_results(ws, q, run)
                first.append(elapsed)
                assert totals["search.tracks"] > 0, q

                # Scrolling further into the track results.
                sub = f"search.tracks-{run}"
                end = min(totals["search.tracks"], 5_000)
                started = time.perf_counter()
                await ws.send("window", sub, start=end - 100, end=end)
                await ws.recv_type("chunk", sub, wait=10)
                scrolls.append(time.perf_counter() - started)
                for stream in STREAMS:
                    await ws.send("unsubscribe", f"{stream}-{run}")

            p95_first = statistics.quantiles(first, n=20)[-1]
            p95_scroll = statistics.quantiles(scrolls, n=20)[-1]
            print(f"\n{q!r}: {totals}, first p95 {p95_first:.3f}s, scroll p95 {p95_scroll:.3f}s")
            assert p95_first <= FIRST_RESULTS_SECONDS, q
            assert p95_scroll <= INTERACTIVE_SECONDS, q
