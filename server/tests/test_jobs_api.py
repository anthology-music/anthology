"""Jobs over the API and the protocol: streams, live progress, control rights, demo job."""

import asyncio
from collections.abc import AsyncIterator

import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy import select

from anthology.api.app import create_app
from anthology.core.config import Settings
from anthology.jobs.models import Job, JobStatus
from anthology.sync.anchors import Anchors
from tests.users_helpers import Account, create_user, login, setup_admin
from tests.ws_helpers import ws_connect

pytestmark = pytest.mark.usefixtures("clean_db")


@pytest.fixture
async def demo_app(settings: Settings, engine) -> AsyncIterator[FastAPI]:
    app = create_app(settings.model_copy(update={"dev_demo": True, "jobs_throttle": "fast"}))
    async with app.router.lifespan_context(app):
        yield app


@pytest.fixture
async def demo_client(demo_app: FastAPI) -> AsyncIterator[AsyncClient]:
    from httpx import ASGITransport

    async with AsyncClient(transport=ASGITransport(app=demo_app), base_url="http://test") as client:
        yield client


async def start_demo(
    client: AsyncClient, account: Account, items: int = 4, seconds: float = 0.2
) -> dict:
    response = await client.post(
        "/api/v1/dev/jobs/demo",
        headers=account.headers,
        json={"items": items, "seconds_per_item": seconds},
    )
    assert response.status_code == 201, response.text
    return response.json()


async def wait_for(client: AsyncClient, account: Account, job_id: str, *statuses: str) -> dict:
    async with asyncio.timeout(10):
        while True:
            job = (await client.get(f"/api/v1/jobs/{job_id}", headers=account.headers)).json()
            if job["status"] in statuses:
                return job
            await asyncio.sleep(0.05)


# --- demo job and control rights -------------------------------------------------


async def test_demo_job_runs_to_the_end(demo_client: AsyncClient) -> None:
    admin = await setup_admin(demo_client)

    job = await start_demo(demo_client, admin, items=3, seconds=0.05)
    finished = await wait_for(demo_client, admin, job["id"], "done")

    assert finished["done_items"] == 3
    assert finished["progress"] == 1.0


async def test_demo_job_endpoint_exists_only_in_demo_mode(client: AsyncClient) -> None:
    admin = await setup_admin(client)

    response = await client.post("/api/v1/dev/jobs/demo", headers=admin.headers, json={})

    assert response.status_code == 404


async def test_listener_cannot_start_jobs(demo_client: AsyncClient) -> None:
    admin = await setup_admin(demo_client)
    await create_user(demo_client, admin, "kid")
    kid = await login(demo_client, "kid")

    response = await demo_client.post("/api/v1/dev/jobs/demo", headers=kid.headers, json={})

    assert response.status_code == 403


async def test_creator_pauses_resumes_and_cancels(demo_client: AsyncClient) -> None:
    admin = await setup_admin(demo_client)
    await create_user(demo_client, admin, "editor", role="editor")
    editor = await login(demo_client, "editor")
    job = await start_demo(demo_client, editor, items=20, seconds=0.2)
    await wait_for(demo_client, editor, job["id"], "running")

    paused = await demo_client.post(f"/api/v1/jobs/{job['id']}/pause", headers=editor.headers)
    resumed = await demo_client.post(f"/api/v1/jobs/{job['id']}/resume", headers=editor.headers)
    cancelled = await demo_client.post(f"/api/v1/jobs/{job['id']}/cancel", headers=editor.headers)

    assert paused.json()["status"] == "paused"
    assert resumed.json()["status"] == "queued"
    assert cancelled.json()["status"] == "cancelled"


async def test_other_editors_cannot_control_a_job_but_admins_can(
    demo_client: AsyncClient,
) -> None:
    admin = await setup_admin(demo_client)
    for name in ("owner", "other"):
        await create_user(demo_client, admin, name, role="editor")
    owner = await login(demo_client, "owner")
    other = await login(demo_client, "other")
    job = await start_demo(demo_client, owner, items=20, seconds=0.2)

    denied = await demo_client.post(f"/api/v1/jobs/{job['id']}/cancel", headers=other.headers)
    allowed = await demo_client.post(f"/api/v1/jobs/{job['id']}/cancel", headers=admin.headers)

    assert denied.status_code == 403
    assert allowed.status_code == 200
    assert allowed.json()["status"] == "cancelled"


async def test_resuming_a_running_job_is_rejected(demo_client: AsyncClient) -> None:
    admin = await setup_admin(demo_client)
    job = await start_demo(demo_client, admin, items=20, seconds=0.2)
    await wait_for(demo_client, admin, job["id"], "running")

    response = await demo_client.post(f"/api/v1/jobs/{job['id']}/resume", headers=admin.headers)

    assert response.status_code == 409
    assert response.json()["detail"] == "invalid_transition"
    await demo_client.post(f"/api/v1/jobs/{job['id']}/cancel", headers=admin.headers)


# --- streams ---------------------------------------------------------------------------


async def test_jobs_stream_shows_newest_first_with_creator_and_counters(
    demo_app: FastAPI, demo_client: AsyncClient
) -> None:
    admin = await setup_admin(demo_client)
    first = await start_demo(demo_client, admin, items=1, seconds=0.0)
    await wait_for(demo_client, admin, first["id"], "done")
    second = await start_demo(demo_client, admin, items=1, seconds=0.0)
    await wait_for(demo_client, admin, second["id"], "done")

    async with ws_connect(demo_app) as ws:
        await ws.hello(admin.access_token)
        meta = await ws.subscribe("jobs", "jobs")
        rows = await ws.rows("jobs", 2)

    assert meta["data"]["total"] == 2
    assert meta["data"]["counters"]["done"] == 2
    assert [row["id"] for row in rows] == [second["id"], first["id"]]
    assert rows[0]["created_by_name"] == "Admin"


async def test_progress_arrives_live_on_the_job_and_item_streams(
    demo_app: FastAPI, demo_client: AsyncClient
) -> None:
    admin = await setup_admin(demo_client)
    job = await start_demo(demo_client, admin, items=3, seconds=0.3)

    async with ws_connect(demo_app) as ws:
        await ws.hello(admin.access_token)
        await ws.subscribe("jobs", "jobs")
        await ws.subscribe("items", "job.items", job_id=job["id"])
        job_states: list[str] = []
        item_updates = 0
        async with asyncio.timeout(10):
            while "done" not in job_states:
                message = await ws.recv()
                if message["type"] != "delta":
                    continue
                if message["sub"] == "jobs":
                    job_states.append(message["data"]["row"]["status"])
                else:
                    item_updates += 1

    assert job_states[-1] == "done"
    assert item_updates >= 3


async def test_job_items_stream_requires_a_job_id(
    demo_app: FastAPI, demo_client: AsyncClient
) -> None:
    admin = await setup_admin(demo_client)

    async with ws_connect(demo_app) as ws:
        await ws.hello(admin.access_token)
        await ws.send("subscribe", "items", stream="job.items", params={}, start=0, end=10)
        error = await ws.recv_type("error")

    assert error["data"]["code"] == "invalid_params"


async def test_counters_follow_status_changes(demo_app: FastAPI, demo_client: AsyncClient):
    admin = await setup_admin(demo_client)
    job = await start_demo(demo_client, admin, items=20, seconds=0.2)
    await wait_for(demo_client, admin, job["id"], "running")
    await demo_client.post(f"/api/v1/jobs/{job['id']}/pause", headers=admin.headers)

    async with ws_connect(demo_app) as ws:
        await ws.hello(admin.access_token)
        meta = await ws.subscribe("jobs", "jobs")

    assert meta["data"]["counters"]["paused"] == 1
    assert meta["data"]["counters"]["running"] == 0
    async with demo_app.state.sessionmaker() as session:
        assert (await session.scalar(select(Job.status))) == JobStatus.PAUSED


# --- descending keys -------------------------------------------------------------------


async def test_descending_anchors_invalidate_in_list_order() -> None:
    rows = sorted(((index,) for index in range(5000)), reverse=True)

    async def keys(after, limit):
        start = 0 if after is None else next(i for i, row in enumerate(rows) if row < after)
        return rows[start : start + limit]

    async def anchor_scan(after, step, count):
        start = 0 if after is None else next(i for i, row in enumerate(rows) if row < after)
        return rows[start + step - 1 :: step][:count]

    anchors = Anchors(keys, anchor_scan, step=1000, anchor_batch=2, descending=True)
    assert await anchors.start_key(3000) == ((2000,), True)

    anchors.invalidate_from((3500,))  # a row near the top changed

    assert anchors._anchors == [None, (4000,)]
    assert await anchors.start_key(3000) == ((2000,), True)
