"""WebSocket test client for the sync protocol."""

import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI
from httpx import AsyncClient
from httpx_ws import AsyncWebSocketSession, aconnect_ws
from httpx_ws.transport import ASGIWebSocketTransport
from sqlalchemy import insert

from anthology.users.models import Role, User

TIMEOUT = 3.0


class Ws:
    def __init__(self, session: AsyncWebSocketSession) -> None:
        self.session = session
        self.seen: list[dict[str, Any]] = []

    async def send(self, type_: str, sub: str | None = None, **data: Any) -> None:
        message: dict[str, Any] = {"type": type_, "data": data}
        if sub is not None:
            message["sub"] = sub
        await self.session.send_json(message)

    async def recv(self, wait: float = TIMEOUT) -> dict[str, Any]:
        message = await self.session.receive_json(timeout=wait)
        self.seen.append(message)
        return message

    async def recv_type(
        self, type_: str, sub: str | None = None, wait: float = TIMEOUT
    ) -> dict[str, Any]:
        """Receive until a message of ``type_`` (and ``sub``) arrives; others are kept."""
        while True:
            message = await self.recv(wait)
            if message["type"] == type_ and (sub is None or message.get("sub") == sub):
                return message

    async def hello(self, token: str, protocol: int = 1) -> dict[str, Any]:
        await self.send("hello", protocol=protocol, token=token)
        return await self.recv_type("welcome")

    async def subscribe(
        self,
        sub: str,
        stream: str,
        start: int = 0,
        end: int = 100,
        since: int | None = None,
        **params: Any,
    ) -> dict[str, Any]:
        data: dict[str, Any] = {"stream": stream, "params": params, "start": start, "end": end}
        if since is not None:
            data["since"] = since
        await self.send("subscribe", sub, **data)
        return await self.recv_type("snapshot_meta", sub)

    async def rows(self, sub: str, count: int, ack: bool = True) -> list[dict[str, Any]]:
        """Collect chunk rows until ``count`` rows arrived (acknowledging chunks)."""
        rows: list[dict[str, Any]] = []
        while len(rows) < count:
            chunk = await self.recv_type("chunk", sub)
            rows.extend(chunk["data"]["rows"])
            if ack:
                await self.send("ack", sub, chunk=chunk["data"]["chunk"])
        return rows


@asynccontextmanager
async def ws_connect(app: FastAPI, path: str = "/api/v1/ws") -> AsyncIterator[Ws]:
    transport = ASGIWebSocketTransport(app=app)
    async with (
        AsyncClient(transport=transport, base_url="http://test") as client,
        aconnect_ws(path, client, keepalive_ping_interval_seconds=None) as session,
    ):
        yield Ws(session)


async def insert_users(app: FastAPI, count: int, prefix: str = "user") -> list[str]:
    """Insert accounts directly (no Argon2) for list tests; returns the user names."""
    names = [f"{prefix}{index:05d}" for index in range(count)]
    rows = [
        {
            "id": uuid.uuid4(),
            "username": name,
            "display_name": name,
            "password_hash": None,
            "role": Role.LISTENER,
            "active": True,
        }
        for name in names
    ]
    async with app.state.engine.begin() as connection:
        await connection.execute(insert(User), rows)
    return names


async def admin_token(client: AsyncClient) -> str:
    from tests.users_helpers import setup_admin

    return (await setup_admin(client)).access_token
