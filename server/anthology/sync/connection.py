"""One WebSocket connection: subscriptions, windows, backpressure, deltas and token expiry."""

import asyncio
import contextlib
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from starlette.websockets import WebSocket

from anthology.core.changes import ChangeLog
from anthology.core.security import InvalidTokenError, decode_access_token
from anthology.db.types import utcnow
from anthology.sync import messages as m
from anthology.sync.anchors import Anchors
from anthology.sync.feed import ChangeEvent, event_from_row
from anthology.sync.streams import (
    Meta,
    RowChange,
    SortKey,
    Stream,
    StreamContext,
    StreamError,
    StreamRegistry,
)
from anthology.users.service import SessionCache, SessionInfo

logger = logging.getLogger(__name__)

CHUNK_SIZE = 200
MAX_UNACKED = 4
MAX_QUEUE = 5000

CLOSE_TOKEN_EXPIRED = 4401


@dataclass
class Subscription:
    id: str
    stream: Stream
    ctx: StreamContext
    anchors: Anchors
    threshold: int
    window: tuple[int, int] = (0, 0)
    next_chunk: int = 0
    unacked: set[int] = field(default_factory=set)
    acked: asyncio.Event = field(default_factory=asyncio.Event)
    pump: asyncio.Task | None = None
    ready: bool = False
    pending: list[m.Delta] = field(default_factory=list)


class Connection:
    def __init__(
        self,
        websocket: WebSocket,
        info: SessionInfo,
        expires_at: datetime,
        *,
        registry: StreamRegistry,
        sessionmaker: async_sessionmaker[AsyncSession],
        session_cache: SessionCache,
        token_key: bytes,
        feed_position: "FeedPosition",
    ) -> None:
        self.websocket = websocket
        self.info = info
        self._registry = registry
        self._sessionmaker = sessionmaker
        self._session_cache = session_cache
        self._token_key = token_key
        self._feed_position = feed_position
        self._queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self._subscriptions: dict[str, Subscription] = {}
        self._expires_at = expires_at
        self._tasks: list[asyncio.Task] = []
        self.closed = asyncio.Event()

    # --- lifecycle --------------------------------------------------------

    def start(self) -> None:
        self._tasks = [
            asyncio.create_task(self._writer(), name="ws-writer"),
            asyncio.create_task(self._expiry(), name="ws-expiry"),
        ]

    async def stop(self) -> None:
        for subscription in self._subscriptions.values():
            self._cancel_pump(subscription)
        for task in self._tasks:
            task.cancel()
        for task in self._tasks:
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await task

    async def close(self, code: int, reason: str = "") -> None:
        if self.closed.is_set():
            return
        self.closed.set()
        with contextlib.suppress(Exception):
            await self.websocket.close(code=code, reason=reason)

    def send(self, message: BaseModel) -> None:
        self._queue.put_nowait(message.model_dump(mode="json", exclude_none=True))

    def error(self, code: str, message: str = "", sub: str | None = None) -> None:
        self.send(m.Error(sub=sub, data=m.ErrorData(code=code, message=message)))

    async def _writer(self) -> None:
        while True:
            message = await self._queue.get()
            await self.websocket.send_json(message)

    async def _expiry(self) -> None:
        while True:
            delay = (self._expires_at - utcnow()).total_seconds()
            if delay <= 0:
                await self.close(CLOSE_TOKEN_EXPIRED, "token expired")
                return
            await asyncio.sleep(delay)

    # --- incoming messages ------------------------------------------------

    async def handle(self, message: Any) -> None:
        match message:
            case m.Auth():
                await self._auth(message.data.token)
            case m.Subscribe():
                await self._subscribe(message)
            case m.Window():
                subscription = self._subscriptions.get(message.sub)
                if subscription is None:
                    self.error("unknown_subscription", sub=message.sub)
                else:
                    self._set_window(subscription, message.data.clamp())
            case m.Ack():
                subscription = self._subscriptions.get(message.sub)
                if subscription is not None:
                    subscription.unacked.discard(message.data.chunk)
                    subscription.acked.set()
            case m.Unsubscribe():
                subscription = self._subscriptions.pop(message.sub, None)
                if subscription is not None:
                    self._cancel_pump(subscription)
            case m.Hello():
                self.error("already_authenticated")

    async def _auth(self, token: str) -> None:
        try:
            claims = decode_access_token(self._token_key, token)
        except InvalidTokenError:
            self.error("invalid_token")
            return
        info = await self._session_cache.get(claims.user_device_id)
        if info is None or claims.user_device_id != self.info.user_device_id:
            self.error("invalid_token")
            return
        self.info = info
        self._expires_at = claims.expires_at
        self._restart_expiry()

    def _restart_expiry(self) -> None:
        old = self._tasks.pop()
        old.cancel()
        self._tasks.append(asyncio.create_task(self._expiry(), name="ws-expiry"))

    # --- subscriptions ----------------------------------------------------

    async def _subscribe(self, message: m.Subscribe) -> None:
        data = message.data
        stream = self._registry.get(data.stream)
        if stream is None:
            self.error("unknown_stream", sub=message.sub)
            return
        if not stream.allowed(self.info):
            self.error("forbidden", sub=message.sub)
            return
        try:
            params = stream.validate(data.params)
        except StreamError as error:
            self.error(error.code, error.message, sub=message.sub)
            return

        previous = self._subscriptions.pop(message.sub, None)
        if previous is not None:
            self._cancel_pump(previous)

        ctx = StreamContext(session=self.info, params=params)
        subscription = Subscription(
            id=message.sub,
            stream=stream,
            ctx=ctx,
            anchors=Anchors(self._key_scanner(stream, ctx)),
            threshold=self._feed_position.last_seq,
        )
        # Registered before reading so that no change after `threshold` is missed;
        # deltas are buffered until the snapshot meta has been sent.
        self._subscriptions[message.sub] = subscription

        async with self._sessionmaker() as db:
            meta = await stream.meta(db, ctx)
            resync = data.since is not None and not await self._replayable(db, data.since)
            if resync:
                self.send(m.Resync(sub=message.sub))
            self._send_meta(subscription, meta)
            if data.since is not None and not resync:
                await self._replay(db, subscription, data.since)

        subscription.ready = True
        for delta in subscription.pending:
            self.send(delta)
        subscription.pending.clear()
        self._set_window(subscription, data.clamp())

    def _send_meta(self, subscription: Subscription, meta: Meta) -> None:
        self.send(
            m.SnapshotMeta(
                sub=subscription.id,
                seq=subscription.threshold,
                data=m.SnapshotMetaData(total=meta.total, counters=meta.counters),
            )
        )

    async def _replayable(self, db: AsyncSession, since: int) -> bool:
        oldest = await db.scalar(
            select(func.min(ChangeLog.change_seq)).where(ChangeLog.change_seq.is_not(None))
        )
        return oldest is None or since + 1 >= oldest

    async def _replay(self, db: AsyncSession, subscription: Subscription, since: int) -> None:
        rows = (
            await db.execute(
                select(ChangeLog)
                .where(
                    ChangeLog.change_seq > since,
                    ChangeLog.change_seq <= subscription.threshold,
                    ChangeLog.entity_type.in_(subscription.stream.entity_types),
                )
                .order_by(ChangeLog.change_seq)
            )
        ).scalars()
        latest: dict[tuple[str, Any], ChangeEvent] = {}
        for row in rows:
            event = event_from_row(row)
            if visible(event, self.info):
                latest[(event.entity_type, event.entity_id)] = event
        for event in sorted(latest.values(), key=lambda item: item.seq):
            await self.apply_event(db, subscription, event)

    def _key_scanner(self, stream: Stream, ctx: StreamContext):
        async def scan(after: SortKey | None, limit: int) -> list[SortKey]:
            async with self._sessionmaker() as db:
                return await stream.keys(db, ctx, after, limit)

        return scan

    # --- windows and chunks -----------------------------------------------

    def _set_window(self, subscription: Subscription, window: tuple[int, int]) -> None:
        self._cancel_pump(subscription)
        subscription.window = window
        subscription.unacked.clear()
        subscription.acked.set()
        subscription.pump = asyncio.create_task(self._pump(subscription), name="ws-pump")

    def _cancel_pump(self, subscription: Subscription) -> None:
        if subscription.pump is not None:
            subscription.pump.cancel()
            subscription.pump = None

    async def _pump(self, subscription: Subscription) -> None:
        start, end = subscription.window
        try:
            after, reachable = await subscription.anchors.start_key(start)
            position = start
            if not reachable:
                return
            async with self._sessionmaker() as db:
                while position < end:
                    rows = await subscription.stream.rows(
                        db, subscription.ctx, after, min(CHUNK_SIZE, end - position)
                    )
                    if not rows:
                        return
                    while len(subscription.unacked) >= MAX_UNACKED:
                        subscription.acked.clear()
                        await subscription.acked.wait()
                    number = subscription.next_chunk
                    subscription.next_chunk += 1
                    subscription.unacked.add(number)
                    self.send(
                        m.Chunk(
                            sub=subscription.id,
                            data=m.ChunkData(
                                chunk=number,
                                start=position,
                                rows=[row.payload() for row in rows],
                            ),
                        )
                    )
                    after = rows[-1].key
                    position += len(rows)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("chunk delivery failed for subscription %s", subscription.id)
            self.error("stream_failed", sub=subscription.id)

    # --- deltas -------------------------------------------------------------

    async def on_change(self, db: AsyncSession, event: ChangeEvent) -> None:
        """Called by the hub for every change feed event."""
        if event.entity_type in ("user", "user_device") and await self._session_revoked():
            await self.close(CLOSE_TOKEN_EXPIRED, "session revoked")
            return
        if not visible(event, self.info):
            return
        for subscription in list(self._subscriptions.values()):
            if event.seq > subscription.threshold and (
                event.entity_type in subscription.stream.entity_types
            ):
                await self.apply_event(db, subscription, event)

    async def _session_revoked(self) -> bool:
        return await self._session_cache.get(self.info.user_device_id) is None

    async def apply_event(
        self, db: AsyncSession, subscription: Subscription, event: ChangeEvent
    ) -> None:
        changes: list[RowChange] = await subscription.stream.changes(db, subscription.ctx, event)
        if not changes:
            return
        total = (await subscription.stream.meta(db, subscription.ctx)).total
        for change in changes:
            if change.key is not None:
                subscription.anchors.invalidate_from(change.key)
            delta = m.Delta(
                sub=subscription.id,
                seq=event.seq,
                data=m.DeltaData(
                    op=change.op,
                    id=change.id,
                    key=list(change.key) if change.key is not None else None,
                    row=change.row.payload() if change.row is not None else None,
                    total=total,
                ),
            )
            if not subscription.ready:
                subscription.pending.append(delta)
            elif self._queue.qsize() > MAX_QUEUE:
                await self._resync_all()
                return
            else:
                self.send(delta)

    async def _resync_all(self) -> None:
        """The client lags too far behind: drop everything queued, send fresh snapshots."""
        while not self._queue.empty():
            self._queue.get_nowait()
        async with self._sessionmaker() as db:
            for subscription in self._subscriptions.values():
                subscription.threshold = self._feed_position.last_seq
                subscription.anchors.reset()
                self.send(m.Resync(sub=subscription.id))
                meta = await subscription.stream.meta(db, subscription.ctx)
                self._send_meta(subscription, meta)
                self._set_window(subscription, subscription.window)


class FeedPosition:
    """Read access to the change feed position (the newest delivered change sequence)."""

    def __init__(self, feed) -> None:
        self._feed = feed

    @property
    def last_seq(self) -> int:
        return self._feed.last_seq or 0


def visible(event: ChangeEvent, info: SessionInfo) -> bool:
    match event.scope.value:
        case "user":
            return event.owner_user_id == info.user_id
        case "device":
            return event.device_id == info.device_id
        case _:
            return True
