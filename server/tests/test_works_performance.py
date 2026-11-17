"""The works list and a medley page with 20,000 works (spec: works, Works list; interaction
budget)."""

import statistics
import time
import uuid

import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy import insert

from anthology.core.config import Settings
from anthology.db.types import utcnow
from anthology.library.service import sort_key
from anthology.works.models import Work, WorkCounter, WorkRelation, WorkType
from tests.users_helpers import setup_admin
from tests.ws_helpers import ws_connect

pytestmark = [pytest.mark.performance, pytest.mark.usefixtures("clean_db")]

BUDGET_SECONDS = 2.0
WORKS = 20_000
RUNS = 5


async def _works(app: FastAPI) -> uuid.UUID:
    """Generated works (fictional titles); the first is a medley of the next 200."""
    now = utcnow()
    rows = []
    for index in range(WORKS):
        title = f"Werk {index:05d}"
        work_type = WorkType.MEDLEY if index == 0 else WorkType.ORIGINAL
        rows.append(
            {
                "id": uuid.uuid4(),
                "title": title,
                "sort_title": sort_key(title),
                "type": work_type,
                "created_at": now,
                "updated_at": now,
            }
        )
    async with app.state.sessionmaker() as session, session.begin():
        await session.execute(insert(Work), rows)
        await session.execute(
            insert(WorkRelation),
            [
                {
                    "id": uuid.uuid4(),
                    "source_work_id": rows[0]["id"],
                    "target_work_id": row["id"],
                    "type": "medley_contains",
                    "position": position,
                    "origin": "user",
                }
                for position, row in enumerate(rows[1:201])
            ],
        )
        await session.execute(
            insert(WorkCounter),
            [
                {"name": "all", "value": WORKS},
                {"name": "medley", "value": 1},
                {"name": "original", "value": WORKS - 1},
            ],
        )
    return rows[0]["id"]


async def test_the_works_list_meets_the_budget(
    settings: Settings, app: FastAPI, client: AsyncClient
) -> None:
    if settings.is_sqlite:
        pytest.skip("performance budgets are measured on PostgreSQL")
    medley = await _works(app)
    admin = await setup_admin(client)
    for stream, params, total in (
        ("works.list", {}, WORKS),
        ("works.list", {"type": "original"}, WORKS - 1),
        ("works.work.contents", {"work_id": str(medley)}, 200),
    ):
        firsts: list[float] = []
        for run in range(RUNS):
            async with ws_connect(app) as ws:
                await ws.hello(admin.access_token)
                started = time.perf_counter()
                meta = await ws.subscribe(f"w{run}", stream, **params)
                await ws.rows(f"w{run}", 100)
                firsts.append(time.perf_counter() - started)
            assert meta["data"]["total"] == total
        p95 = statistics.quantiles(firsts, n=20)[-1]
        print(f"\n{stream} {params}: count and first rows p95 {p95:.3f}s")
        assert p95 <= BUDGET_SECONDS
