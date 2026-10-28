"""Streams of the library domain (spec: library, Library lists).

Every list is one index range scan on the table it lists (sort keys are denormalized onto
its rows); totals come from maintained counters. Rows of a chunk are completed with
primary-key joins.
"""

import uuid
from typing import Any

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from anthology.library import maintenance, service
from anthology.library.models import (
    IDENTIFICATION_COUNTERS,
    REFERENCED_COUNTERS,
    SUPERSEDED_COUNTERS,
    Artist,
    AudioFile,
    MaintenanceFinding,
    MaintenanceRun,
    OriginalStatus,
    Recording,
    Release,
    Track,
)
from anthology.library.schemas import (
    LibraryArtistRow,
    LibraryIdentificationRow,
    LibraryReleaseRow,
    LibraryStorageRow,
    LibrarySupersededRow,
    LibraryTrackRow,
    MaintenanceFindingRow,
    MaintenanceRunRow,
)
from anthology.sources.models import Source
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
from anthology.users.models import Role
from anthology.users.service import SessionInfo

ARTIST_KEY = (Artist.sort_name, Artist.id)
RELEASE_KEY = (Release.sort_album_artist, Release.sort_title, Release.id)
ARTIST_RELEASE_KEY = (Release.sort_title, Release.id)
TRACK_KEY = (Track.sort_artist, Track.sort_title, Track.sort_album, Track.id)
RELEASE_TRACK_KEY = (Track.disc_number, Track.track_number, Track.id)


def _no_params(params: dict[str, Any]) -> dict[str, Any]:
    if params:
        raise StreamError("invalid_params", "this stream takes no parameters")
    return {}


def _id_param(params: dict[str, Any], name: str) -> dict[str, Any]:
    try:
        return {name: uuid.UUID(str(params[name]))}
    except (KeyError, ValueError) as error:
        raise StreamError("invalid_params", f"{name} is required") from error


async def _page(
    db: AsyncSession, key_query: KeyQuery, query: Select, after: SortKey | None, limit: int
):
    condition = key_query.after(after)
    if condition is not None:
        query = query.where(condition)
    return await db.execute(query.order_by(*key_query.ordering()).limit(limit))


def _upsert(row: Row) -> list[RowChange]:
    return [RowChange(op="upsert", id=row.id, key=row.key, row=row)]


def _remove(entity_id: uuid.UUID) -> list[RowChange]:
    return [RowChange(op="remove", id=str(entity_id))]


async def _library_meta(db: AsyncSession, counter: str) -> Meta:
    counters = await service.counters(db)
    return Meta(total=counters[counter], counters=counters)


# --- artists ------------------------------------------------------------------------------


def _artist_row(artist: Artist, key: SortKey | None = None) -> Row:
    key = key or (artist.sort_name, artist.id)
    model = LibraryArtistRow(
        id=str(artist.id),
        key=list(key),
        name=artist.name,
        release_count=artist.release_count,
        track_count=artist.track_count,
    )
    return Row(id=model.id, key=key, data=_data(model))


class ArtistsStream:
    """All artists by sort name, with the library counters."""

    name = "library.artists"
    entity_types = frozenset({"artist"})

    def allowed(self, session: SessionInfo) -> bool:
        return True

    def validate(self, params: dict[str, Any]) -> dict[str, Any]:
        return _no_params(params)

    async def meta(self, db: AsyncSession, ctx: StreamContext) -> Meta:
        return await _library_meta(db, "artists")

    def key_query(self, ctx: StreamContext) -> KeyQuery:
        return KeyQuery(query=select(Artist), columns=ARTIST_KEY)

    async def rows(
        self, db: AsyncSession, ctx: StreamContext, after: SortKey | None, limit: int
    ) -> list[Row]:
        key_query = self.key_query(ctx)
        result = await _page(db, key_query, select(Artist), after, limit)
        return [_artist_row(artist) for (artist,) in result]

    async def changes(
        self, db: AsyncSession, ctx: StreamContext, event: ChangeEvent
    ) -> list[RowChange]:
        artist = await db.get(Artist, event.entity_id, populate_existing=True)
        return _remove(event.entity_id) if artist is None else _upsert(_artist_row(artist))


class ArtistStream:
    """One artist by ID (0 or 1 rows), for the artist page header."""

    name = "library.artist"
    entity_types = frozenset({"artist"})

    def allowed(self, session: SessionInfo) -> bool:
        return True

    def validate(self, params: dict[str, Any]) -> dict[str, Any]:
        return _id_param(params, "artist_id")

    async def meta(self, db: AsyncSession, ctx: StreamContext) -> Meta:
        artist = await db.get(Artist, ctx.params["artist_id"], populate_existing=True)
        return Meta(total=0 if artist is None else 1)

    def key_query(self, ctx: StreamContext) -> KeyQuery:
        return KeyQuery(
            query=select(Artist).where(Artist.id == ctx.params["artist_id"]),
            columns=(Artist.id,),
        )

    async def rows(
        self, db: AsyncSession, ctx: StreamContext, after: SortKey | None, limit: int
    ) -> list[Row]:
        key_query = self.key_query(ctx)
        result = await _page(db, key_query, key_query.query, after, limit)
        return [_artist_row(artist, (artist.id,)) for (artist,) in result]

    async def changes(
        self, db: AsyncSession, ctx: StreamContext, event: ChangeEvent
    ) -> list[RowChange]:
        if event.entity_id != ctx.params["artist_id"]:
            return []
        artist = await db.get(Artist, event.entity_id, populate_existing=True)
        if artist is None:
            return _remove(event.entity_id)
        return _upsert(_artist_row(artist, (artist.id,)))


# --- releases -----------------------------------------------------------------------------


def _release_row(release: Release, key: SortKey) -> Row:
    model = LibraryReleaseRow(
        id=str(release.id),
        key=list(key),
        title=release.title,
        album_artist=release.album_artist_display,
        album_artist_id=str(release.album_artist_id),
        edition=release.edition,
        year=release.release_date.year if release.release_date else None,
        disc_count=release.disc_count,
        track_count=release.track_count,
    )
    return Row(id=model.id, key=key, data=_data(model))


class ReleasesStream:
    """All releases by album artist and title, with the library counters."""

    name = "library.releases"
    entity_types = frozenset({"release"})

    def allowed(self, session: SessionInfo) -> bool:
        return True

    def validate(self, params: dict[str, Any]) -> dict[str, Any]:
        return _no_params(params)

    async def meta(self, db: AsyncSession, ctx: StreamContext) -> Meta:
        return await _library_meta(db, "releases")

    def key_query(self, ctx: StreamContext) -> KeyQuery:
        return KeyQuery(query=select(Release), columns=RELEASE_KEY)

    async def rows(
        self, db: AsyncSession, ctx: StreamContext, after: SortKey | None, limit: int
    ) -> list[Row]:
        result = await _page(db, self.key_query(ctx), select(Release), after, limit)
        return [_release_row(release, _release_key(release)) for (release,) in result]

    async def changes(
        self, db: AsyncSession, ctx: StreamContext, event: ChangeEvent
    ) -> list[RowChange]:
        release = await db.get(Release, event.entity_id, populate_existing=True)
        if release is None:
            return _remove(event.entity_id)
        return _upsert(_release_row(release, _release_key(release)))


def _release_key(release: Release) -> SortKey:
    return (release.sort_album_artist, release.sort_title, release.id)


class ReleaseStream:
    """One release by ID (0 or 1 rows), for the album page header."""

    name = "library.release"
    entity_types = frozenset({"release"})

    def allowed(self, session: SessionInfo) -> bool:
        return True

    def validate(self, params: dict[str, Any]) -> dict[str, Any]:
        return _id_param(params, "release_id")

    async def meta(self, db: AsyncSession, ctx: StreamContext) -> Meta:
        release = await db.get(Release, ctx.params["release_id"], populate_existing=True)
        return Meta(total=0 if release is None else 1)

    def key_query(self, ctx: StreamContext) -> KeyQuery:
        return KeyQuery(
            query=select(Release).where(Release.id == ctx.params["release_id"]),
            columns=(Release.id,),
        )

    async def rows(
        self, db: AsyncSession, ctx: StreamContext, after: SortKey | None, limit: int
    ) -> list[Row]:
        key_query = self.key_query(ctx)
        result = await _page(db, key_query, key_query.query, after, limit)
        return [_release_row(release, (release.id,)) for (release,) in result]

    async def changes(
        self, db: AsyncSession, ctx: StreamContext, event: ChangeEvent
    ) -> list[RowChange]:
        if event.entity_id != ctx.params["release_id"]:
            return []
        release = await db.get(Release, event.entity_id, populate_existing=True)
        if release is None:
            return _remove(event.entity_id)
        return _upsert(_release_row(release, (release.id,)))


class ArtistReleasesStream:
    """The releases of one album artist by title."""

    name = "library.artist.releases"
    entity_types = frozenset({"release", service.RELEASE_MOVED})

    def allowed(self, session: SessionInfo) -> bool:
        return True

    def validate(self, params: dict[str, Any]) -> dict[str, Any]:
        return _id_param(params, "artist_id")

    async def meta(self, db: AsyncSession, ctx: StreamContext) -> Meta:
        artist = await db.get(Artist, ctx.params["artist_id"], populate_existing=True)
        return Meta(total=artist.release_count if artist is not None else 0)

    def key_query(self, ctx: StreamContext) -> KeyQuery:
        return KeyQuery(
            query=select(Release).where(Release.album_artist_id == ctx.params["artist_id"]),
            columns=ARTIST_RELEASE_KEY,
        )

    async def rows(
        self, db: AsyncSession, ctx: StreamContext, after: SortKey | None, limit: int
    ) -> list[Row]:
        key_query = self.key_query(ctx)
        result = await _page(db, key_query, key_query.query, after, limit)
        return [_release_row(release, (release.sort_title, release.id)) for (release,) in result]

    async def changes(
        self, db: AsyncSession, ctx: StreamContext, event: ChangeEvent
    ) -> list[RowChange]:
        release = await db.get(Release, event.entity_id, populate_existing=True)
        if release is None:
            return _remove(event.entity_id)
        if release.album_artist_id != ctx.params["artist_id"]:
            # Only a moved release can have been in this list before.
            return _remove(release.id) if event.entity_type == service.RELEASE_MOVED else []
        return _upsert(_release_row(release, (release.sort_title, release.id)))


# --- tracks -------------------------------------------------------------------------------

_TRACK_ROW = (
    select(
        Track,
        Recording,
        Release,
        AudioFile.format,
        AudioFile.sample_rate_hz,
        AudioFile.bit_depth,
        AudioFile.bitrate_kbps,
        AudioFile.effective_quality,
        AudioFile.quality_status,
        Source.label,
        Source.short,
        Source.retrieved_at,
    )
    .join(Recording, Recording.id == Track.recording_id)
    .join(Release, Release.id == Track.release_id)
    .outerjoin(
        AudioFile,
        (AudioFile.recording_id == Track.recording_id)
        & (AudioFile.original_status == OriginalStatus.ACTIVE),
    )
    .outerjoin(Source, Source.id == AudioFile.source_id)
)


def _track_row(result_row, key: SortKey) -> Row:
    """A track row by context (spec: library, Track rows by context)."""
    (track, recording, release, audio_format, sample_rate, bit_depth, bitrate, effective,
     quality_status, source, source_short, retrieved_at) = result_row  # fmt: skip
    model = LibraryTrackRow(
        id=str(track.id),
        key=list(key),
        title=track.context_title or recording.title,
        artist=track.context_artist or recording.artist_display,
        album=release.title,
        album_artist=release.album_artist_display,
        release_id=str(release.id),
        recording_id=str(recording.id),
        disc_number=track.disc_number,
        track_number=track.track_number,
        duration_ms=recording.duration_ms,
        format=audio_format,
        sample_rate_hz=sample_rate,
        bit_depth=bit_depth,
        bitrate_kbps=bitrate,
        effective_quality=effective,
        quality_status=quality_status,
        source=source,
        source_short=source_short,
        retrieved_at=retrieved_at,
    )
    return Row(id=model.id, key=key, data=_data(model))


def _track_key(track: Track) -> SortKey:
    return (track.sort_artist, track.sort_title, track.sort_album, track.id)


def _release_track_key(track: Track) -> SortKey:
    return (track.disc_number, track.track_number, track.id)


async def _load_track(db: AsyncSession, track_id: uuid.UUID):
    return (
        await db.execute(
            _TRACK_ROW.where(Track.id == track_id).execution_options(populate_existing=True)
        )
    ).first()


class TracksStream:
    """All tracks by artist, title and album, with the library counters."""

    name = "library.tracks"
    entity_types = frozenset({"track"})

    def allowed(self, session: SessionInfo) -> bool:
        return True

    def validate(self, params: dict[str, Any]) -> dict[str, Any]:
        return _no_params(params)

    async def meta(self, db: AsyncSession, ctx: StreamContext) -> Meta:
        return await _library_meta(db, "tracks")

    def key_query(self, ctx: StreamContext) -> KeyQuery:
        return KeyQuery(query=select(Track), columns=TRACK_KEY)

    async def rows(
        self, db: AsyncSession, ctx: StreamContext, after: SortKey | None, limit: int
    ) -> list[Row]:
        result = await _page(db, self.key_query(ctx), _TRACK_ROW, after, limit)
        return [_track_row(row, _track_key(row[0])) for row in result]

    async def changes(
        self, db: AsyncSession, ctx: StreamContext, event: ChangeEvent
    ) -> list[RowChange]:
        row = await _load_track(db, event.entity_id)
        if row is None:
            return _remove(event.entity_id)
        return _upsert(_track_row(row, _track_key(row[0])))


class ReleaseTracksStream:
    """The tracks of one release by disc and track number."""

    name = "library.release.tracks"
    entity_types = frozenset({"track", service.TRACK_MOVED})

    def allowed(self, session: SessionInfo) -> bool:
        return True

    def validate(self, params: dict[str, Any]) -> dict[str, Any]:
        return _id_param(params, "release_id")

    async def meta(self, db: AsyncSession, ctx: StreamContext) -> Meta:
        release = await db.get(Release, ctx.params["release_id"], populate_existing=True)
        return Meta(total=release.track_count if release is not None else 0)

    def key_query(self, ctx: StreamContext) -> KeyQuery:
        return KeyQuery(
            query=select(Track).where(Track.release_id == ctx.params["release_id"]),
            columns=RELEASE_TRACK_KEY,
        )

    async def rows(
        self, db: AsyncSession, ctx: StreamContext, after: SortKey | None, limit: int
    ) -> list[Row]:
        query = _TRACK_ROW.where(Track.release_id == ctx.params["release_id"])
        result = await _page(db, self.key_query(ctx), query, after, limit)
        return [_track_row(row, _release_track_key(row[0])) for row in result]

    async def changes(
        self, db: AsyncSession, ctx: StreamContext, event: ChangeEvent
    ) -> list[RowChange]:
        row = await _load_track(db, event.entity_id)
        if row is None:
            return _remove(event.entity_id)
        if row[0].release_id != ctx.params["release_id"]:
            # Only a moved track can have been in this list before.
            return _remove(event.entity_id) if event.entity_type == service.TRACK_MOVED else []
        return _upsert(_track_row(row, _release_track_key(row[0])))


# --- identification summary ------------------------------------------------------------------


class IdentificationStream:
    """One row with the recordings per identification outcome, live through deltas."""

    name = "library.identification"
    entity_types = frozenset({service.IDENTIFICATION})

    def allowed(self, session: SessionInfo) -> bool:
        return session.role in (Role.ADMIN, Role.EDITOR)

    def validate(self, params: dict[str, Any]) -> dict[str, Any]:
        return _no_params(params)

    async def meta(self, db: AsyncSession, ctx: StreamContext) -> Meta:
        return Meta(total=1, counters=await _identification_counts(db))

    def key_query(self, ctx: StreamContext) -> KeyQuery:
        # The single row has no table of its own; anchors are never needed for one row.
        return KeyQuery(
            query=select(Recording).where(Recording.id == service.IDENTIFICATION_SUMMARY_ID),
            columns=(Recording.id,),
        )

    async def rows(
        self, db: AsyncSession, ctx: StreamContext, after: SortKey | None, limit: int
    ) -> list[Row]:
        if after is not None or limit < 1:
            return []
        return [await _identification_row(db)]

    async def changes(
        self, db: AsyncSession, ctx: StreamContext, event: ChangeEvent
    ) -> list[RowChange]:
        return _upsert(await _identification_row(db))


async def _identification_counts(db: AsyncSession) -> dict[str, int]:
    counts = await service.counters(db, tuple(IDENTIFICATION_COUNTERS.values()))
    return {
        status.value: counts[IDENTIFICATION_COUNTERS[status].value]
        for status in IDENTIFICATION_COUNTERS
    }


async def _identification_row(db: AsyncSession) -> Row:
    summary_id = service.IDENTIFICATION_SUMMARY_ID
    model = LibraryIdentificationRow(
        id=str(summary_id), key=[str(summary_id)], **await _identification_counts(db)
    )
    return Row(id=model.id, key=(summary_id,), data=_data(model))


# --- storage summary ------------------------------------------------------------------------


class StorageStream:
    """One row with the number and size of active referenced originals (admins)."""

    name = "library.storage"
    entity_types = frozenset({service.STORAGE})

    def allowed(self, session: SessionInfo) -> bool:
        return session.role == Role.ADMIN

    def validate(self, params: dict[str, Any]) -> dict[str, Any]:
        return _no_params(params)

    async def meta(self, db: AsyncSession, ctx: StreamContext) -> Meta:
        return Meta(total=1, counters=await service.counters(db, REFERENCED_COUNTERS))

    def key_query(self, ctx: StreamContext) -> KeyQuery:
        # A single row without a table of its own, like the identification summary.
        return KeyQuery(
            query=select(Recording).where(Recording.id == service.STORAGE_SUMMARY_ID),
            columns=(Recording.id,),
        )

    async def rows(
        self, db: AsyncSession, ctx: StreamContext, after: SortKey | None, limit: int
    ) -> list[Row]:
        if after is not None or limit < 1:
            return []
        return [await _storage_row(db)]

    async def changes(
        self, db: AsyncSession, ctx: StreamContext, event: ChangeEvent
    ) -> list[RowChange]:
        return _upsert(await _storage_row(db))


async def _storage_row(db: AsyncSession) -> Row:
    summary_id = service.STORAGE_SUMMARY_ID
    model = LibraryStorageRow(
        id=str(summary_id),
        key=[str(summary_id)],
        **await service.counters(db, REFERENCED_COUNTERS),
    )
    return Row(id=model.id, key=(summary_id,), data=_data(model))


# --- superseded files ---------------------------------------------------------------------

SUPERSEDED_KEY = (AudioFile.path, AudioFile.id)
_REPLACEMENT = aliased(AudioFile)
_SUPERSEDED_ROW = (
    select(AudioFile, Recording, _REPLACEMENT.path)
    .join(Recording, Recording.id == AudioFile.recording_id)
    .outerjoin(_REPLACEMENT, _REPLACEMENT.id == AudioFile.superseded_by_id)
    .where(AudioFile.original_status == OriginalStatus.SUPERSEDED)
)


def _superseded_row(result_row) -> Row:
    audio_file, recording, replaced_by_path = result_row
    key = (audio_file.path, audio_file.id)
    model = LibrarySupersededRow(
        id=str(audio_file.id),
        key=list(key),
        path=audio_file.path,
        size_bytes=audio_file.size_bytes,
        format=audio_file.format,
        storage_mode=audio_file.storage_mode,
        recording_id=str(recording.id),
        title=recording.title,
        artist=recording.artist_display,
        superseded_at=audio_file.superseded_at.isoformat() if audio_file.superseded_at else None,
        replaced_by_id=str(audio_file.superseded_by_id) if audio_file.superseded_by_id else None,
        replaced_by_path=replaced_by_path,
    )
    return Row(id=model.id, key=key, data=_data(model))


class SupersededFilesStream:
    """Report of superseded originals by path (admins only), with counts and sizes in total and
    of the managed ones (deletable)."""

    name = "library.superseded"
    entity_types = frozenset({service.SUPERSEDED_FILE})

    def allowed(self, session: SessionInfo) -> bool:
        return session.role == Role.ADMIN

    def validate(self, params: dict[str, Any]) -> dict[str, Any]:
        return _no_params(params)

    async def meta(self, db: AsyncSession, ctx: StreamContext) -> Meta:
        counters = await service.counters(db, SUPERSEDED_COUNTERS)
        return Meta(total=counters["superseded_files"], counters=counters)

    def key_query(self, ctx: StreamContext) -> KeyQuery:
        return KeyQuery(
            query=select(AudioFile).where(AudioFile.original_status == OriginalStatus.SUPERSEDED),
            columns=SUPERSEDED_KEY,
        )

    async def rows(
        self, db: AsyncSession, ctx: StreamContext, after: SortKey | None, limit: int
    ) -> list[Row]:
        result = await _page(db, self.key_query(ctx), _SUPERSEDED_ROW, after, limit)
        return [_superseded_row(row) for row in result]

    async def changes(
        self, db: AsyncSession, ctx: StreamContext, event: ChangeEvent
    ) -> list[RowChange]:
        row = (
            await db.execute(
                _SUPERSEDED_ROW.where(AudioFile.id == event.entity_id).execution_options(
                    populate_existing=True
                )
            )
        ).first()
        return _remove(event.entity_id) if row is None else _upsert(_superseded_row(row))


# --- maintenance -----------------------------------------------------------------------------

RUN_KEY = (MaintenanceRun.started_at, MaintenanceRun.id)
COUNTS = (
    "orphan_files",
    "orphan_bytes",
    "leftover_files",
    "leftover_bytes",
    "missing_files",
    "missing_bytes",
    "deleted_files",
    "deleted_bytes",
    "listed_files",
    "listed_bytes",
)


def _iso(value) -> str | None:
    return value.isoformat() if value is not None else None


def _run_row(run: MaintenanceRun) -> Row:
    key = (run.started_at, run.id)
    model = MaintenanceRunRow(
        id=str(run.id),
        key=[_iso(run.started_at), str(run.id)],
        job_id=str(run.job_id) if run.job_id else None,
        trigger=run.trigger,
        status=run.status,
        action=run.action,
        grace_hours=run.grace_hours,
        safety_share_percent=run.safety_share_percent,
        safety_limit=run.safety_limit,
        managed_files=run.managed_files,
        started_at=_iso(run.started_at),
        finished_at=_iso(run.finished_at),
        error=run.error,
        **{name: getattr(run, name) for name in COUNTS},
    )
    return Row(id=model.id, key=key, data=_data(model))


class MaintenanceRunsStream:
    """Maintenance runs with their results, newest first (admins only)."""

    name = "library.maintenance"
    entity_types = frozenset({maintenance.RUN})

    def allowed(self, session: SessionInfo) -> bool:
        return session.role == Role.ADMIN

    def validate(self, params: dict[str, Any]) -> dict[str, Any]:
        return _no_params(params)

    async def meta(self, db: AsyncSession, ctx: StreamContext) -> Meta:
        # Few rows (the newest runs are kept): counted directly.
        total = await db.scalar(select(func.count()).select_from(MaintenanceRun))
        return Meta(total=total or 0)

    def key_query(self, ctx: StreamContext) -> KeyQuery:
        return KeyQuery(query=select(MaintenanceRun), columns=RUN_KEY, descending=True)

    async def rows(
        self, db: AsyncSession, ctx: StreamContext, after: SortKey | None, limit: int
    ) -> list[Row]:
        result = await _page(db, self.key_query(ctx), select(MaintenanceRun), after, limit)
        return [_run_row(run) for (run,) in result]

    async def changes(
        self, db: AsyncSession, ctx: StreamContext, event: ChangeEvent
    ) -> list[RowChange]:
        run = await db.get(MaintenanceRun, event.entity_id, populate_existing=True)
        return _remove(event.entity_id) if run is None else _upsert(_run_row(run))


def _finding_row(finding: MaintenanceFinding) -> Row:
    model = MaintenanceFindingRow(
        id=str(finding.id),
        key=[finding.path],
        path=finding.path,
        kind=finding.kind,
        size_bytes=finding.size_bytes,
        modified_at=_iso(finding.modified_at),
        outcome=finding.outcome,
        detail=finding.detail,
    )
    return Row(id=model.id, key=(finding.path,), data=_data(model))


class MaintenanceFindingsStream:
    """The files one maintenance run found, by path (admins only); the totals come from the
    run's counts."""

    name = "library.maintenance.findings"
    entity_types = frozenset({maintenance.FINDING})

    def allowed(self, session: SessionInfo) -> bool:
        return session.role == Role.ADMIN

    def validate(self, params: dict[str, Any]) -> dict[str, Any]:
        return _id_param(params, "run_id")

    async def meta(self, db: AsyncSession, ctx: StreamContext) -> Meta:
        run = await db.get(MaintenanceRun, ctx.params["run_id"], populate_existing=True)
        if run is None:
            return Meta(total=0)
        counters = {name: getattr(run, name) for name in COUNTS}
        total = run.orphan_files + run.leftover_files + run.missing_files
        return Meta(total=total, counters=counters)

    def key_query(self, ctx: StreamContext) -> KeyQuery:
        return KeyQuery(
            query=select(MaintenanceFinding).where(
                MaintenanceFinding.run_id == ctx.params["run_id"]
            ),
            columns=(MaintenanceFinding.path,),
        )

    async def rows(
        self, db: AsyncSession, ctx: StreamContext, after: SortKey | None, limit: int
    ) -> list[Row]:
        key_query = self.key_query(ctx)
        result = await _page(db, key_query, key_query.query, after, limit)
        return [_finding_row(finding) for (finding,) in result]

    async def changes(
        self, db: AsyncSession, ctx: StreamContext, event: ChangeEvent
    ) -> list[RowChange]:
        finding = await db.get(MaintenanceFinding, event.entity_id, populate_existing=True)
        if finding is None:
            return _remove(event.entity_id)
        if finding.run_id != ctx.params["run_id"]:
            return []
        return _upsert(_finding_row(finding))


def _data(model) -> dict[str, Any]:
    """Row fields without ``id`` and ``key`` (the protocol adds those from the row)."""
    return model.model_dump(mode="json", exclude={"id", "key"})


STREAMS = (
    ArtistsStream,
    ArtistStream,
    ReleasesStream,
    ReleaseStream,
    ArtistReleasesStream,
    ReleaseTracksStream,
    TracksStream,
    SupersededFilesStream,
    IdentificationStream,
    StorageStream,
    MaintenanceRunsStream,
    MaintenanceFindingsStream,
)


# Row builders for other lists of library items (search results).
TRACK_ROW = _TRACK_ROW
artist_row = _artist_row
release_row = _release_row
track_row = _track_row
