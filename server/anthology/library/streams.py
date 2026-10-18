"""Streams of the library domain (spec: library, Library lists).

Every list is one index range scan on the table it lists (sort keys are denormalized onto
its rows); totals come from maintained counters. Rows of a chunk are completed with
primary-key joins.
"""

import uuid
from typing import Any

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from anthology.library import service
from anthology.library.models import Artist, AudioFile, Recording, Release, Track
from anthology.library.schemas import LibraryArtistRow, LibraryReleaseRow, LibraryTrackRow
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
    )
    .join(Recording, Recording.id == Track.recording_id)
    .join(Release, Release.id == Track.release_id)
    .outerjoin(AudioFile, AudioFile.recording_id == Track.recording_id)
)


def _track_row(result_row, key: SortKey) -> Row:
    """A track row by context (spec: library, Track rows by context)."""
    track, recording, release, audio_format, sample_rate, bit_depth, bitrate = result_row
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
)
