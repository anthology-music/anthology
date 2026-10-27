"""Maintenance of the search documents (spec: search; design: Search documents).

Library writes record change entries; a change listener collects the changed artists,
releases, tracks, recordings and originals in the session, and the documents they affect
are rewritten just before the transaction commits, so the index never lags behind a
committed write. The handlers run inside SQLAlchemy's ``before_commit`` event, which the
asyncio extension calls in its greenlet: synchronous ``execute`` calls are allowed there.
"""

import uuid
from collections.abc import Iterable
from typing import Any

from sqlalchemy import Connection, delete, event, func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from anthology.core.changes import add_change_listener
from anthology.library.models import (
    Artist,
    AudioFile,
    OriginalStatus,
    Recording,
    Release,
    Track,
)
from anthology.search.models import SearchDocument, SearchIndexState, SearchTerm
from anthology.search.normalize import fold

# Raise when the documents' contents or the folding change: the server rebuilds the index.
VERSION = 1
ARTIST, RELEASE, TRACK = "artist", "release", "track"
ITEM_TYPES = (ARTIST, RELEASE, TRACK)
SEPARATOR = "\x01"
BATCH = 500

_PENDING = "search.pending"
# Change entries that affect documents (``track.moved``: see library.service.TRACK_MOVED).
_WATCHED = frozenset({"artist", "release", "track", "track.moved", "recording", "audio_file"})

Executor = Session | Connection


def _collect(session: AsyncSession, entity_type: str, entity_ids: list[uuid.UUID]) -> None:
    if entity_type in _WATCHED:
        pending = session.info.setdefault(_PENDING, {})
        pending.setdefault(entity_type, set()).update(entity_ids)


def _chunks(ids: Iterable[uuid.UUID]) -> Iterable[list[uuid.UUID]]:
    ids = sorted(set(ids))
    for start in range(0, len(ids), BATCH):
        yield ids[start : start + BATCH]


def _join(*parts: str | None) -> str:
    return " ".join(folded for part in parts if part and (folded := fold(part)))


# --- documents ----------------------------------------------------------------------------


def _artist_docs(conn: Executor, ids: list[uuid.UUID]) -> list[dict[str, Any]]:
    docs = []
    # Columns, not entities: bulk updates of the library leave loaded entities stale.
    query = select(Artist.id, Artist.name, Artist.sort_name).where(Artist.id.in_(ids))
    for artist in conn.execute(query):
        name = fold(artist.name)
        extra = [word for word in fold(artist.sort_name).split() if word not in name.split()]
        docs.append(
            _doc(
                ARTIST,
                artist.id,
                text=" ".join([name, *extra]).strip(),
                artist=name,
                artist_id=artist.id,
                sort_key=artist.sort_name,
            )
        )
    return docs


def _release_docs(conn: Executor, ids: list[uuid.UUID]) -> list[dict[str, Any]]:
    docs = []
    query = select(
        Release.id,
        Release.title,
        Release.album_artist_display,
        Release.album_artist_id,
        Release.release_date,
        Release.sort_album_artist,
        Release.sort_title,
    ).where(Release.id.in_(ids))
    for release in conn.execute(query):
        year = release.release_date.year if release.release_date else None
        docs.append(
            _doc(
                RELEASE,
                release.id,
                text=_join(release.title, release.album_artist_display, str(year or "")),
                artist=fold(release.album_artist_display),
                album=fold(release.title),
                year=year,
                release_id=release.id,
                album_artist_id=release.album_artist_id,
                sort_key=SEPARATOR.join((release.sort_album_artist, release.sort_title)),
            )
        )
    return docs


_TRACKS = (
    select(
        Track.id,
        Track.release_id,
        Track.context_title,
        Track.context_artist,
        Track.sort_artist,
        Track.sort_title,
        Track.sort_album,
        Recording.title,
        Recording.artist_display,
        Recording.artist_id,
        Recording.composers,
        Recording.genres,
        Release.title,
        Release.album_artist_display,
        Release.album_artist_id,
        Release.release_date,
        AudioFile.format,
        AudioFile.effective_quality,
    )
    .join(Recording, Recording.id == Track.recording_id)
    .join(Release, Release.id == Track.release_id)
    .outerjoin(
        AudioFile,
        (AudioFile.recording_id == Track.recording_id)
        & (AudioFile.original_status == OriginalStatus.ACTIVE),
    )
)


def _track_docs(conn: Executor, ids: list[uuid.UUID]) -> list[dict[str, Any]]:
    docs = []
    for row in conn.execute(_TRACKS.where(Track.id.in_(ids))):
        (track_id, release_id, context_title, context_artist, sort_artist, sort_title,
         sort_album, title, artist, artist_id, composers, genres, album, album_artist,
         album_artist_id, release_date, audio_format, quality) = row  # fmt: skip
        title = context_title or title
        artist = context_artist or artist
        year = release_date.year if release_date else None
        composer = _join(*(composers or []))
        genre = _join(*(genres or []))
        docs.append(
            _doc(
                TRACK,
                track_id,
                text=" ".join(
                    part
                    for part in (
                        _join(title, artist, album, album_artist),
                        composer,
                        genre,
                        str(year or ""),
                    )
                    if part
                ),
                artist=_join(artist, album_artist),
                album=fold(album),
                composer=composer,
                genre=genre,
                year=year,
                format=audio_format.value if audio_format else None,
                quality=quality.value if quality else None,
                release_id=release_id,
                artist_id=artist_id,
                album_artist_id=album_artist_id,
                sort_key=SEPARATOR.join((sort_artist, sort_title, sort_album)),
            )
        )
    return docs


def _doc(item_type: str, item_id: uuid.UUID, **values: Any) -> dict[str, Any]:
    return {
        "item_type": item_type,
        "item_id": item_id,
        "artist": "",
        "album": "",
        "composer": "",
        "genre": "",
        "year": None,
        "format": None,
        "quality": None,
        "release_id": None,
        "artist_id": None,
        "album_artist_id": None,
        **values,
    }


_BUILDERS = {ARTIST: _artist_docs, RELEASE: _release_docs, TRACK: _track_docs}


def _insert_ignoring(conn: Executor):
    dialect = conn.get_bind().dialect.name if isinstance(conn, Session) else conn.dialect.name
    return pg_insert if dialect == "postgresql" else sqlite_insert


def rewrite(conn: Executor, item_type: str, ids: Iterable[uuid.UUID]) -> int:
    """Rewrite the documents of ``ids`` (removing those of deleted items); returns the count."""
    written = 0
    insert = _insert_ignoring(conn)
    for chunk in _chunks(ids):
        conn.execute(
            delete(SearchDocument).where(
                SearchDocument.item_type == item_type, SearchDocument.item_id.in_(chunk)
            )
        )
        docs = _BUILDERS[item_type](conn, chunk)
        if not docs:
            continue
        conn.execute(insert(SearchDocument), docs)
        terms = sorted({term[:128] for doc in docs for term in doc["text"].split()})
        if terms:
            conn.execute(
                insert(SearchTerm).on_conflict_do_nothing(),
                [{"term": term} for term in terms],
            )
        written += len(docs)
    return written


def _process(session: Session) -> None:
    pending: dict[str, set[uuid.UUID]] = session.info.pop(_PENDING, None) or {}
    if not pending:
        return
    tracks = pending.get("track", set()) | pending.get("track.moved", set())
    recordings = set(pending.get("recording", set()))
    for chunk in _chunks(pending.get("audio_file", set())):
        recordings.update(
            session.execute(select(AudioFile.recording_id).where(AudioFile.id.in_(chunk)))
            .scalars()
            .all()
        )
    for chunk in _chunks(recordings):
        tracks.update(
            session.execute(select(Track.id).where(Track.recording_id.in_(chunk))).scalars().all()
        )
    releases = pending.get("release", set())
    # Tracks carry their release's title, album artist and year.
    for chunk in _chunks(releases):
        tracks.update(
            session.execute(select(Track.id).where(Track.release_id.in_(chunk))).scalars().all()
        )
    rewrite(session, ARTIST, pending.get("artist", set()))
    rewrite(session, RELEASE, releases)
    rewrite(session, TRACK, tracks)


@event.listens_for(Session, "before_commit")
def _before_commit(session: Session) -> None:
    _process(session)


@event.listens_for(Session, "after_rollback")
def _after_rollback(session: Session) -> None:
    session.info.pop(_PENDING, None)


async def flush(session: AsyncSession) -> None:
    """Rewrite the collected documents now (to search them before the commit)."""
    await session.run_sync(_process)


add_change_listener(_collect)


# --- full rebuild ---------------------------------------------------------------------------

_SOURCES = {ARTIST: Artist.id, RELEASE: Release.id, TRACK: Track.id}


def rebuild_batch(
    conn: Executor, item_type: str, after: uuid.UUID | None, limit: int
) -> uuid.UUID | None:
    """Rewrite the documents of the next ``limit`` items after ``after`` (by ID); returns the
    last ID, or None when the items are exhausted."""
    column = _SOURCES[item_type]
    query = select(column).order_by(column).limit(limit)
    if after is not None:
        query = query.where(column > after)
    ids = list(conn.execute(query).scalars())
    if not ids:
        return None
    rewrite(conn, item_type, ids)
    return ids[-1]


def remove_stale(conn: Executor) -> None:
    """Remove the documents of items that no longer exist."""
    for item_type, column in _SOURCES.items():
        conn.execute(
            delete(SearchDocument).where(
                SearchDocument.item_type == item_type,
                ~select(column).where(column == SearchDocument.item_id).exists(),
            )
        )


def rebuild_all(conn: Executor, batch: int = 5_000) -> None:
    """Rebuild the whole index in the caller's transaction (generator, tests)."""
    conn.execute(delete(SearchDocument))
    conn.execute(delete(SearchTerm))
    for item_type in ITEM_TYPES:
        after = None
        while (after := rebuild_batch(conn, item_type, after, batch)) is not None:
            pass
    set_version(conn)


def set_version(conn: Executor, version: int = VERSION) -> None:
    if conn.execute(update(SearchIndexState).values(version=version)).rowcount == 0:
        conn.execute(_insert_ignoring(conn)(SearchIndexState).values(id=1, version=version))


def current_version(conn: Executor) -> int | None:
    return conn.execute(select(func.max(SearchIndexState.version))).scalar()


def item_count(conn: Executor, item_type: str) -> int:
    return conn.execute(select(func.count(_SOURCES[item_type]))).scalar() or 0
