"""Streams of playback (spec: playback, Play queue): ``playback.state`` (one row: the queue of
this device) and ``playback.queue`` (its entries in order). Both show the requesting user's
queue on the requesting device only."""

import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from anthology.library import streams as library
from anthology.library.models import Track
from anthology.library.schemas import LibraryTrackRow
from anthology.playback import service
from anthology.playback.models import PlayQueue, PlayQueueEntry
from anthology.playback.schemas import PlayQueueEntryRow, PlayQueueStateRow
from anthology.sync.feed import ChangeEvent
from anthology.sync.streams import (
    KeyQuery,
    Meta,
    Row,
    RowChange,
    SortKey,
    StreamContext,
    StreamError,
)
from anthology.users.service import SessionInfo

ENTRY_KEY = (PlayQueueEntry.position, PlayQueueEntry.id)


def _queue_id(ctx: StreamContext):
    session = ctx.session
    return (
        select(PlayQueue.id)
        .where(PlayQueue.user_id == session.user_id, PlayQueue.device_id == session.device_id)
        .scalar_subquery()
    )


def _data(model) -> dict[str, Any]:
    return model.model_dump(mode="json", exclude={"id", "key"})


async def _track_rows(db: AsyncSession, track_ids: list[uuid.UUID]) -> dict[uuid.UUID, Any]:
    if not track_ids:
        return {}
    result = await db.execute(
        library.TRACK_ROW.where(Track.id.in_(track_ids)).execution_options(populate_existing=True)
    )
    return {row[0].id: row for row in result}


def _track(result_row):
    return LibraryTrackRow.model_validate(library.track_row(result_row, ()).payload())


class QueueStream:
    name = "playback.queue"
    entity_types = frozenset({service.ENTRY, "track"})

    def allowed(self, session: SessionInfo) -> bool:
        return True

    def validate(self, params: dict[str, Any]) -> dict[str, Any]:
        # The generation only makes a rewritten queue a new subscription for the client.
        if set(params) - {"generation"}:
            raise StreamError("invalid_params", "only generation is allowed")
        return {"generation": str(params.get("generation", ""))}

    async def meta(self, db: AsyncSession, ctx: StreamContext) -> Meta:
        count = await db.scalar(
            select(func.count()).where(PlayQueueEntry.queue_id == _queue_id(ctx))
        )
        return Meta(total=count or 0)

    def key_query(self, ctx: StreamContext) -> KeyQuery:
        return KeyQuery(
            query=select(PlayQueueEntry).where(PlayQueueEntry.queue_id == _queue_id(ctx)),
            columns=ENTRY_KEY,
        )

    async def _rows(self, db: AsyncSession, entries: list[PlayQueueEntry]) -> list[Row]:
        tracks = await _track_rows(db, [entry.track_id for entry in entries])
        rows = []
        for entry in entries:
            track = tracks.get(entry.track_id)
            if track is None:
                continue
            key = (entry.position, entry.id)
            model = PlayQueueEntryRow(
                id=str(entry.id), key=list(key), position=entry.position, track=_track(track)
            )
            rows.append(Row(id=model.id, key=key, data=_data(model)))
        return rows

    async def rows(
        self, db: AsyncSession, ctx: StreamContext, after: SortKey | None, limit: int
    ) -> list[Row]:
        key_query = self.key_query(ctx)
        query = key_query.query
        condition = key_query.after(after)
        if condition is not None:
            query = query.where(condition)
        entries = list(
            await db.scalars(
                query.order_by(*key_query.ordering())
                .limit(limit)
                .execution_options(populate_existing=True)
            )
        )
        return await self._rows(db, entries)

    async def changes(
        self, db: AsyncSession, ctx: StreamContext, event: ChangeEvent
    ) -> list[RowChange]:
        base = select(PlayQueueEntry).where(PlayQueueEntry.queue_id == _queue_id(ctx))
        if event.entity_type == "track":
            entries = list(
                await db.scalars(
                    base.where(PlayQueueEntry.track_id == event.entity_id).execution_options(
                        populate_existing=True
                    )
                )
            )
            return [
                RowChange(op="upsert", id=row.id, key=row.key, row=row)
                for row in await self._rows(db, entries)
            ]
        entry_id = event.entity_id.int
        entry = await db.scalar(
            base.where(PlayQueueEntry.id == entry_id).execution_options(populate_existing=True)
        )
        rows = await self._rows(db, [entry]) if entry is not None else []
        if not rows:
            return [RowChange(op="remove", id=str(entry_id))]
        return [RowChange(op="upsert", id=rows[0].id, key=rows[0].key, row=rows[0])]


class StateStream:
    name = "playback.state"
    entity_types = frozenset({service.QUEUE, "track"})
    # Entry changes always come with a queue change entry (count, next entry).

    def allowed(self, session: SessionInfo) -> bool:
        return True

    def validate(self, params: dict[str, Any]) -> dict[str, Any]:
        if params:
            raise StreamError("invalid_params", "this stream takes no parameters")
        return {}

    async def _queue(self, db: AsyncSession, ctx: StreamContext) -> PlayQueue | None:
        return await db.scalar(
            select(PlayQueue)
            .where(
                PlayQueue.user_id == ctx.session.user_id,
                PlayQueue.device_id == ctx.session.device_id,
            )
            .execution_options(populate_existing=True)
        )

    async def meta(self, db: AsyncSession, ctx: StreamContext) -> Meta:
        return Meta(total=0 if await self._queue(db, ctx) is None else 1)

    def key_query(self, ctx: StreamContext) -> KeyQuery:
        session = ctx.session
        return KeyQuery(
            query=select(PlayQueue).where(
                PlayQueue.user_id == session.user_id, PlayQueue.device_id == session.device_id
            ),
            columns=(PlayQueue.id,),
        )

    async def _row(self, db: AsyncSession, queue: PlayQueue) -> Row:
        current = track = None
        if queue.current_entry_id is not None:
            current = await db.get(PlayQueueEntry, queue.current_entry_id, populate_existing=True)
        if current is not None:
            track = (await _track_rows(db, [current.track_id])).get(current.track_id)
        count = await db.scalar(select(func.count()).where(PlayQueueEntry.queue_id == queue.id))
        following = await service.neighbour(db, queue, 1) if current is not None else None
        model = PlayQueueStateRow(
            id=str(queue.id),
            key=[str(queue.id)],
            generation=str(queue.generation),
            current_entry_id=str(current.id) if current is not None else None,
            current=_track(track) if track is not None else None,
            next_entry_id=str(following) if following is not None else None,
            position_ms=queue.position_ms,
            playing=queue.playing,
            entries=count or 0,
            shortened=queue.shortened,
            updated_at=queue.updated_at,
        )
        return Row(id=model.id, key=(queue.id,), data=_data(model))

    async def rows(
        self, db: AsyncSession, ctx: StreamContext, after: SortKey | None, limit: int
    ) -> list[Row]:
        queue = await self._queue(db, ctx)
        if queue is None or after is not None or limit < 1:
            return []
        return [await self._row(db, queue)]

    async def changes(
        self, db: AsyncSession, ctx: StreamContext, event: ChangeEvent
    ) -> list[RowChange]:
        queue = await self._queue(db, ctx)
        if queue is None:
            return []
        if event.entity_type == service.QUEUE and event.entity_id != queue.id:
            return []
        if event.entity_type == "track":
            current = (
                await db.get(PlayQueueEntry, queue.current_entry_id)
                if queue.current_entry_id is not None
                else None
            )
            if current is None or current.track_id != event.entity_id:
                return []
        row = await self._row(db, queue)
        return [RowChange(op="upsert", id=row.id, key=row.key, row=row)]


STREAMS = (QueueStream, StateStream)
