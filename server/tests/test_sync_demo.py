"""Developer demo stream and the protocol performance budget (change sync-demo-stream)."""

import statistics
import time
from collections.abc import AsyncIterator

import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncEngine

from anthology.api.app import create_app
from anthology.cli import seed_demo
from anthology.core.config import Settings
from anthology.sync.demo import demo_items, generate, seed
from tests.users_helpers import setup_admin
from tests.ws_helpers import ws_connect

pytestmark = pytest.mark.usefixtures("clean_db")

BUDGET_SECONDS = 2.0
PERFORMANCE_ROWS = 500_000


@pytest.fixture
async def demo_app(settings: Settings, engine: AsyncEngine) -> AsyncIterator[FastAPI]:
    app = create_app(settings.model_copy(update={"dev_demo": True}))
    async with app.router.lifespan_context(app):
        yield app


async def _count(engine: AsyncEngine) -> int:
    async with engine.connect() as connection:
        return await connection.scalar(select(func.count()).select_from(demo_items))


def test_seeding_is_refused_without_the_flag(settings: Settings) -> None:
    assert seed_demo(settings.model_copy(update={"dev_demo": False}), 10, reset=False) == 1


def test_generated_rows_are_deterministic() -> None:
    assert generate(50) == generate(50)
    assert len({row["id"] for row in generate(1000)}) == 1000


async def test_seeding_creates_the_requested_rows_once(engine: AsyncEngine) -> None:
    assert await seed(engine, 10_000, reset=True) == 10_000
    assert await _count(engine) == 10_000

    assert await seed(engine, 10_000) == 0
    assert await _count(engine) == 10_000


async def test_demo_stream_is_not_available_without_the_flag(
    app: FastAPI, client: AsyncClient
) -> None:
    admin = await setup_admin(client)

    async with ws_connect(app) as ws:
        await ws.hello(admin.access_token)
        await ws.send("subscribe", "s1", stream="demo.items", start=0, end=10)
        error = await ws.recv_type("error")

    assert error["data"]["code"] == "unknown_stream"


async def test_demo_stream_serves_sorted_rows(demo_app: FastAPI, engine: AsyncEngine) -> None:
    await seed(engine, 10_000, reset=True)
    transport_client = AsyncClient(transport=_asgi(demo_app), base_url="http://test")
    async with transport_client as client:
        admin = await setup_admin(client)

    async with ws_connect(demo_app) as ws:
        await ws.hello(admin.access_token)
        meta = await ws.subscribe("s1", "demo.items", start=0, end=200)
        rows = await ws.rows("s1", 200)

    assert meta["data"]["total"] == 10_000
    keys = [(row["key"][0], row["key"][1], row["key"][2]) for row in rows]
    assert keys == sorted(keys)
    assert {"artist", "title", "year"} <= set(rows[0])


def _asgi(app: FastAPI):
    from httpx import ASGITransport

    return ASGITransport(app=app)


# --- performance budget -----------------------------------------------------------


@pytest.mark.performance
async def test_large_list_meets_the_interaction_budget(
    settings: Settings, demo_app: FastAPI, engine: AsyncEngine
) -> None:
    if settings.is_sqlite:
        pytest.skip("performance budgets are measured on PostgreSQL")
    await seed(engine, PERFORMANCE_ROWS)
    async with AsyncClient(transport=_asgi(demo_app), base_url="http://test") as client:
        admin = await setup_admin(client)

    first_window: list[float] = []
    jumps: list[float] = []
    for _ in range(5):
        async with ws_connect(demo_app) as ws:
            await ws.hello(admin.access_token)

            started = time.perf_counter()
            meta = await ws.subscribe("s1", "demo.items", start=0, end=100)
            await ws.rows("s1", 100)
            first_window.append(time.perf_counter() - started)

            started = time.perf_counter()
            await ws.send("window", "s1", start=250_000, end=250_100)
            chunk = await ws.recv_type("chunk", "s1", wait=10)
            jumps.append(time.perf_counter() - started)

        assert meta["data"]["total"] == PERFORMANCE_ROWS
        assert chunk["data"]["start"] == 250_000

    p95_first = statistics.quantiles(first_window, n=20)[-1]
    p95_jump = statistics.quantiles(jumps, n=20)[-1]
    print(f"\nfirst window p95 {p95_first:.3f}s, jump p95 {p95_jump:.3f}s")
    assert p95_first <= BUDGET_SECONDS
    assert p95_jump <= BUDGET_SECONDS
