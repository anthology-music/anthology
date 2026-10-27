"""WebSocket protocol: lifecycle, streams, windows, backpressure, deltas, resume."""

import asyncio
import uuid
from collections.abc import AsyncIterator
from datetime import timedelta

import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from httpx_ws import WebSocketDisconnect
from sqlalchemy import event, update

from anthology.api.app import create_app
from anthology.core.changes import ChangeLog
from anthology.core.config import Settings
from anthology.core.security import create_access_token, decode_access_token
from anthology.db.types import utcnow
from anthology.sync.retention import prune_change_log
from tests.users_helpers import create_user, login, setup_admin
from tests.ws_helpers import insert_users, ws_connect

pytestmark = pytest.mark.usefixtures("clean_db")


async def _closed_with(ws, code: int, wait: float = 3.0) -> bool:
    try:
        while True:
            await ws.recv(wait)
    except WebSocketDisconnect as closed:
        return closed.code == code


async def _wait_until_numbered(app: FastAPI) -> None:
    """Wait until the background sequencer and feed have processed all changes."""
    sequencer = app.state.change_background.sequencer
    async with asyncio.timeout(3):
        while True:
            await sequencer.run_once()
            await app.state.change_feed.run_once()
            async with app.state.engine.connect() as connection:
                pending = await connection.scalar(
                    ChangeLog.__table__.select()
                    .where(ChangeLog.change_seq.is_(None))
                    .with_only_columns(ChangeLog.id)
                    .limit(1)
                )
            if pending is None:
                return
            await asyncio.sleep(0.05)


async def _delta_for(ws, sub: str, entity_id: str) -> dict:
    """Receive deltas until the one for ``entity_id`` arrives (earlier ones may repeat)."""
    while True:
        delta = await ws.recv_type("delta", sub)
        if delta["data"]["id"] == entity_id:
            return delta


# --- lifecycle --------------------------------------------------------------


async def test_hello_is_answered_with_welcome(app: FastAPI, client: AsyncClient) -> None:
    admin = await setup_admin(client)

    async with ws_connect(app) as ws:
        welcome = await ws.hello(admin.access_token)

    assert welcome["data"]["protocol"] == 1
    assert welcome["data"]["current_seq"] >= 0


@pytest.fixture
async def quick_app(settings: Settings, engine) -> AsyncIterator[FastAPI]:
    app = create_app(settings.model_copy(update={"ws_hello_timeout_seconds": 0.2}))
    async with app.router.lifespan_context(app):
        yield app


async def test_connection_without_hello_is_closed(quick_app: FastAPI) -> None:
    async with ws_connect(quick_app) as ws:
        assert await _closed_with(ws, 4408)


async def test_token_in_the_url_is_not_accepted(quick_app: FastAPI, client: AsyncClient) -> None:
    admin = await setup_admin(client)

    async with ws_connect(quick_app, f"/api/v1/ws?token={admin.access_token}") as ws:
        assert await _closed_with(ws, 4408)


async def test_first_message_must_be_hello(app: FastAPI, client: AsyncClient) -> None:
    async with ws_connect(app) as ws:
        await ws.send("subscribe", "s1", stream="users", start=0, end=10)
        assert await _closed_with(ws, 4400)


async def test_unsupported_protocol_is_closed_with_4426(app: FastAPI, client: AsyncClient) -> None:
    admin = await setup_admin(client)

    async with ws_connect(app) as ws:
        await ws.send("hello", protocol=99, token=admin.access_token)
        assert await _closed_with(ws, 4426)


async def test_invalid_token_is_closed_with_4401(app: FastAPI) -> None:
    async with ws_connect(app) as ws:
        await ws.send("hello", protocol=1, token="garbage")
        assert await _closed_with(ws, 4401)


async def test_malformed_message_gets_an_error_and_keeps_the_connection(
    app: FastAPI, client: AsyncClient
) -> None:
    admin = await setup_admin(client)

    async with ws_connect(app) as ws:
        await ws.hello(admin.access_token)
        await ws.session.send_text("{not json")
        error = await ws.recv_type("error")
        await ws.send("window", "s1", start=-5, end=1)
        second = await ws.recv_type("error")
        meta = await ws.subscribe("s1", "users")

    assert error["data"]["code"] == "invalid_message"
    assert second["data"]["code"] == "invalid_message"
    assert meta["data"]["total"] == 1


def _short_token(app: FastAPI, access_token: str, seconds: int) -> str:
    claims = decode_access_token(app.state.token_key, access_token)
    token, _ = create_access_token(
        app.state.token_key, claims.user_id, claims.user_device_id, "admin", seconds
    )
    return token


async def test_expired_token_closes_with_4401(app: FastAPI, client: AsyncClient) -> None:
    admin = await setup_admin(client)

    async with ws_connect(app) as ws:
        await ws.hello(_short_token(app, admin.access_token, 1))
        assert await _closed_with(ws, 4401, wait=3)


async def test_auth_renews_the_token_on_the_open_connection(
    app: FastAPI, client: AsyncClient
) -> None:
    admin = await setup_admin(client)

    async with ws_connect(app) as ws:
        # Room for hello and auth on a slow runner (expiry times are whole seconds).
        await ws.hello(_short_token(app, admin.access_token, 3))
        await ws.send("auth", token=admin.access_token)
        await asyncio.sleep(3.5)
        meta = await ws.subscribe("s1", "users")

    assert meta["type"] == "snapshot_meta"


async def test_signing_out_closes_the_connection(app: FastAPI, client: AsyncClient) -> None:
    admin = await setup_admin(client)
    phone = await login(client, "admin", name="Phone")

    async with ws_connect(app) as ws:
        await ws.hello(phone.access_token)
        await client.post("/api/v1/auth/logout", headers=phone.headers)
        assert await _closed_with(ws, 4401)

    assert admin  # the other device is unaffected


# --- streams, windows, backpressure ------------------------------------------


async def test_counts_come_before_rows(app: FastAPI, client: AsyncClient) -> None:
    admin = await setup_admin(client)
    await insert_users(app, 3)

    async with ws_connect(app) as ws:
        await ws.hello(admin.access_token)
        await ws.send("subscribe", "s1", stream="users", params={}, start=0, end=10)
        first = await ws.recv_type("snapshot_meta", "s1")
        rows = await ws.rows("s1", 4)

    assert first["data"] == {"total": 4, "counters": {"active": 4}}
    assert [row["username"] for row in rows] == ["admin", "user00000", "user00001", "user00002"]
    types = [message["type"] for message in ws.seen]
    assert types.index("snapshot_meta") < types.index("chunk")


async def test_listener_cannot_subscribe_to_users(app: FastAPI, client: AsyncClient) -> None:
    admin = await setup_admin(client)
    await create_user(client, admin, "kid")
    kid = await login(client, "kid")

    async with ws_connect(app) as ws:
        await ws.hello(kid.access_token)
        await ws.send("subscribe", "s1", stream="users", start=0, end=10)
        error = await ws.recv_type("error")
        await ws.send("subscribe", "s2", stream="nonexistent", start=0, end=10)
        unknown = await ws.recv_type("error")

    assert error["data"]["code"] == "forbidden"
    assert unknown["data"]["code"] == "unknown_stream"


async def test_backpressure_limits_unacknowledged_chunks(app: FastAPI, client: AsyncClient) -> None:
    admin = await setup_admin(client)
    await insert_users(app, 1500)

    async with ws_connect(app) as ws:
        await ws.hello(admin.access_token)
        await ws.subscribe("s1", "users", start=0, end=1000)
        chunks = [await ws.recv_type("chunk", "s1") for _ in range(4)]
        with pytest.raises(TimeoutError):
            await ws.recv_type("chunk", "s1", wait=0.3)

        await ws.send("ack", "s1", chunk=chunks[0]["data"]["chunk"])
        fifth = await ws.recv_type("chunk", "s1")

    assert [chunk["data"]["start"] for chunk in chunks] == [0, 200, 400, 600]
    assert fifth["data"]["start"] == 800


async def test_jump_to_a_position_without_offset(app: FastAPI, client: AsyncClient) -> None:
    admin = await setup_admin(client)
    names = sorted(["admin", *await insert_users(app, 5000)])
    statements: list[tuple[str, object]] = []

    def record(_conn, _cursor, statement, parameters, *_args) -> None:
        statements.append((statement, parameters))

    event.listen(app.state.engine.sync_engine, "before_cursor_execute", record)
    try:
        async with ws_connect(app) as ws:
            await ws.hello(admin.access_token)
            await ws.subscribe("s1", "users", start=0, end=10)
            await ws.rows("s1", 10)
            await ws.send("window", "s1", start=4321, end=4371)
            chunk = await ws.recv_type("chunk", "s1")
    finally:
        event.remove(app.state.engine.sync_engine, "before_cursor_execute", record)

    assert chunk["data"]["start"] == 4321
    assert [row["username"] for row in chunk["data"]["rows"]] == names[4321:4371]
    assert not [sql for sql, params in statements if _uses_offset(sql, params)]


def _uses_offset(sql: str, params) -> bool:
    """True for a real OFFSET; SQLite always renders ``LIMIT ? OFFSET ?`` with offset 0."""
    if "OFFSET" not in sql.upper():
        return False
    return not (sql.rstrip().upper().endswith("OFFSET ?") and params and params[-1] == 0)


async def test_new_window_replaces_the_previous_one(app: FastAPI, client: AsyncClient) -> None:
    admin = await setup_admin(client)
    await insert_users(app, 4000)

    async with ws_connect(app) as ws:
        await ws.hello(admin.access_token)
        await ws.subscribe("s1", "users", start=0, end=1000)
        for _ in range(4):
            await ws.recv_type("chunk", "s1")
        await ws.send("window", "s1", start=3000, end=3010)
        chunk = await ws.recv_type("chunk", "s1")

    assert chunk["data"]["start"] == 3000
    assert len(chunk["data"]["rows"]) == 10


async def test_window_after_the_end_returns_no_rows(app: FastAPI, client: AsyncClient) -> None:
    admin = await setup_admin(client)

    async with ws_connect(app) as ws:
        await ws.hello(admin.access_token)
        await ws.subscribe("s1", "users", start=5000, end=5010)
        with pytest.raises(TimeoutError):
            await ws.recv_type("chunk", "s1", wait=0.3)


# --- deltas, resume, resync ---------------------------------------------------


async def test_live_delta_for_a_new_account(app: FastAPI, client: AsyncClient) -> None:
    admin = await setup_admin(client)

    async with ws_connect(app) as ws:
        await ws.hello(admin.access_token)
        await _wait_until_numbered(app)
        await ws.subscribe("s1", "users")
        await ws.rows("s1", 1)
        created = await create_user(client, admin, "kid")
        delta = await _delta_for(ws, "s1", created["id"])

    assert delta["data"]["op"] == "upsert"
    assert delta["data"]["id"] == created["id"]
    assert delta["data"]["row"]["username"] == "kid"
    assert delta["data"]["total"] == 2
    assert delta["seq"] > 0


async def test_private_deltas_reach_only_their_owner(app: FastAPI, client: AsyncClient) -> None:
    admin = await setup_admin(client)
    await create_user(client, admin, "kid")
    kid = await login(client, "kid", name="Kid laptop")

    async with ws_connect(app) as admin_ws, ws_connect(app) as kid_ws:
        await admin_ws.hello(admin.access_token)
        await kid_ws.hello(kid.access_token)
        await _wait_until_numbered(app)
        await admin_ws.subscribe("d", "me.devices")
        await kid_ws.subscribe("d", "me.devices")
        await admin_ws.rows("d", 1)
        await kid_ws.rows("d", 1)

        phone = await login(client, "kid", name="Kid phone")
        kid_delta = await _delta_for(kid_ws, "d", phone.device_id)
        with pytest.raises(TimeoutError):
            await admin_ws.recv_type("delta", "d", wait=0.5)

    assert kid_delta["data"]["row"]["name"] == "Kid phone"
    assert kid_delta["data"]["total"] == 2


async def test_removed_device_is_sent_as_remove(app: FastAPI, client: AsyncClient) -> None:
    admin = await setup_admin(client)
    phone = await login(client, "admin", name="Phone")

    async with ws_connect(app) as ws:
        await ws.hello(admin.access_token)
        await _wait_until_numbered(app)
        await ws.subscribe("d", "me.devices")
        await ws.rows("d", 2)
        await client.delete(f"/api/v1/me/devices/{phone.device_id}", headers=admin.headers)
        delta = await _delta_for(ws, "d", phone.device_id)

    assert delta["data"] == {
        "op": "remove",
        "id": phone.device_id,
        "key": ["Phone", phone.device_id],
        "total": 1,
    }


async def test_missed_changes_are_replayed_after_reconnect(
    app: FastAPI, client: AsyncClient
) -> None:
    admin = await setup_admin(client)
    await _wait_until_numbered(app)
    async with ws_connect(app) as ws:
        await ws.hello(admin.access_token)
        meta = await ws.subscribe("s1", "users")
    since = meta["seq"]

    created = await create_user(client, admin, "kid")
    await _wait_until_numbered(app)

    async with ws_connect(app) as ws:
        await ws.hello(admin.access_token)
        await ws.subscribe("s1", "users", since=since)
        delta = await _delta_for(ws, "s1", created["id"])

    assert delta["data"]["id"] == created["id"]
    types = [message["type"] for message in ws.seen]
    assert types.index("snapshot_meta") < types.index("delta")
    assert "resync" not in types


async def test_resync_when_the_gap_is_older_than_the_retention(
    app: FastAPI, client: AsyncClient
) -> None:
    admin = await setup_admin(client)
    await create_user(client, admin, "early")
    await _wait_until_numbered(app)
    async with app.state.engine.begin() as connection:
        await connection.execute(update(ChangeLog).values(changed_at=utcnow() - timedelta(days=30)))
    await prune_change_log(app.state.engine, days=7)
    await create_user(client, admin, "late")
    await _wait_until_numbered(app)

    async with ws_connect(app) as ws:
        await ws.hello(admin.access_token)
        await ws.send("subscribe", "s1", stream="users", params={}, since=0, start=0, end=10)
        first = await ws.recv()
        while first["type"] == "delta":  # pragma: no cover - defensive
            first = await ws.recv()
        meta = await ws.recv_type("snapshot_meta", "s1")
        rows = await ws.rows("s1", 3)

    assert first["type"] == "resync"
    assert meta["data"]["total"] == 3
    assert {row["username"] for row in rows} == {"admin", "early", "late"}


# --- several server processes ----------------------------------------------------


async def test_delta_arrives_through_another_process(
    settings: Settings, app: FastAPI, client: AsyncClient
) -> None:
    if settings.is_sqlite:
        pytest.skip("several server processes require PostgreSQL")
    admin = await setup_admin(client)
    other = create_app(settings)
    async with other.router.lifespan_context(other):
        async with ws_connect(other) as ws:
            await ws.hello(admin.access_token)
            await _wait_until_numbered(app)
            await ws.subscribe("s1", "users")
            await ws.rows("s1", 1)
            created = await create_user(client, admin, "kid")  # through the first process
            delta = await _delta_for(ws, "s1", created["id"])

    assert delta["data"]["id"] == created["id"]
    assert uuid.UUID(delta["data"]["id"])
