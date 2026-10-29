"""Playlists (spec: personal-data, Playlist ownership and visibility, Shared playlists are
editable by all, Concurrent playlist edits, Undo playlist edits, Playlist folders).

Change entries: ``playlist`` and ``playlist_entry`` with scope ``user`` for private playlists
(the owner) and ``shared`` for shared ones; ``playlist_folder`` with scope ``user``. Entries are
ordered by fractional keys (``keys.py``), so an insert never touches other entries; every
change of entries is a ``PlaylistEdit`` that its author or the owner can undo.
"""

import json
import uuid
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import delete, event, func, insert, select, text, update
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
from anthology.library.models import Recording, Track
from anthology.personal_data import keys
from anthology.personal_data.models import (
    EditKind,
    Playlist,
    PlaylistEdit,
    PlaylistEntry,
    PlaylistFolder,
    Visibility,
)
from anthology.playback import service as playback

PLAYLIST = "playlist"
ENTRY = "playlist_entry"
FOLDER = "playlist_folder"
# Entries per request and per playlist.
MAX_ADD = 10_000
MAX_ENTRIES = 50_000
# Edits can be undone this long.
UNDO_DAYS = 30


class PlaylistError(Exception):
    code = "playlist_error"


class NotFound(PlaylistError):
    code = "unknown_playlist"


class Forbidden(PlaylistError):
    code = "forbidden"


class ChangedSince(PlaylistError):
    code = "changed_since"


class TooLarge(PlaylistError):
    code = "playlist_too_large"


def visible(playlist: Playlist, user_id: uuid.UUID) -> bool:
    return playlist.owner_id == user_id or playlist.visibility == Visibility.SHARED


def _scope(playlist: Playlist) -> dict[str, Any]:
    if playlist.visibility == Visibility.SHARED:
        return {"scope": ChangeScope.SHARED, "owner_user_id": None}
    return {"scope": ChangeScope.USER, "owner_user_id": playlist.owner_id}


async def _changed(
    session: AsyncSession, playlist: Playlist, operation=ChangeOperation.UPDATE
) -> None:
    playlist.updated_at = utcnow()
    await session.flush()
    await record_change(
        session,
        entity_type=PLAYLIST,
        entity_id=playlist.id,
        operation=operation,
        **_scope(playlist),
    )


async def _entries_changed(
    session: AsyncSession, playlist: Playlist, ids: Iterable[uuid.UUID], operation
) -> None:
    await record_changes(
        session, entity_type=ENTRY, entity_ids=ids, operation=operation, **_scope(playlist)
    )


async def get(
    session: AsyncSession, playlist_id: uuid.UUID, user_id: uuid.UUID, *, lock: bool = False
) -> Playlist:
    """A playlist the user may see (and edit); raises ``NotFound`` otherwise."""
    playlist = await session.get(Playlist, playlist_id, with_for_update=lock)
    if playlist is None or not visible(playlist, user_id):
        raise NotFound(playlist_id)
    return playlist


def _owner(playlist: Playlist, user_id: uuid.UUID) -> None:
    if playlist.owner_id != user_id:
        raise Forbidden("only the owner may do this")


# --- playlists and folders --------------------------------------------------------------------


async def _folder(session: AsyncSession, folder_id: uuid.UUID | None, user_id: uuid.UUID):
    if folder_id is None:
        return None
    folder = await session.get(PlaylistFolder, folder_id)
    if folder is None or folder.user_id != user_id:
        raise NotFound(folder_id)
    return folder.id


async def create(
    session: AsyncSession,
    owner_id: uuid.UUID,
    name: str,
    *,
    visibility: Visibility = Visibility.PRIVATE,
    folder_id: uuid.UUID | None = None,
) -> Playlist:
    playlist = Playlist(
        owner_id=owner_id,
        name=name,
        visibility=visibility,
        folder_id=await _folder(session, folder_id, owner_id),
    )
    session.add(playlist)
    await session.flush()
    await _changed(session, playlist, ChangeOperation.INSERT)
    return playlist


_UNSET: Any = object()


async def update_playlist(
    session: AsyncSession,
    playlist: Playlist,
    user_id: uuid.UUID,
    *,
    name: str = _UNSET,
    visibility: Visibility = _UNSET,
    folder_id: uuid.UUID | None = _UNSET,
) -> None:
    """Rename, share or move a playlist (the owner only)."""
    _owner(playlist, user_id)
    if name is not _UNSET:
        playlist.name = name
    if folder_id is not _UNSET:
        playlist.folder_id = await _folder(session, folder_id, user_id)
    if visibility is not _UNSET and visibility != playlist.visibility:
        # Who loses access must see the playlist and its entries disappear: record the change
        # in the old scope too.
        old = _scope(playlist)
        playlist.visibility = visibility
        await record_change(
            session,
            entity_type=PLAYLIST,
            entity_id=playlist.id,
            operation=ChangeOperation.UPDATE,
            **old,
        )
    await _changed(session, playlist)


async def delete_playlist(session: AsyncSession, playlist: Playlist, user_id: uuid.UUID) -> None:
    _owner(playlist, user_id)
    scope = _scope(playlist)
    playlist_id = playlist.id
    await session.delete(playlist)
    await session.flush()
    await record_change(
        session,
        entity_type=PLAYLIST,
        entity_id=playlist_id,
        operation=ChangeOperation.DELETE,
        **scope,
    )


async def _folder_changed(session: AsyncSession, folder: PlaylistFolder, operation) -> None:
    await record_change(
        session,
        entity_type=FOLDER,
        entity_id=folder.id,
        operation=operation,
        scope=ChangeScope.USER,
        owner_user_id=folder.user_id,
    )


async def create_folder(session: AsyncSession, user_id: uuid.UUID, name: str) -> PlaylistFolder:
    folder = PlaylistFolder(user_id=user_id, name=name)
    session.add(folder)
    await session.flush()
    await _folder_changed(session, folder, ChangeOperation.INSERT)
    return folder


async def rename_folder(
    session: AsyncSession, folder_id: uuid.UUID, user_id: uuid.UUID, name: str
) -> None:
    folder = await session.get(PlaylistFolder, folder_id)
    if folder is None or folder.user_id != user_id:
        raise NotFound(folder_id)
    folder.name = name
    await session.flush()
    await _folder_changed(session, folder, ChangeOperation.UPDATE)


async def delete_folder(session: AsyncSession, folder_id: uuid.UUID, user_id: uuid.UUID) -> None:
    """The folder's playlists stay, outside any folder."""
    folder = await session.get(PlaylistFolder, folder_id)
    if folder is None or folder.user_id != user_id:
        raise NotFound(folder_id)
    playlists = list(await session.scalars(select(Playlist).where(Playlist.folder_id == folder_id)))
    for playlist in playlists:
        playlist.folder_id = None
        await _changed(session, playlist)
    await session.delete(folder)
    await session.flush()
    await _folder_changed(session, folder, ChangeOperation.DELETE)


# --- entries ----------------------------------------------------------------------------------


@dataclass(frozen=True)
class Added:
    entries: int
    edit_id: uuid.UUID | None
    shortened: bool


async def _key(session: AsyncSession, entry_id: uuid.UUID | None, playlist: Playlist) -> str | None:
    if entry_id is None:
        return None
    key = await session.scalar(
        select(PlaylistEntry.position_key).where(
            PlaylistEntry.id == entry_id, PlaylistEntry.playlist_id == playlist.id
        )
    )
    if key is None:
        raise NotFound(entry_id)
    return key


async def _next_key(
    session: AsyncSession, playlist: Playlist, key: str | None, exclude=()
) -> str | None:
    """The smallest key after ``key`` (None: before the first), or None at the end; entries
    in ``exclude`` (being moved) do not count."""
    query = select(func.min(PlaylistEntry.position_key)).where(
        PlaylistEntry.playlist_id == playlist.id, PlaylistEntry.id.not_in(list(exclude))
    )
    if key is not None:
        query = query.where(PlaylistEntry.position_key > key)
    return await session.scalar(query)


async def _gap(
    session: AsyncSession,
    playlist: Playlist,
    after: uuid.UUID | None,
    *,
    at_start: bool,
    exclude=(),
) -> tuple[str | None, str | None]:
    """The keys around the place after ``after`` (None: at the end, or the start), without
    the entries in ``exclude``."""
    if after is not None:
        low = await _key(session, after, playlist)
        return low, await _next_key(session, playlist, low, exclude)
    if at_start:
        return None, await _next_key(session, playlist, None, exclude)
    last = await session.scalar(
        select(func.max(PlaylistEntry.position_key)).where(
            PlaylistEntry.playlist_id == playlist.id, PlaylistEntry.id.not_in(list(exclude))
        )
    )
    return last, None


async def _durations(session: AsyncSession, track_ids: list[uuid.UUID]) -> dict[uuid.UUID, int]:
    if not track_ids:
        return {}
    rows = await session.execute(
        select(Track.id, Recording.duration_ms)
        .join(Recording, Recording.id == Track.recording_id)
        .where(Track.id.in_(track_ids))
    )
    return dict(rows.all())


def _edit(
    session: AsyncSession, playlist: Playlist, user_id: uuid.UUID, kind: EditKind, entries
) -> PlaylistEdit:
    edit = PlaylistEdit(
        playlist_id=playlist.id,
        user_id=user_id,
        kind=kind,
        entries_json=json.dumps(entries, sort_keys=True),
    )
    session.add(edit)
    return edit


async def add(
    session: AsyncSession,
    playlist: Playlist,
    user_id: uuid.UUID,
    *,
    ids: list[uuid.UUID] | None = None,
    rule: dict[str, Any] | None = None,
    after: uuid.UUID | None = None,
    at_start: bool = False,
) -> Added:
    """Insert tracks (in order) after the entry ``after``, at the start, or at the end."""
    room = MAX_ENTRIES - playlist.entry_count
    limit = min(MAX_ADD, max(room, 0))
    if ids is not None:
        requested = list(dict.fromkeys(ids))
        durations = await _durations(session, requested)
        tracks = [track_id for track_id in requested if track_id in durations][:limit]
        shortened = len(tracks) < len([t for t in requested if t in durations])
    else:
        tracks = await playback.rule_tracks(session, rule or {}, limit + 1)
        shortened = len(tracks) > limit
        tracks = tracks[:limit]
        durations = await _durations(session, tracks)
    if not tracks:
        if room <= 0:
            raise TooLarge(playlist.id)
        return Added(0, None, shortened)
    low, high = await _gap(session, playlist, after, at_start=at_start)
    positions = keys.spread(low, high, len(tracks))
    now = utcnow()
    rows = [
        {
            "id": uuid.uuid4(),
            "playlist_id": playlist.id,
            "track_id": track_id,
            "position_key": key,
            "added_by": user_id,
            "added_at": now,
        }
        for track_id, key in zip(tracks, positions, strict=True)
    ]
    await session.execute(insert(PlaylistEntry), rows)
    playlist.entry_count += len(rows)
    playlist.duration_ms += sum(durations.get(track_id, 0) for track_id in tracks)
    edit = _edit(
        session,
        playlist,
        user_id,
        EditKind.ADD,
        [{"id": str(row["id"]), "key": row["position_key"]} for row in rows],
    )
    await session.flush()
    await _entries_changed(session, playlist, [row["id"] for row in rows], ChangeOperation.INSERT)
    await _rebalance_if_needed(session, playlist, positions)
    await _changed(session, playlist)
    return Added(len(rows), edit.id, shortened)


async def _entries(
    session: AsyncSession, playlist: Playlist, entry_ids: list[uuid.UUID]
) -> list[PlaylistEntry]:
    entries = list(
        await session.scalars(
            select(PlaylistEntry).where(
                PlaylistEntry.playlist_id == playlist.id, PlaylistEntry.id.in_(entry_ids)
            )
        )
    )
    if len(entries) != len(set(entry_ids)):
        raise NotFound("entry")
    return entries


def _snapshot(entry: PlaylistEntry) -> dict[str, Any]:
    return {
        "id": str(entry.id),
        "track_id": str(entry.track_id),
        "key": entry.position_key,
        "added_by": str(entry.added_by) if entry.added_by else None,
        "added_at": entry.added_at.isoformat(),
    }


async def remove(
    session: AsyncSession, playlist: Playlist, user_id: uuid.UUID, entry_ids: list[uuid.UUID]
) -> uuid.UUID:
    entries = await _entries(session, playlist, entry_ids)
    durations = await _durations(session, [entry.track_id for entry in entries])
    edit = _edit(session, playlist, user_id, EditKind.REMOVE, [_snapshot(e) for e in entries])
    await session.execute(
        delete(PlaylistEntry).where(PlaylistEntry.id.in_([entry.id for entry in entries]))
    )
    playlist.entry_count -= len(entries)
    playlist.duration_ms -= sum(durations.get(entry.track_id, 0) for entry in entries)
    await session.flush()
    await _entries_changed(session, playlist, [e.id for e in entries], ChangeOperation.DELETE)
    await _changed(session, playlist)
    return edit.id


async def move(
    session: AsyncSession,
    playlist: Playlist,
    user_id: uuid.UUID,
    entry_ids: list[uuid.UUID],
    *,
    after: uuid.UUID | None,
) -> uuid.UUID:
    """Move entries (in the given order) behind ``after``; None moves them to the start."""
    entries = {entry.id: entry for entry in await _entries(session, playlist, entry_ids)}
    if after in entries:
        raise ValueError("cannot move entries behind one of themselves")
    ordered = [entries[entry_id] for entry_id in dict.fromkeys(entry_ids)]
    before = [{"id": str(entry.id), "key": entry.position_key} for entry in ordered]
    low, high = await _gap(
        session, playlist, after, at_start=after is None, exclude=[e.id for e in ordered]
    )
    positions = keys.spread(low, high, len(ordered))
    for entry, key in zip(ordered, positions, strict=True):
        entry.position_key = key
    after_keys = [{"id": str(entry.id), "key": entry.position_key} for entry in ordered]
    edit = _edit(session, playlist, user_id, EditKind.MOVE, {"before": before, "after": after_keys})
    await session.flush()
    await _entries_changed(session, playlist, entries, ChangeOperation.UPDATE)
    await _rebalance_if_needed(session, playlist, positions)
    await _changed(session, playlist)
    return edit.id


async def _rebalance_if_needed(
    session: AsyncSession, playlist: Playlist, new_keys: list[str]
) -> None:
    """Rewrite every key evenly once keys grow long (one change, a new generation)."""
    if not new_keys or max(len(key) for key in new_keys) <= keys.MAX_LENGTH:
        return
    entry_ids = list(
        await session.scalars(
            select(PlaylistEntry.id)
            .where(PlaylistEntry.playlist_id == playlist.id)
            .order_by(PlaylistEntry.position_key, PlaylistEntry.id)
        )
    )
    fresh = keys.spread(None, None, len(entry_ids))
    await session.execute(
        update(PlaylistEntry),
        [
            {"id": entry_id, "position_key": key}
            for entry_id, key in zip(entry_ids, fresh, strict=True)
        ],
    )
    playlist.generation = uuid.uuid4()
    # Edits before the rebalancing refer to old keys: they cannot be undone any more.
    await session.execute(
        update(PlaylistEdit)
        .where(PlaylistEdit.playlist_id == playlist.id, PlaylistEdit.undone_at.is_(None))
        .values(undone_at=utcnow())
    )


# --- undo -------------------------------------------------------------------------------------


async def undo(session: AsyncSession, edit_id: uuid.UUID, user_id: uuid.UUID) -> Playlist:
    """Undo an edit (its author or the playlist's owner); raises ``ChangedSince`` when its
    entries changed since."""
    edit = await session.get(PlaylistEdit, edit_id, with_for_update=True)
    if edit is None:
        raise NotFound(edit_id)
    playlist = await get(session, edit.playlist_id, user_id, lock=True)
    if user_id not in (edit.user_id, playlist.owner_id):
        raise Forbidden("only the author or the owner may undo")
    if edit.undone_at is not None or edit.created_at < utcnow() - timedelta(days=UNDO_DAYS):
        raise ChangedSince(edit_id)
    entries = json.loads(edit.entries_json)
    if edit.kind == EditKind.ADD:
        await _undo_add(session, playlist, entries)
    elif edit.kind == EditKind.REMOVE:
        await _undo_remove(session, playlist, entries)
    else:
        await _undo_move(session, playlist, entries)
    edit.undone_at = utcnow()
    await _changed(session, playlist)
    return playlist


async def _current(session: AsyncSession, playlist: Playlist, ids: list[str]):
    return {
        str(entry.id): entry
        for entry in await session.scalars(
            select(PlaylistEntry).where(
                PlaylistEntry.playlist_id == playlist.id,
                PlaylistEntry.id.in_([uuid.UUID(value) for value in ids]),
            )
        )
    }


async def _undo_add(session, playlist, entries) -> None:
    present = await _current(session, playlist, [entry["id"] for entry in entries])
    if any(
        entry["id"] not in present or present[entry["id"]].position_key != entry["key"]
        for entry in entries
    ):
        raise ChangedSince(playlist.id)
    durations = await _durations(session, [entry.track_id for entry in present.values()])
    await session.execute(
        delete(PlaylistEntry).where(PlaylistEntry.id.in_([e.id for e in present.values()]))
    )
    playlist.entry_count -= len(present)
    playlist.duration_ms -= sum(durations.get(e.track_id, 0) for e in present.values())
    await session.flush()
    await _entries_changed(
        session, playlist, [e.id for e in present.values()], ChangeOperation.DELETE
    )


async def _undo_remove(session, playlist, entries) -> None:
    present = await _current(session, playlist, [entry["id"] for entry in entries])
    if present:
        raise ChangedSince(playlist.id)
    tracks = await _durations(session, [uuid.UUID(entry["track_id"]) for entry in entries])
    restored = [entry for entry in entries if uuid.UUID(entry["track_id"]) in tracks]
    if not restored:
        raise ChangedSince(playlist.id)
    await session.execute(
        insert(PlaylistEntry),
        [
            {
                "id": uuid.UUID(entry["id"]),
                "playlist_id": playlist.id,
                "track_id": uuid.UUID(entry["track_id"]),
                "position_key": entry["key"],
                "added_by": uuid.UUID(entry["added_by"]) if entry["added_by"] else None,
                "added_at": datetime.fromisoformat(entry["added_at"]),
            }
            for entry in restored
        ],
    )
    playlist.entry_count += len(restored)
    playlist.duration_ms += sum(tracks[uuid.UUID(entry["track_id"])] for entry in restored)
    await session.flush()
    await _entries_changed(
        session, playlist, [uuid.UUID(entry["id"]) for entry in restored], ChangeOperation.INSERT
    )


async def _undo_move(session, playlist, entries) -> None:
    after = {entry["id"]: entry["key"] for entry in entries["after"]}
    present = await _current(session, playlist, list(after))
    if set(present) != set(after) or any(present[i].position_key != k for i, k in after.items()):
        raise ChangedSince(playlist.id)
    for entry in entries["before"]:
        present[entry["id"]].position_key = entry["key"]
    await session.flush()
    await _entries_changed(
        session, playlist, [e.id for e in present.values()], ChangeOperation.UPDATE
    )


# --- the playlist rule of play queues ---------------------------------------------------------


def _playlist_tracks(rule: dict[str, Any]):
    query = select(PlaylistEntry.track_id.label("track_id")).where(
        PlaylistEntry.playlist_id == uuid.UUID(rule["playlist_id"])
    )
    return query, [PlaylistEntry.position_key, PlaylistEntry.id]


playback.register_list("playlist", _playlist_tracks)


# --- entries of deleted tracks ----------------------------------------------------------------

_DELETED = "personal_data.tracks"


def _collect(session: AsyncSession, entity_type: str, entity_ids: list[uuid.UUID]) -> None:
    if entity_type == "track":
        session.info.setdefault(_DELETED, set()).update(entity_ids)


def _remove_deleted(session: Session) -> None:
    """Before the commit: entries of tracks that no longer exist leave their playlists, with
    their change entries (synchronous: ``before_commit``)."""
    ids = session.info.pop(_DELETED, None)
    if not ids:
        return
    rows = session.execute(
        select(PlaylistEntry.id, Playlist.id, Playlist.visibility, Playlist.owner_id)
        .join(Playlist, Playlist.id == PlaylistEntry.playlist_id)
        .where(
            PlaylistEntry.track_id.in_(ids),
            ~select(Track.id).where(Track.id == PlaylistEntry.track_id).exists(),
        )
    ).all()
    if not rows:
        return
    session.execute(delete(PlaylistEntry).where(PlaylistEntry.id.in_([row[0] for row in rows])))
    counts: dict[uuid.UUID, int] = {}
    for _entry, playlist_id, _visibility, _owner_id in rows:
        counts[playlist_id] = counts.get(playlist_id, 0) + 1
    for playlist_id, count in counts.items():
        session.execute(
            update(Playlist)
            .where(Playlist.id == playlist_id)
            .values(entry_count=Playlist.entry_count - count)
            .execution_options(synchronize_session=False)
        )
    now = utcnow()

    def scope(visibility, owner_id):
        shared = visibility == Visibility.SHARED
        return {
            "scope": ChangeScope.SHARED if shared else ChangeScope.USER,
            "owner_user_id": None if shared else owner_id,
        }

    owners = {row[1]: (row[2], row[3]) for row in rows}
    changes = [
        {"entity_type": ENTRY, "entity_id": row[0], "operation": ChangeOperation.DELETE,
         "changed_at": now, **scope(row[2], row[3])}
        for row in rows
    ] + [
        {"entity_type": PLAYLIST, "entity_id": playlist_id, "operation": ChangeOperation.UPDATE,
         "changed_at": now, **scope(*owners[playlist_id])}
        for playlist_id in counts
    ]  # fmt: skip
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
