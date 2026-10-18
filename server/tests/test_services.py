"""Service availability: monitor, stored status, stream and readiness (specs: tagging, sync)."""

import asyncio
from collections.abc import AsyncIterator

import httpx
import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from anthology.core.changes import ChangeLog
from anthology.core.services import (
    Observation,
    ServiceMonitor,
    ServiceState,
    ServiceStatus,
    store_status,
)
from anthology.tagging.tagger_client import TaggerClient, TaggerUnavailable, check_tagger
from tests.users_helpers import setup_admin
from tests.ws_helpers import ws_connect

pytestmark = pytest.mark.usefixtures("clean_db")


@pytest.fixture
def sessionmaker(engine: AsyncEngine) -> async_sessionmaker:
    return async_sessionmaker(engine, expire_on_commit=False)


async def stored(sessionmaker: async_sessionmaker, name: str = "tagger") -> ServiceStatus | None:
    async with sessionmaker() as session:
        return await session.get(ServiceStatus, name)


async def eventually(condition, seconds: float = 3.0) -> None:
    async with asyncio.timeout(seconds):
        for _ in iter(int, 1):
            if await condition():
                return
            await asyncio.sleep(0.02)


class Switch:
    """A service that can be switched on and off."""

    def __init__(self) -> None:
        self.up = False
        self.checks = 0

    async def check(self) -> Observation:
        self.checks += 1
        if not self.up:
            return Observation(ServiceState.UNAVAILABLE, message="connection refused")
        return Observation(ServiceState.AVAILABLE, version="0.1.0", interface="1.0")


@pytest.fixture
async def monitor(sessionmaker: async_sessionmaker) -> AsyncIterator[tuple[ServiceMonitor, Switch]]:
    switch = Switch()
    monitor = ServiceMonitor(
        "tagger", switch.check, sessionmaker, available_interval=60, retry_interval=0.05
    )
    await monitor.start()
    yield monitor, switch
    await monitor.stop()


async def test_server_starts_without_tagger_and_reports_it(app: FastAPI, client: AsyncClient):
    async def reported() -> bool:
        body = (await client.get("/api/v1/ready")).json()
        return body["services"].get("tagger") == "unavailable"

    await eventually(reported)
    assert (await client.get("/api/v1/health")).status_code == 200


async def test_tagger_coming_back_is_noticed_quickly(monitor, sessionmaker) -> None:
    service, switch = monitor

    async def down() -> bool:
        row = await stored(sessionmaker)
        return row is not None and row.status == ServiceState.UNAVAILABLE

    await eventually(down)
    switch.up = True

    async def up() -> bool:
        row = await stored(sessionmaker)
        return row is not None and row.status == ServiceState.AVAILABLE

    await eventually(up, seconds=1.0)
    assert service.state == ServiceState.AVAILABLE


async def test_failed_call_triggers_an_immediate_check(sessionmaker) -> None:
    switch = Switch()
    switch.up = True
    service = ServiceMonitor("tagger", switch.check, sessionmaker, available_interval=60)
    await service.start()
    try:
        await eventually(lambda: _true(switch.checks == 1))

        def refuse(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("refused", request=request)

        client = TaggerClient(
            "http://tagger",
            transport=httpx.MockTransport(refuse),
            on_unavailable=service.request_check,
        )
        with pytest.raises(TaggerUnavailable):
            await client.read(["/data/library/a.flac"])

        await eventually(lambda: _true(switch.checks == 2), seconds=1.0)
    finally:
        await service.stop()


async def _true(value: bool) -> bool:
    return value


async def test_incompatible_tagger_is_reported(sessionmaker) -> None:
    def health(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "status": "ok",
                "service": "anthology-tagger",
                "version": "9.0.0",
                "interface": "2.0",
            },
        )

    client = TaggerClient("http://tagger", transport=httpx.MockTransport(health))
    service = ServiceMonitor("tagger", lambda: check_tagger(client), sessionmaker)

    await service.check_now()

    row = await stored(sessionmaker)
    assert row is not None
    assert (row.status, row.interface, row.version) == (ServiceState.INCOMPATIBLE, "2.0", "9.0.0")


async def test_status_is_written_only_when_it_changes(sessionmaker) -> None:
    down = Observation(ServiceState.UNAVAILABLE, message="connection refused")
    up = Observation(ServiceState.AVAILABLE, version="0.1.0", interface="1.0")

    changed = [
        await store_status(sessionmaker, "tagger", seen) for seen in (down, down, up, up, down)
    ]

    assert changed == [True, False, True, False, True]
    async with sessionmaker() as session:
        entries = await session.scalar(
            select(func.count()).where(ChangeLog.entity_type == "service_status")
        )
    assert entries == 3


async def test_services_stream_shows_status_and_sends_deltas(
    app: FastAPI, client: AsyncClient, sessionmaker
) -> None:
    await app.state.tagger_monitor.stop()  # this test drives the status itself
    admin = await setup_admin(client)
    await store_status(sessionmaker, "tagger", Observation(ServiceState.UNAVAILABLE, message="x"))

    async with ws_connect(app) as ws:
        await ws.hello(admin.access_token)
        meta = await ws.subscribe("s", "services")
        [row] = await ws.rows("s", 1)
        await store_status(
            sessionmaker,
            "tagger",
            Observation(ServiceState.AVAILABLE, version="0.1.0", interface="1.0"),
        )
        # A delta may first repeat the snapshot state (numbered after the subscription).
        delta = await ws.recv_type("delta")
        while delta["data"]["row"]["status"] != "available":
            delta = await ws.recv_type("delta")

    assert meta["data"]["total"] == 1
    assert meta["data"]["counters"] == {"available": 0, "unavailable": 1, "incompatible": 0}
    assert (row["name"], row["status"]) == ("tagger", "unavailable")
    assert delta["data"]["row"]["status"] == "available"
    assert delta["data"]["row"]["interface"] == "1.0"
    assert delta["data"]["counters"]["available"] == 1
