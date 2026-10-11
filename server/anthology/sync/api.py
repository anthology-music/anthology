"""WebSocket endpoint ``/api/v1/ws``."""

import asyncio
import contextlib
import json
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import ValidationError
from sqlalchemy import func, select

from anthology.core.changes import ChangeLog
from anthology.core.security import InvalidTokenError, decode_access_token
from anthology.sync import messages as m
from anthology.sync.connection import CLOSE_TOKEN_EXPIRED, Connection, FeedPosition

logger = logging.getLogger(__name__)

router = APIRouter()

CLOSE_BAD_HELLO = 4400
CLOSE_HELLO_TIMEOUT = 4408
CLOSE_UNSUPPORTED_PROTOCOL = 4426


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    state = websocket.app.state
    await websocket.accept()

    try:
        async with asyncio.timeout(state.settings.ws_hello_timeout_seconds):
            raw = await websocket.receive_text()
    except TimeoutError:
        await websocket.close(code=CLOSE_HELLO_TIMEOUT, reason="hello expected")
        return
    except WebSocketDisconnect:
        return

    try:
        hello = m.client_message.validate_json(raw)
    except ValidationError:
        hello = None
    if not isinstance(hello, m.Hello):
        await websocket.close(code=CLOSE_BAD_HELLO, reason="hello expected")
        return
    if hello.data.protocol not in m.SUPPORTED_PROTOCOLS:
        await websocket.close(code=CLOSE_UNSUPPORTED_PROTOCOL, reason="unsupported protocol")
        return
    try:
        claims = decode_access_token(state.token_key, hello.data.token)
    except InvalidTokenError:
        await websocket.close(code=CLOSE_TOKEN_EXPIRED, reason="invalid token")
        return
    info = await state.session_cache.get(claims.user_device_id)
    if info is None or info.user_id != claims.user_id:
        await websocket.close(code=CLOSE_TOKEN_EXPIRED, reason="session revoked")
        return

    connection = Connection(
        websocket,
        info,
        claims.expires_at,
        registry=state.streams,
        sessionmaker=state.sessionmaker,
        session_cache=state.session_cache,
        token_key=state.token_key,
        feed_position=FeedPosition(state.change_feed),
    )
    async with state.sessionmaker() as db:
        oldest = await db.scalar(
            select(func.min(ChangeLog.change_seq)).where(ChangeLog.change_seq.is_not(None))
        )
    connection.send(
        m.Welcome(
            data=m.WelcomeData(
                protocol=m.PROTOCOL_VERSION,
                current_seq=state.change_feed.last_seq or 0,
                oldest_seq=oldest,
            )
        )
    )
    connection.start()
    state.hub.add(connection)
    try:
        await _receive(websocket, connection)
    finally:
        state.hub.remove(connection)
        await connection.stop()


async def _receive(websocket: WebSocket, connection: Connection) -> None:
    closed = asyncio.create_task(connection.closed.wait())
    try:
        while True:
            receive = asyncio.create_task(websocket.receive_text())
            done, _ = await asyncio.wait({receive, closed}, return_when=asyncio.FIRST_COMPLETED)
            if closed in done:
                receive.cancel()
                return
            try:
                raw = receive.result()
            except WebSocketDisconnect:
                return
            try:
                message = m.client_message.validate_json(raw)
            except (ValidationError, json.JSONDecodeError) as error:
                connection.error("invalid_message", str(error).splitlines()[0])
                continue
            await connection.handle(message)
    finally:
        closed.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await closed
