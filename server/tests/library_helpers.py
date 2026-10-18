"""Building small libraries and checking their maintained values in tests."""

import itertools
import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from anthology.core.changes import ChangeLog
from anthology.library import service
from anthology.library.models import (
    Artist,
    AudioFormat,
    QualityTier,
    Recording,
    Release,
    Track,
)
from anthology.library.service import AudioFileInfo, sort_key

_paths = itertools.count()


def audio(path: str | None = None) -> AudioFileInfo:
    return AudioFileInfo(
        path=path or f"/library/_originals/{next(_paths)}-{uuid.uuid4()}.flac",
        format=AudioFormat.FLAC,
        codec="flac",
        sample_rate_hz=44_100,
        bit_depth=16,
        channels=2,
        size_bytes=30_000_000,
        audio_hash=uuid.uuid4().hex,
        declared_quality=QualityTier.CD_LOSSLESS,
    )


async def album(
    session: AsyncSession, artist_name: str, title: str, tracks: list[str]
) -> tuple[Release, list[Track]]:
    """A release by ``artist_name`` with one new recording per title."""
    artist = await service.get_or_create_artist(session, artist_name)
    release = await service.create_release(session, title=title, album_artist=artist)
    created = [
        await service.add_recording(
            session,
            release=release,
            title=track_title,
            artist=artist,
            duration_ms=180_000 + number,
            track_number=number,
            audio=audio(),
        )
        for number, track_title in enumerate(tracks, start=1)
    ]
    return release, created


async def change_mark(session: AsyncSession) -> int:
    return await session.scalar(select(func.coalesce(func.max(ChangeLog.id), 0))) or 0


async def changes_since(session: AsyncSession, mark: int) -> list[tuple[str, uuid.UUID, str]]:
    rows = await session.execute(
        select(ChangeLog.entity_type, ChangeLog.entity_id, ChangeLog.operation)
        .where(ChangeLog.id > mark)
        .order_by(ChangeLog.id)
    )
    return [(entity_type, entity_id, operation.value) for entity_type, entity_id, operation in rows]


async def assert_consistent(session: AsyncSession) -> None:
    """Counters, per-entity counts and sort keys equal a recomputation from the data."""
    session.expire_all()
    counted = {
        "artists": await session.scalar(select(func.count()).select_from(Artist)),
        "releases": await session.scalar(select(func.count()).select_from(Release)),
        "tracks": await session.scalar(select(func.count()).select_from(Track)),
        "recordings": await session.scalar(select(func.count()).select_from(Recording)),
    }
    assert await service.counters(session) == counted

    for artist in await session.scalars(select(Artist)):
        releases = await session.scalar(
            select(func.count()).where(Release.album_artist_id == artist.id)
        )
        tracks = await session.scalar(
            select(func.count())
            .select_from(Track)
            .join(Recording, Recording.id == Track.recording_id)
            .where(Recording.artist_id == artist.id)
        )
        assert (artist.release_count, artist.track_count) == (releases, tracks), artist.name

    for release in await session.scalars(select(Release)):
        album_artist = await session.get_one(Artist, release.album_artist_id)
        tracks = await session.scalar(select(func.count()).where(Track.release_id == release.id))
        assert release.track_count == tracks
        assert release.sort_title == sort_key(release.title)
        assert release.sort_album_artist == album_artist.sort_name

    rows = await session.execute(
        select(Track, Recording, Release, Artist)
        .join(Recording, Recording.id == Track.recording_id)
        .join(Release, Release.id == Track.release_id)
        .join(Artist, Artist.id == Recording.artist_id)
    )
    for track, recording, release, artist in rows:
        assert track.sort_title == sort_key(track.context_title or recording.title)
        assert track.sort_artist == (
            sort_key(track.context_artist) if track.context_artist else artist.sort_name
        )
        assert track.sort_album == release.sort_title
