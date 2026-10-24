"""Seed a development database with a generated library (``anthology dev seed-library``).

Uses the test library generator from ``tools/library-generator`` (a development dependency,
not part of production images). Seeding is an offline developer action: it writes no change
log entries, so connected clients should reconnect afterwards.
"""

import json
import uuid
from typing import Any

from anthology_library_generator import generate
from sqlalchemy import JSON, Table, bindparam, delete, func, insert, select, text, update
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from anthology.db.types import utcnow
from anthology.library.models import (
    LIBRARY_COUNTERS,
    Artist,
    AudioFile,
    Counter,
    IdentificationStatus,
    LibraryCounter,
    OriginalStatus,
    Recording,
    Release,
    ReleaseGroup,
    StorageMode,
    Track,
)
from anthology.library.service import sort_key

FLUSH_TRACKS = 20_000
SQLITE_BATCH = 5_000
# Insert order follows the foreign keys; deletion runs in reverse.
TABLES: tuple[Table, ...] = tuple(
    model.__table__
    for model in (Artist, ReleaseGroup, Release, Recording, Track, AudioFile)  # type: ignore[misc]
)


class LibraryNotEmptyError(Exception):
    pass


async def seed_library(engine: AsyncEngine, tracks: int, reset: bool = False) -> dict[str, int]:
    """Fill the library with ``tracks`` generated tracks; return the library counters."""
    async with engine.begin() as connection:
        if reset:
            for table in reversed(TABLES):
                await connection.execute(delete(table))
        elif await connection.scalar(select(func.count()).select_from(Artist)):
            raise LibraryNotEmptyError("the library is not empty; use --reset to replace it")

        loader = _Loader(connection)
        analyzed = False
        for batch in generate(tracks):
            loader.add(batch)
            if len(loader.rows[Track.__table__]) >= FLUSH_TRACKS:
                await loader.flush()
                if not analyzed:
                    await _analyze(connection)
                    analyzed = True
        await loader.flush()
        await _set_counts(connection, loader.counts)
        # Generated recordings are not identified, their originals not analysed yet.
        unchecked = {
            Counter.IDENTIFICATION_UNCHECKED: loader.totals[Counter.RECORDINGS],
            Counter.QUALITY_UNANALYSED: loader.totals[Counter.RECORDINGS],
        }
        await _set_counters(connection, {**loader.totals, **unchecked})
    async with engine.begin() as connection:
        await _analyze(connection)
    return {name.value: value for name, value in loader.totals.items()}


async def _analyze(connection: AsyncConnection) -> None:
    """Refresh the planner statistics of the library tables (PostgreSQL).

    Statistics of a small earlier library would make PostgreSQL plan the foreign key checks of
    the bulk load as sequential scans and keep those plans, so that every inserted row scans
    the whole referenced table. ANALYZE after the first batch (it counts this transaction's
    rows) invalidates those plans; after the load it gives the list queries real statistics.
    """
    if connection.dialect.name != "postgresql":
        return
    for table in TABLES:
        await connection.execute(text(f'ANALYZE "{table.name}"'))


class _Loader:
    """Turns generated batches into table rows with the same keys the service writes."""

    def __init__(self, connection: AsyncConnection) -> None:
        self.connection = connection
        self.rows: dict[Table, list[dict[str, Any]]] = {table: [] for table in TABLES}
        self.artist_sort: dict[uuid.UUID, str] = {}
        # Recording ID -> (sort title, artist ID), for reused recordings.
        self.recordings: dict[uuid.UUID, tuple[str, uuid.UUID]] = {}
        # Artist ID -> [release count, track count]
        self.counts: dict[uuid.UUID, list[int]] = {}
        self.homes: set[uuid.UUID] = set()
        self.totals = dict.fromkeys(LIBRARY_COUNTERS, 0)
        self.now = utcnow()

    def add(self, batch) -> None:
        for artist in batch.artists:
            self.artist_sort[artist.id] = sort_key(artist.name)
            self.counts[artist.id] = [0, 0]
            self._row(
                Artist,
                id=artist.id,
                name=artist.name,
                sort_name=self.artist_sort[artist.id],
                mb_artist_id=None,
                release_count=0,
                track_count=0,
            )
        self.totals[Counter.ARTISTS] += len(batch.artists)

        release = batch.release
        if release.edition is None:
            self._row(
                ReleaseGroup,
                id=release.release_group_id,
                title=release.title,
                type=release.group_type,
                mb_release_group_id=None,
            )
        release_sort = sort_key(release.title)
        self._row(
            Release,
            id=release.id,
            release_group_id=release.release_group_id,
            title=release.title,
            album_artist_id=release.album_artist_id,
            album_artist_display=release.album_artist_display,
            edition=release.edition,
            country=None,
            release_date=release.release_date,
            label=None,
            disc_count=release.disc_count,
            track_count=len(release.tracks),
            sort_title=release_sort,
            sort_album_artist=self.artist_sort[release.album_artist_id],
            mb_release_id=None,
        )
        self.totals[Counter.RELEASES] += 1
        self.counts[release.album_artist_id][0] += 1

        audio_rows = {}
        for recording in batch.recordings:
            self.recordings[recording.id] = (sort_key(recording.title), recording.artist_id)
            self._row(
                Recording,
                id=recording.id,
                title=recording.title,
                artist_id=recording.artist_id,
                artist_display=recording.artist_display,
                duration_ms=recording.duration_ms,
                composers=[],
                genres=[],
                isrc=None,
                mb_recording_id=None,
                acoust_id=None,
                identification_status=IdentificationStatus.UNCHECKED,
                identification_checked_at=None,
                identification_note=None,
                identification_duplicate_of_id=None,
            )
            audio_rows[recording.id] = recording.audio
        self.totals[Counter.RECORDINGS] += len(batch.recordings)

        for track in release.tracks:
            title_sort, artist_id = self.recordings[track.recording_id]
            self.counts[artist_id][1] += 1
            self._row(
                Track,
                id=track.id,
                release_id=release.id,
                recording_id=track.recording_id,
                disc_number=track.disc_number,
                track_number=track.track_number,
                context_title=track.context_title,
                context_artist=None,
                sort_artist=self.artist_sort[artist_id],
                sort_title=sort_key(track.context_title) if track.context_title else title_sort,
                sort_album=release_sort,
            )
            if track.recording_id in audio_rows and track.recording_id not in self.homes:
                self.homes.add(track.recording_id)
                audio = audio_rows[track.recording_id]
                self._row(
                    AudioFile,
                    id=uuid.uuid5(track.recording_id, "audio"),
                    recording_id=track.recording_id,
                    path=audio.path,
                    format=audio.format,
                    codec=audio.codec,
                    bitrate_kbps=audio.bitrate_kbps,
                    sample_rate_hz=audio.sample_rate_hz,
                    bit_depth=audio.bit_depth,
                    channels=audio.channels,
                    size_bytes=audio.size_bytes,
                    audio_hash=audio.audio_hash,
                    content_hash=None,
                    declared_quality=audio.declared_quality,
                    effective_quality=None,
                    quality_status=None,
                    storage_mode=StorageMode.MANAGED,
                    original_status=OriginalStatus.ACTIVE,
                    tag_writes_allowed=False,
                    superseded_by_id=None,
                    superseded_at=None,
                    fingerprint=None,
                    fingerprint_duration_s=None,
                    home_track_id=track.id,
                    added_at=self.now,
                )
        self.totals[Counter.TRACKS] += len(release.tracks)

    def _row(self, model, **values: Any) -> None:
        self.rows[model.__table__].append(values)

    async def flush(self) -> None:
        for table in TABLES:
            rows = self.rows[table]
            if rows:
                await _insert(self.connection, table, rows)
                self.rows[table] = []


async def _insert(connection: AsyncConnection, table: Table, rows: list[dict[str, Any]]) -> None:
    if connection.dialect.name == "postgresql":
        raw = await connection.get_raw_connection()
        columns = [column.name for column in table.columns]
        # COPY takes JSON columns as text.
        as_json = {column.name for column in table.columns if isinstance(column.type, JSON)}
        await raw.driver_connection.copy_records_to_table(
            table.name,
            records=[
                tuple(json.dumps(row[name]) if name in as_json else row[name] for name in columns)
                for row in rows
            ],
            columns=columns,
        )
        return
    for start in range(0, len(rows), SQLITE_BATCH):
        await connection.execute(insert(table), rows[start : start + SQLITE_BATCH])


async def _set_counts(connection: AsyncConnection, counts: dict[uuid.UUID, list[int]]) -> None:
    """Per-artist release and track counts (tracks of reused recordings count for their artist)."""
    statement = (
        update(Artist.__table__)
        .where(Artist.__table__.c.id == bindparam("artist_id"))
        .values(release_count=bindparam("releases"), track_count=bindparam("tracks"))
    )
    rows = [
        {"artist_id": artist_id, "releases": releases, "tracks": tracks}
        for artist_id, (releases, tracks) in counts.items()
    ]
    for start in range(0, len(rows), SQLITE_BATCH):
        await connection.execute(statement, rows[start : start + SQLITE_BATCH])


async def _set_counters(connection: AsyncConnection, totals: dict[Counter, int]) -> None:
    await connection.execute(delete(LibraryCounter))
    await connection.execute(
        insert(LibraryCounter), [{"name": name, "value": value} for name, value in totals.items()]
    )
