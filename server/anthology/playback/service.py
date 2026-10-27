"""Play queues (spec: playback, Play queue, Starting playback, Resume).

One queue per user and device. Entries are ordered by an integer key: a new queue numbers
them ``GAP`` apart, insertions take the room between two entries, and when there is none the
queue is renumbered. Rewriting the queue as a whole (replace, renumber, clear) changes its
``generation``: clients subscribe to the entries of one generation, so the rewrite needs one
change entry instead of one per entry.
"""

import uuid
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any, Literal

from sqlalchemy import (
    ColumnElement,
    Select,
    case,
    delete,
    event,
    func,
    insert,
    literal,
    select,
    text,
    update,
)
from sqlalchemy import Uuid as UuidType
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from anthology.core.changes import (
    ChangeLog,
    ChangeOperation,
    ChangeScope,
    add_change_listener,
    record_change,
    record_changes,
)
from anthology.db.types import utcnow
from anthology.library.models import Recording, Release, Track
from anthology.playback.models import GAP, MAX_ENTRIES, PlayQueue, PlayQueueEntry
from anthology.search import service as search

QUEUE = "play_queue"
ENTRY = "play_queue_entry"

Mode = Literal["replace", "next", "append"]


class QueueError(ValueError):
    """An operation on an entry that is not in the device's queue."""


@dataclass(frozen=True)
class Started:
    entries: int
    shortened: bool


# --- queues and change entries ------------------------------------------------------------


async def queue_of(session: AsyncSession, user_id: uuid.UUID, device_id: uuid.UUID) -> PlayQueue:
    """The device's queue, created on first use, locked for this transaction."""
    query = (
        select(PlayQueue)
        .where(PlayQueue.user_id == user_id, PlayQueue.device_id == device_id)
        .with_for_update()
    )
    queue = await session.scalar(query)
    if queue is None:
        queue = PlayQueue(user_id=user_id, device_id=device_id)
        session.add(queue)
        await session.flush()
    return queue


async def find_queue(
    session: AsyncSession, user_id: uuid.UUID, device_id: uuid.UUID
) -> PlayQueue | None:
    return await session.scalar(
        select(PlayQueue).where(PlayQueue.user_id == user_id, PlayQueue.device_id == device_id)
    )


async def _queue_changed(session: AsyncSession, queue: PlayQueue) -> None:
    queue.updated_at = utcnow()
    await session.flush()
    await record_change(
        session,
        entity_type=QUEUE,
        entity_id=queue.id,
        operation=ChangeOperation.UPDATE,
        scope=ChangeScope.USER,
        owner_user_id=queue.user_id,
    )


def entry_uuid(entry_id: int) -> uuid.UUID:
    """Change entries name entities by UUID; entries have integer IDs."""
    return uuid.UUID(int=entry_id)


async def _entries_changed(
    session: AsyncSession, queue: PlayQueue, ids: Iterable[int], operation: ChangeOperation
) -> None:
    await record_changes(
        session,
        entity_type=ENTRY,
        entity_ids=[entry_uuid(entry_id) for entry_id in ids],
        operation=operation,
        scope=ChangeScope.USER,
        owner_user_id=queue.user_id,
    )


def _rewritten(queue: PlayQueue) -> None:
    queue.generation = uuid.uuid4()


# --- tracks of a selection in list order --------------------------------------------------


def _ordered(rule: dict[str, Any], postgresql: bool) -> tuple[Select, list[ColumnElement]]:
    """The tracks of a list rule (one column ``track_id``) and the list's order."""
    match rule["list"]:
        case "release_tracks":
            query = select(Track.id.label("track_id")).where(
                Track.release_id == uuid.UUID(rule["release_id"])
            )
            return query, [Track.disc_number, Track.track_number, Track.id]
        case "artist_tracks":
            query = (
                select(Track.id.label("track_id"))
                .join(Recording, Recording.id == Track.recording_id)
                .join(Release, Release.id == Track.release_id)
                .where(Recording.artist_id == uuid.UUID(rule["artist_id"]))
            )
            return query, [
                Release.sort_title,
                Release.id,
                Track.disc_number,
                Track.track_number,
                Track.id,
            ]
        case "search":
            release_id, artist_id = rule.get("release_id"), rule.get("artist_id")
            return search.ordered(
                rule["q"],
                postgresql=postgresql,
                release_id=uuid.UUID(release_id) if release_id else None,
                artist_id=uuid.UUID(artist_id) if artist_id else None,
            )
    return select(Track.id.label("track_id")), [
        Track.sort_artist,
        Track.sort_title,
        Track.sort_album,
        Track.id,
    ]


def _ranked(rule: dict[str, Any], postgresql: bool):
    query, order = _ordered(rule, postgresql)
    track_id = query.selected_columns[0]
    return query.with_only_columns(
        track_id.label("track_id"), func.row_number().over(order_by=order).label("rn")
    ).subquery()


async def _existing(session: AsyncSession, ids: list[uuid.UUID]) -> list[uuid.UUID]:
    """``ids`` that are tracks, in the given order without repeats."""
    found = set(await session.scalars(select(Track.id).where(Track.id.in_(ids))))
    return [track_id for track_id in dict.fromkeys(ids) if track_id in found]


# --- starting playback --------------------------------------------------------------------


async def start(
    session: AsyncSession,
    queue: PlayQueue,
    *,
    mode: Mode,
    ids: list[uuid.UUID] | None = None,
    rule: dict[str, Any] | None = None,
    start_track: uuid.UUID | None = None,
) -> Started:
    """Replace the queue with a list (from ``start_track``), or insert it after the current
    entry (``next``) or at the end (``append``)."""
    postgresql = search.postgresql(session)
    if mode == "replace":
        return await _replace(session, queue, ids, rule, start_track, postgresql)
    return await _insert(session, queue, mode, ids, rule, postgresql)


async def _replace(session, queue, ids, rule, start_track, postgresql) -> Started:
    await session.execute(delete(PlayQueueEntry).where(PlayQueueEntry.queue_id == queue.id))
    shortened = False
    current_position = GAP
    if ids is not None:
        tracks = await _existing(session, ids)
        first = tracks.index(start_track) if start_track in tracks else 0
        if len(tracks) > MAX_ENTRIES:
            tracks, first, shortened = tracks[first : first + MAX_ENTRIES], 0, True
        if tracks:
            await session.execute(
                insert(PlayQueueEntry),
                [
                    {"queue_id": queue.id, "track_id": track_id, "position": (index + 1) * GAP}
                    for index, track_id in enumerate(tracks)
                ],
            )
        current_position = (first + 1) * GAP
        count = len(tracks)
    else:
        ranked = _ranked(rule, postgresql)
        total = await session.scalar(select(func.count()).select_from(ranked)) or 0
        start_rn = 1
        if start_track is not None:
            start_rn = (
                await session.scalar(
                    select(func.min(ranked.c.rn)).where(ranked.c.track_id == start_track)
                )
                or 1
            )
        offset = 1
        if total > MAX_ENTRIES:
            offset, shortened = start_rn, True
        await session.execute(
            insert(PlayQueueEntry).from_select(
                ["queue_id", "track_id", "position"],
                select(
                    literal(queue.id, UuidType()),
                    ranked.c.track_id,
                    (ranked.c.rn - offset + 1) * GAP,
                ).where(ranked.c.rn >= offset, ranked.c.rn < offset + MAX_ENTRIES),
            )
        )
        current_position = (start_rn - offset + 1) * GAP
        count = min(total - offset + 1, MAX_ENTRIES)
    queue.current_entry_id = await session.scalar(
        select(PlayQueueEntry.id).where(
            PlayQueueEntry.queue_id == queue.id, PlayQueueEntry.position == current_position
        )
    )
    queue.position_ms = 0
    queue.playing = queue.current_entry_id is not None
    queue.shortened = shortened
    _rewritten(queue)
    await _queue_changed(session, queue)
    return Started(entries=max(count, 0), shortened=shortened)


async def _renumber(session: AsyncSession, queue: PlayQueue, hole_after: int, hole: int) -> None:
    """Number the entries ``GAP`` apart, leaving ``hole`` free keys after position
    ``hole_after`` (one statement; a new generation)."""
    ranked = (
        select(
            PlayQueueEntry.id.label("entry_id"),
            PlayQueueEntry.position.label("old"),
            func.row_number()
            .over(order_by=[PlayQueueEntry.position, PlayQueueEntry.id])
            .label("rn"),
        )
        .where(PlayQueueEntry.queue_id == queue.id)
        .subquery()
    )
    new_position = (ranked.c.rn + case((ranked.c.old > hole_after, hole), else_=0)) * GAP
    await session.execute(
        update(PlayQueueEntry)
        .where(PlayQueueEntry.id == ranked.c.entry_id)
        .values(position=new_position)
        .execution_options(synchronize_session=False)
    )
    _rewritten(queue)


async def _neighbours(
    session: AsyncSession, queue: PlayQueue, anchor: int | None
) -> tuple[int, int | None]:
    """The key of the anchor entry (0 before the first) and of its successor."""
    position = 0
    if anchor is not None:
        position = await session.scalar(
            select(PlayQueueEntry.position).where(PlayQueueEntry.id == anchor)
        )
    successor = await session.scalar(
        select(func.min(PlayQueueEntry.position)).where(
            PlayQueueEntry.queue_id == queue.id, PlayQueueEntry.position > position
        )
    )
    return position, successor


async def _room(
    session: AsyncSession, queue: PlayQueue, anchor: int | None, count: int
) -> tuple[int, int]:
    """First key and step for ``count`` entries after ``anchor``; renumbers if needed."""
    position, successor = await _neighbours(session, queue, anchor)
    if successor is None:
        return position + GAP, GAP
    if successor - position > count:
        step = (successor - position) // (count + 1)
        return position + step, step
    await _renumber(session, queue, position, count)
    position, _successor = await _neighbours(session, queue, anchor)
    return position + GAP, GAP


async def _insert(session, queue, mode, ids, rule, postgresql) -> Started:
    present = (
        await session.scalar(select(func.count()).where(PlayQueueEntry.queue_id == queue.id)) or 0
    )
    room = MAX_ENTRIES - present
    if ids is not None:
        tracks = await _existing(session, ids)
        requested = len(tracks)
        tracks = tracks[: max(room, 0)]
        count = len(tracks)
    else:
        ranked = _ranked(rule, postgresql)
        requested = await session.scalar(select(func.count()).select_from(ranked)) or 0
        count = min(requested, max(room, 0))
    if count == 0:
        return Started(entries=0, shortened=requested > 0)

    anchor = queue.current_entry_id if mode == "next" else None
    if mode == "append":
        anchor = await session.scalar(
            select(PlayQueueEntry.id)
            .where(PlayQueueEntry.queue_id == queue.id)
            .order_by(PlayQueueEntry.position.desc(), PlayQueueEntry.id.desc())
            .limit(1)
        )
    generation = queue.generation
    first, step = await _room(session, queue, anchor, count)
    if ids is not None:
        await session.execute(
            insert(PlayQueueEntry),
            [
                {"queue_id": queue.id, "track_id": track_id, "position": first + index * step}
                for index, track_id in enumerate(tracks)
            ],
        )
    else:
        await session.execute(
            insert(PlayQueueEntry).from_select(
                ["queue_id", "track_id", "position"],
                select(
                    literal(queue.id, UuidType()),
                    ranked.c.track_id,
                    first + (ranked.c.rn - 1) * step,
                ).where(ranked.c.rn <= count),
            )
        )
    inserted = list(
        await session.scalars(
            select(PlayQueueEntry.id)
            .where(
                PlayQueueEntry.queue_id == queue.id,
                PlayQueueEntry.position >= first,
                PlayQueueEntry.position <= first + (count - 1) * step,
            )
            .order_by(PlayQueueEntry.position)
        )
    )
    if queue.current_entry_id is None:
        queue.current_entry_id = inserted[0]
        queue.position_ms = 0
    queue.shortened = count < requested
    if queue.generation == generation:
        await _entries_changed(session, queue, inserted, ChangeOperation.INSERT)
    await _queue_changed(session, queue)
    return Started(entries=count, shortened=count < requested)


# --- state and entries --------------------------------------------------------------------


async def _entry(session: AsyncSession, queue: PlayQueue, entry_id: int) -> PlayQueueEntry:
    entry = await session.get(PlayQueueEntry, entry_id)
    if entry is None or entry.queue_id != queue.id:
        raise QueueError("not an entry of this queue")
    return entry


async def set_state(
    session: AsyncSession,
    queue: PlayQueue,
    *,
    current_entry_id: int | None,
    position_ms: int,
    playing: bool,
) -> None:
    if current_entry_id is not None:
        await _entry(session, queue, current_entry_id)
    queue.current_entry_id = current_entry_id
    queue.position_ms = max(position_ms, 0)
    queue.playing = playing and current_entry_id is not None
    await _queue_changed(session, queue)


async def _successor(session: AsyncSession, entry: PlayQueueEntry) -> int | None:
    return await session.scalar(
        select(PlayQueueEntry.id)
        .where(
            PlayQueueEntry.queue_id == entry.queue_id,
            PlayQueueEntry.position > entry.position,
        )
        .order_by(PlayQueueEntry.position, PlayQueueEntry.id)
        .limit(1)
    )


async def _predecessor(session: AsyncSession, entry: PlayQueueEntry) -> int | None:
    return await session.scalar(
        select(PlayQueueEntry.id)
        .where(
            PlayQueueEntry.queue_id == entry.queue_id,
            PlayQueueEntry.position < entry.position,
        )
        .order_by(PlayQueueEntry.position.desc(), PlayQueueEntry.id.desc())
        .limit(1)
    )


async def neighbour(session: AsyncSession, queue: PlayQueue, by: int) -> int | None:
    """The entry after (``by`` = 1) or before (-1) the current one."""
    if queue.current_entry_id is None:
        return None
    entry = await session.get(PlayQueueEntry, queue.current_entry_id)
    if entry is None:
        return None
    return await (_successor if by > 0 else _predecessor)(session, entry)


async def skip(session: AsyncSession, queue: PlayQueue, by: int) -> int | None:
    """Make the next (1) or previous (-1) entry current from its start; at the end of the
    queue playback stops on the last entry. Returns the new current entry."""
    target = await neighbour(session, queue, by)
    if target is None:
        if by > 0:
            queue.playing = False
        await _queue_changed(session, queue)
        return queue.current_entry_id
    queue.current_entry_id = target
    queue.position_ms = 0
    await _queue_changed(session, queue)
    return target


async def remove(session: AsyncSession, queue: PlayQueue, entry_id: int) -> None:
    """Remove an entry; removing the current one makes its successor current."""
    entry = await _entry(session, queue, entry_id)
    if queue.current_entry_id == entry.id:
        queue.current_entry_id = await _successor(session, entry)
        queue.position_ms = 0
        queue.playing = queue.playing and queue.current_entry_id is not None
    await session.delete(entry)
    await session.flush()
    await _entries_changed(session, queue, [entry_id], ChangeOperation.DELETE)
    await _queue_changed(session, queue)


async def move(session: AsyncSession, queue: PlayQueue, entry_id: int, after: int | None) -> None:
    """Move an entry behind ``after`` (None: to the front)."""
    entry = await _entry(session, queue, entry_id)
    if after is not None:
        await _entry(session, queue, after)
    if after == entry.id:
        return
    # Out of the way first, so that the room is computed without it.
    entry.position = -1
    await session.flush()
    generation = queue.generation
    first, _step = await _room(session, queue, after, 1)
    entry.position = first
    await session.flush()
    if queue.generation == generation:
        await _entries_changed(session, queue, [entry.id], ChangeOperation.UPDATE)
    await _queue_changed(session, queue)


async def clear(session: AsyncSession, queue: PlayQueue) -> None:
    await session.execute(delete(PlayQueueEntry).where(PlayQueueEntry.queue_id == queue.id))
    queue.current_entry_id = None
    queue.position_ms = 0
    queue.playing = False
    queue.shortened = False
    _rewritten(queue)
    await _queue_changed(session, queue)


# --- entries of deleted tracks ------------------------------------------------------------

_DELETED = "playback.tracks"


def _collect(session: AsyncSession, entity_type: str, entity_ids: list[uuid.UUID]) -> None:
    if entity_type == "track":
        session.info.setdefault(_DELETED, set()).update(entity_ids)


def _remove_deleted(session: Session) -> None:
    """Before the commit: entries of tracks that no longer exist leave their queues, with the
    change entries a cascade could not write (synchronous: ``before_commit``)."""
    ids = session.info.pop(_DELETED, None)
    if not ids:
        return
    rows = session.execute(
        select(PlayQueueEntry.id, PlayQueueEntry.queue_id, PlayQueue.user_id)
        .join(PlayQueue, PlayQueue.id == PlayQueueEntry.queue_id)
        .where(
            PlayQueueEntry.track_id.in_(ids),
            ~select(Track.id).where(Track.id == PlayQueueEntry.track_id).exists(),
        )
    ).all()
    if not rows:
        return
    entry_ids = [row.id for row in rows]
    session.execute(delete(PlayQueueEntry).where(PlayQueueEntry.id.in_(entry_ids)))
    owners = {row.queue_id: row.user_id for row in rows}
    affected = list(
        session.execute(
            select(PlayQueue.id).where(
                PlayQueue.id.in_(owners), PlayQueue.current_entry_id.in_(entry_ids)
            )
        ).scalars()
    )
    if affected:
        session.execute(
            update(PlayQueue)
            .where(PlayQueue.id.in_(affected))
            .values(current_entry_id=None, playing=False, position_ms=0)
            .execution_options(synchronize_session=False)
        )
    now = utcnow()
    changes = [
        {
            "entity_type": ENTRY,
            "entity_id": entry_uuid(row.id),
            "operation": ChangeOperation.DELETE,
            "scope": ChangeScope.USER,
            "owner_user_id": row.user_id,
            "changed_at": now,
        }
        for row in rows
    ] + [
        {
            "entity_type": QUEUE,
            "entity_id": queue_id,
            "operation": ChangeOperation.UPDATE,
            "scope": ChangeScope.USER,
            "owner_user_id": owners[queue_id],
            "changed_at": now,
        }
        for queue_id in owners
    ]
    session.execute(insert(ChangeLog), changes)
    if session.get_bind().dialect.name == "postgresql":
        session.execute(text("SELECT pg_notify('anthology_changes', '')"))


@event.listens_for(Session, "before_commit")
def _before_commit(session: Session) -> None:
    _remove_deleted(session)


@event.listens_for(Session, "after_rollback")
def _after_rollback(session: Session) -> None:
    session.info.pop(_DELETED, None)


add_change_listener(_collect)
