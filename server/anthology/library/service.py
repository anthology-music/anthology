"""Library writes: the only place that changes library data (spec: library).

Every write keeps the denormalized sort keys, the maintained counters and the change log
consistent, so callers (import, tagging, metadata lookup) cannot forget them. A change that
alters what other list rows show or sort by writes a change entry for each of those rows
(spec: Deltas for derived values).
"""

import enum
import unicodedata
import uuid
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from sqlalchemy import exists, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from anthology.core.changes import (
    ChangeOperation,
    ChangeScope,
    record_audit,
    record_change,
    record_changes,
)
from anthology.db.types import utcnow
from anthology.library.models import (
    IDENTIFICATION_COUNTERS,
    LIBRARY_COUNTERS,
    QUALITY_COUNTERS,
    Artist,
    AudioFile,
    AudioFormat,
    Counter,
    IdentificationStatus,
    LibraryCounter,
    OriginalStatus,
    QualityStatus,
    QualityTier,
    Recording,
    Release,
    ReleaseGroup,
    ReleaseGroupType,
    StorageMode,
    Track,
)
from anthology.metadata_lookup.service import register_external_ref, unregister_external_ref

# Change entry written when a release leaves the list of its former album artist.
RELEASE_MOVED = "release.moved"
# Change entry written when a track moves to another release (written by tag editing).
TRACK_MOVED = "track.moved"
# Change entries of the report of superseded files (one per file entering or leaving it).
SUPERSEDED_FILE = "superseded_file"
# Change entries of the quality summary (stream quality_analysis.summary).
QUALITY = "quality_summary"
QUALITY_SUMMARY_ID = uuid.UUID("4c1e9b72-0d3a-4f86-b5e2-7a9c3d1f6e08")
# Change entries of the storage summary (stream library.storage: referenced originals).
STORAGE = "library_storage"
STORAGE_SUMMARY_ID = uuid.UUID("8f3c2a91-5d4e-4b7a-9c61-0e2f7d8a4b13")


def sort_key(text: str) -> str:
    """Normalized sort key: no case, no diacritics, single spaces (spec: Normalized sort keys)."""
    decomposed = unicodedata.normalize("NFKD", text)
    stripped = "".join(char for char in decomposed if not unicodedata.combining(char))
    return " ".join(stripped.casefold().split())


@dataclass(frozen=True)
class AudioFileInfo:
    """Technical description of an original as read by import or acquisition."""

    path: str
    format: AudioFormat
    codec: str
    sample_rate_hz: int
    channels: int
    size_bytes: int
    audio_hash: str
    declared_quality: QualityTier
    bitrate_kbps: int | None = None
    bit_depth: int | None = None
    storage_mode: StorageMode = StorageMode.MANAGED
    # Opt-in of the import for referenced files (spec: library, Managed and referenced originals).
    tag_writes_allowed: bool = False
    # SHA-256 of the whole file, when known (verified transfers).
    content_hash: str | None = None


def _audio_file(
    recording_id: uuid.UUID, audio: AudioFileInfo, home_track_id: uuid.UUID | None
) -> AudioFile:
    return AudioFile(
        id=uuid.uuid4(),
        recording_id=recording_id,
        path=audio.path,
        format=audio.format,
        codec=audio.codec,
        bitrate_kbps=audio.bitrate_kbps,
        sample_rate_hz=audio.sample_rate_hz,
        bit_depth=audio.bit_depth,
        channels=audio.channels,
        size_bytes=audio.size_bytes,
        audio_hash=audio.audio_hash,
        content_hash=audio.content_hash,
        declared_quality=audio.declared_quality,
        storage_mode=audio.storage_mode,
        original_status=OriginalStatus.ACTIVE,
        tag_writes_allowed=audio.storage_mode == StorageMode.REFERENCED
        and audio.tag_writes_allowed,
        home_track_id=home_track_id,
    )


# --- counters and change entries ----------------------------------------------------------


async def adjust_counter(session: AsyncSession, counter: Counter, delta: int) -> None:
    result = await session.execute(
        update(LibraryCounter)
        .where(LibraryCounter.name == counter)
        .values(value=LibraryCounter.value + delta)
    )
    if not result.rowcount:
        session.add(LibraryCounter(name=counter, value=max(0, delta)))
        await session.flush()


async def counters(
    session: AsyncSession, names: tuple[Counter, ...] = LIBRARY_COUNTERS
) -> dict[str, int]:
    """Maintained counters, by default the four library counters (missing rows count as 0)."""
    values = {counter.value: 0 for counter in names}
    for row in await session.scalars(select(LibraryCounter).where(LibraryCounter.name.in_(names))):
        values[row.name.value] = row.value
    return values


async def _changed(
    session: AsyncSession,
    entity_type: str,
    entity_id: uuid.UUID,
    operation: ChangeOperation = ChangeOperation.UPDATE,
) -> None:
    await record_change(
        session,
        entity_type=entity_type,
        entity_id=entity_id,
        operation=operation,
        scope=ChangeScope.SHARED,
    )


async def _rows_changed(session: AsyncSession, entity_type: str, ids: Iterable[uuid.UUID]) -> None:
    await record_changes(
        session,
        entity_type=entity_type,
        entity_ids=ids,
        operation=ChangeOperation.UPDATE,
        scope=ChangeScope.SHARED,
    )


async def _audit(
    session: AsyncSession,
    entity_type: str,
    entity_id: uuid.UUID,
    action: str,
    user_id: uuid.UUID | None,
    diff: dict[str, Any],
) -> None:
    await record_audit(
        session,
        entity_type=entity_type,
        entity_id=entity_id,
        action=action,
        user_id=user_id,
        diff=diff,
    )


def _apply(entity: Any, fields: dict[str, Any]) -> dict[str, list[Any]]:
    """Set changed fields on ``entity``; return the audit diff ``{field: [old, new]}``."""
    diff = {}
    for name, value in fields.items():
        old = getattr(entity, name)
        if old != value:
            diff[name] = [old, value]
            setattr(entity, name, value)
    return diff


# --- creation -----------------------------------------------------------------------------


async def get_or_create_artist(
    session: AsyncSession,
    name: str,
    *,
    sort_name: str | None = None,
    mb_artist_id: uuid.UUID | None = None,
    user_id: uuid.UUID | None = None,
) -> Artist:
    """Find an artist by MusicBrainz ID, otherwise by exact name, or create it."""
    if mb_artist_id is not None:
        found = await session.scalar(select(Artist).where(Artist.mb_artist_id == mb_artist_id))
    else:
        found = await session.scalar(
            select(Artist).where(Artist.name == name, Artist.mb_artist_id.is_(None)).limit(1)
        )
    if found is not None:
        return found
    artist = Artist(
        id=uuid.uuid4(),
        name=name,
        sort_name=sort_key(sort_name or name),
        mb_artist_id=mb_artist_id,
        release_count=0,
        track_count=0,
    )
    session.add(artist)
    await session.flush()
    await adjust_counter(session, Counter.ARTISTS, +1)
    await _changed(session, "artist", artist.id, ChangeOperation.INSERT)
    await _audit(session, "artist", artist.id, "create", user_id, {"name": [None, name]})
    return artist


async def create_release(
    session: AsyncSession,
    *,
    title: str,
    album_artist: Artist,
    album_artist_display: str | None = None,
    release_group: ReleaseGroup | None = None,
    group_type: ReleaseGroupType = ReleaseGroupType.ALBUM,
    edition: str | None = None,
    country: str | None = None,
    release_date: date | None = None,
    label: str | None = None,
    disc_count: int = 1,
    mb_release_id: uuid.UUID | None = None,
    mb_release_group_id: uuid.UUID | None = None,
    user_id: uuid.UUID | None = None,
) -> Release:
    """Create a release (and its release group unless one is given)."""
    if release_group is None:
        release_group = ReleaseGroup(
            id=uuid.uuid4(), title=title, type=group_type, mb_release_group_id=mb_release_group_id
        )
        session.add(release_group)
        await session.flush()
        await _changed(session, "release_group", release_group.id, ChangeOperation.INSERT)
    release = Release(
        id=uuid.uuid4(),
        release_group_id=release_group.id,
        title=title,
        album_artist_id=album_artist.id,
        album_artist_display=album_artist_display or album_artist.name,
        edition=edition,
        country=country,
        release_date=release_date,
        label=label,
        disc_count=disc_count,
        track_count=0,
        sort_title=sort_key(title),
        sort_album_artist=album_artist.sort_name,
        mb_release_id=mb_release_id,
    )
    session.add(release)
    album_artist.release_count += 1
    await session.flush()
    await adjust_counter(session, Counter.RELEASES, +1)
    await _changed(session, "release", release.id, ChangeOperation.INSERT)
    await _changed(session, "artist", album_artist.id)
    await _audit(session, "release", release.id, "create", user_id, {"title": [None, title]})
    return release


async def add_recording(
    session: AsyncSession,
    *,
    release: Release,
    title: str,
    artist: Artist,
    duration_ms: int,
    track_number: int,
    audio: AudioFileInfo,
    disc_number: int = 1,
    artist_display: str | None = None,
    context_title: str | None = None,
    context_artist: str | None = None,
    isrc: str | None = None,
    mb_recording_id: uuid.UUID | None = None,
    acoust_id: uuid.UUID | None = None,
    recording_id: uuid.UUID | None = None,
    user_id: uuid.UUID | None = None,
) -> Track:
    """Create a recording with its original and its home track context on ``release``.

    ``recording_id`` is given when the original's managed file name was chosen before.
    """
    recording = Recording(
        id=recording_id or uuid.uuid4(),
        title=title,
        artist_id=artist.id,
        artist_display=artist_display or artist.name,
        duration_ms=duration_ms,
        isrc=isrc,
        mb_recording_id=mb_recording_id,
        acoust_id=acoust_id,
    )
    session.add(recording)
    await session.flush()
    await adjust_counter(session, Counter.RECORDINGS, +1)
    await adjust_counter(session, Counter.IDENTIFICATION_UNCHECKED, +1)
    await _changed(session, "recording", recording.id, ChangeOperation.INSERT)
    await _audit(session, "recording", recording.id, "create", user_id, {"title": [None, title]})

    track = await add_track(
        session,
        release=release,
        recording=recording,
        track_number=track_number,
        disc_number=disc_number,
        context_title=context_title,
        context_artist=context_artist,
        user_id=user_id,
        artist=artist,
    )
    audio_file = _audio_file(recording.id, audio, track.id)
    session.add(audio_file)
    await session.flush()
    await _referenced(session, audio_file, +1)
    await _quality_counted(session, audio_file, +1)
    await _changed(session, "audio_file", audio_file.id, ChangeOperation.INSERT)
    return track


async def _quality_counted(session: AsyncSession, audio_file: AudioFile, sign: int) -> None:
    """Keep the active originals per quality status (spec: quality-analysis, Quality overview)."""
    await adjust_counter(session, QUALITY_COUNTERS[audio_file.quality_status], sign)
    await _changed(session, QUALITY, QUALITY_SUMMARY_ID)


async def _referenced(session: AsyncSession, audio_file: AudioFile, sign: int) -> None:
    """Keep the counters of active referenced originals (spec: library, adoption)."""
    if audio_file.storage_mode != StorageMode.REFERENCED:
        return
    await adjust_counter(session, Counter.REFERENCED_FILES, sign)
    await adjust_counter(session, Counter.REFERENCED_BYTES, sign * audio_file.size_bytes)
    await _changed(session, STORAGE, STORAGE_SUMMARY_ID)


async def add_track(
    session: AsyncSession,
    *,
    release: Release,
    recording: Recording,
    track_number: int,
    disc_number: int = 1,
    context_title: str | None = None,
    context_artist: str | None = None,
    user_id: uuid.UUID | None = None,
    artist: Artist | None = None,
) -> Track:
    """Add a track context for an existing recording (no second original)."""
    if artist is None:
        artist = await session.get_one(Artist, recording.artist_id)
    track = Track(
        id=uuid.uuid4(),
        release_id=release.id,
        recording_id=recording.id,
        disc_number=disc_number,
        track_number=track_number,
        context_title=context_title,
        context_artist=context_artist,
        sort_artist=sort_key(context_artist) if context_artist else artist.sort_name,
        sort_title=sort_key(context_title or recording.title),
        sort_album=release.sort_title,
    )
    session.add(track)
    release.track_count += 1
    artist.track_count += 1
    await session.flush()
    await adjust_counter(session, Counter.TRACKS, +1)
    await _changed(session, "track", track.id, ChangeOperation.INSERT)
    await _changed(session, "release", release.id)
    await _changed(session, "artist", artist.id)
    await _audit(
        session,
        "track",
        track.id,
        "create",
        user_id,
        {"release_id": [None, str(release.id)], "recording_id": [None, str(recording.id)]},
    )
    return track


# --- updates ------------------------------------------------------------------------------

_UNSET: Any = object()


async def update_artist(
    session: AsyncSession,
    artist: Artist,
    *,
    name: str = _UNSET,
    sort_name: str = _UNSET,
    mb_artist_id: uuid.UUID | None = _UNSET,
    user_id: uuid.UUID | None = None,
) -> None:
    """Change an artist; credits equal to the old name follow the new name.

    The sort name follows a renamed artist while it is still the default (the normalized
    old name). Credits such as "A feat. B" stay as they are (edited by tag editing).
    """
    old_name, old_sort = artist.name, artist.sort_name
    fields: dict[str, Any] = {}
    if name is not _UNSET:
        fields["name"] = name
        if sort_name is _UNSET and old_sort == sort_key(old_name):
            fields["sort_name"] = sort_key(name)
    if sort_name is not _UNSET:
        fields["sort_name"] = sort_key(sort_name)
    if mb_artist_id is not _UNSET:
        fields["mb_artist_id"] = mb_artist_id
    diff = _apply(artist, fields)
    if not diff:
        return
    await session.flush()
    await _changed(session, "artist", artist.id)
    await _audit(session, "artist", artist.id, "update", user_id, diff)
    if "name" not in diff and "sort_name" not in diff:
        return

    of_artist = select(Recording.id).where(Recording.artist_id == artist.id)
    if "name" in diff:
        await session.execute(
            update(Recording)
            .where(Recording.artist_id == artist.id, Recording.artist_display == old_name)
            .values(artist_display=artist.name)
            .execution_options(synchronize_session=False)
        )
        await session.execute(
            update(Release)
            .where(Release.album_artist_id == artist.id, Release.album_artist_display == old_name)
            .values(album_artist_display=artist.name)
            .execution_options(synchronize_session=False)
        )
    if "sort_name" in diff:
        await session.execute(
            update(Release)
            .where(Release.album_artist_id == artist.id)
            .values(sort_album_artist=artist.sort_name)
            .execution_options(synchronize_session=False)
        )
        await session.execute(
            update(Track)
            .where(Track.recording_id.in_(of_artist), Track.context_artist.is_(None))
            .values(sort_artist=artist.sort_name)
            .execution_options(synchronize_session=False)
        )

    releases = list(
        await session.scalars(select(Release.id).where(Release.album_artist_id == artist.id))
    )
    tracks = await session.scalars(
        select(Track.id).where(
            or_(
                Track.recording_id.in_(of_artist),
                Track.release_id.in_(
                    select(Release.id).where(Release.album_artist_id == artist.id)
                ),
            )
        )
    )
    await _rows_changed(session, "release", releases)
    await _rows_changed(session, "track", tracks)


async def update_release(
    session: AsyncSession,
    release: Release,
    *,
    title: str = _UNSET,
    album_artist: Artist = _UNSET,
    album_artist_display: str = _UNSET,
    edition: str | None = _UNSET,
    country: str | None = _UNSET,
    release_date: date | None = _UNSET,
    label: str | None = _UNSET,
    disc_count: int = _UNSET,
    mb_release_id: uuid.UUID | None = _UNSET,
    user_id: uuid.UUID | None = None,
) -> None:
    """Change a release; its tracks follow title and album artist."""
    fields: dict[str, Any] = {
        key: value
        for key, value in {
            "title": title,
            "album_artist_display": album_artist_display,
            "edition": edition,
            "country": country,
            "release_date": release_date,
            "label": label,
            "disc_count": disc_count,
            "mb_release_id": mb_release_id,
        }.items()
        if value is not _UNSET
    }
    old_artist_id = release.album_artist_id
    if title is not _UNSET:
        fields["sort_title"] = sort_key(title)
    if album_artist is not _UNSET and album_artist.id != old_artist_id:
        fields["album_artist_id"] = album_artist.id
        fields["sort_album_artist"] = album_artist.sort_name
        if album_artist_display is _UNSET:
            fields["album_artist_display"] = album_artist.name
    diff = _apply(release, fields)
    if not diff:
        return
    await session.flush()
    await _changed(session, "release", release.id)
    await _audit(session, "release", release.id, "update", user_id, _public(diff))

    if "album_artist_id" in diff:
        old_artist = await session.get_one(Artist, old_artist_id)
        old_artist.release_count -= 1
        album_artist.release_count += 1
        await session.flush()
        await _changed(session, RELEASE_MOVED, release.id)
        await _changed(session, "artist", album_artist.id)
        await _changed(session, "artist", old_artist.id)
        await remove_if_orphaned(session, old_artist, user_id=user_id)
    if "sort_title" in diff:
        await session.execute(
            update(Track)
            .where(Track.release_id == release.id)
            .values(sort_album=release.sort_title)
            .execution_options(synchronize_session=False)
        )
    if diff.keys() & {"title", "album_artist_id", "album_artist_display"}:
        tracks = await session.scalars(select(Track.id).where(Track.release_id == release.id))
        await _rows_changed(session, "track", tracks)


async def update_recording(
    session: AsyncSession,
    recording: Recording,
    *,
    title: str = _UNSET,
    artist: Artist = _UNSET,
    artist_display: str = _UNSET,
    duration_ms: int = _UNSET,
    isrc: str | None = _UNSET,
    mb_recording_id: uuid.UUID | None = _UNSET,
    acoust_id: uuid.UUID | None = _UNSET,
    composers: list[str] = _UNSET,
    genres: list[str] = _UNSET,
    user_id: uuid.UUID | None = None,
) -> None:
    """Change a recording; all its track contexts follow (unless they override a value)."""
    fields: dict[str, Any] = {
        key: value
        for key, value in {
            "title": title,
            "artist_display": artist_display,
            "duration_ms": duration_ms,
            "isrc": isrc,
            "mb_recording_id": mb_recording_id,
            "acoust_id": acoust_id,
            "composers": list(composers) if composers is not _UNSET else _UNSET,
            "genres": list(genres) if genres is not _UNSET else _UNSET,
        }.items()
        if value is not _UNSET
    }
    old_artist_id = recording.artist_id
    if artist is not _UNSET and artist.id != old_artist_id:
        fields["artist_id"] = artist.id
        if artist_display is _UNSET:
            fields["artist_display"] = artist.name
    diff = _apply(recording, fields)
    if not diff:
        return
    await session.flush()
    await _changed(session, "recording", recording.id)
    await _audit(session, "recording", recording.id, "update", user_id, _public(diff))

    of_recording = Track.recording_id == recording.id
    if "artist_id" in diff:
        count = await session.scalar(select(func.count()).where(of_recording)) or 0
        old_artist = await session.get_one(Artist, old_artist_id)
        old_artist.track_count -= count
        artist.track_count += count
        await session.flush()
        await session.execute(
            update(Track)
            .where(of_recording, Track.context_artist.is_(None))
            .values(sort_artist=artist.sort_name)
            .execution_options(synchronize_session=False)
        )
        await _changed(session, "artist", artist.id)
        await _changed(session, "artist", old_artist.id)
        await remove_if_orphaned(session, old_artist, user_id=user_id)
    if "title" in diff:
        await session.execute(
            update(Track)
            .where(of_recording, Track.context_title.is_(None))
            .values(sort_title=sort_key(recording.title))
            .execution_options(synchronize_session=False)
        )
    if diff.keys() & {"title", "artist_id", "artist_display", "duration_ms"}:
        tracks = await session.scalars(select(Track.id).where(of_recording))
        await _rows_changed(session, "track", tracks)


async def update_track(
    session: AsyncSession,
    track: Track,
    *,
    context_title: str | None = _UNSET,
    context_artist: str | None = _UNSET,
    disc_number: int = _UNSET,
    track_number: int = _UNSET,
    user_id: uuid.UUID | None = None,
) -> None:
    """Change the context-specific values of a track."""
    fields: dict[str, Any] = {
        key: value
        for key, value in {
            "context_title": context_title,
            "context_artist": context_artist,
            "disc_number": disc_number,
            "track_number": track_number,
        }.items()
        if value is not _UNSET
    }
    diff = _apply(track, fields)
    if not diff:
        return
    if diff.keys() & {"context_title", "context_artist"}:
        recording = await session.get_one(Recording, track.recording_id, populate_existing=True)
        artist = await session.get_one(Artist, recording.artist_id)
        track.sort_title = sort_key(track.context_title or recording.title)
        track.sort_artist = (
            sort_key(track.context_artist) if track.context_artist else artist.sort_name
        )
    await session.flush()
    await _changed(session, "track", track.id)
    await _audit(session, "track", track.id, "update", user_id, diff)


async def find_or_create_release(
    session: AsyncSession,
    title: str,
    album_artist: Artist,
    *,
    like: Release | None = None,
    user_id: uuid.UUID | None = None,
) -> Release:
    """The release with this title (sort key) and album artist, or a new one that takes the
    other values (year, label, type) from ``like``."""
    found = await session.scalar(
        select(Release)
        .where(Release.sort_title == sort_key(title), Release.album_artist_id == album_artist.id)
        .order_by(Release.id)
        .limit(1)
    )
    if found is not None:
        return found
    group_type = ReleaseGroupType.ALBUM
    if like is not None:
        group = await session.get(ReleaseGroup, like.release_group_id)
        group_type = group.type if group is not None else group_type
    return await create_release(
        session,
        title=title,
        album_artist=album_artist,
        group_type=group_type,
        release_date=like.release_date if like is not None else None,
        label=like.label if like is not None else None,
        user_id=user_id,
    )


async def move_track(
    session: AsyncSession, track: Track, release: Release, *, user_id: uuid.UUID | None = None
) -> None:
    """Move a track context to another release (spec: tagging, Moving tracks by album); its
    position stays. A release left without tracks is removed."""
    old = await session.get_one(Release, track.release_id)
    if old.id == release.id:
        return
    track.release_id = release.id
    track.sort_album = release.sort_title
    old.track_count -= 1
    release.track_count += 1
    release.disc_count = max(release.disc_count, track.disc_number)
    await session.flush()
    await _changed(session, TRACK_MOVED, track.id)
    await _changed(session, "track", track.id)
    await _changed(session, "release", old.id)
    await _changed(session, "release", release.id)
    await _audit(
        session,
        "track",
        track.id,
        "move",
        user_id,
        {"release_id": [str(old.id), str(release.id)]},
    )
    if old.track_count == 0:
        await remove_release(session, old, user_id=user_id)


async def remove_release(
    session: AsyncSession, release: Release, *, user_id: uuid.UUID | None = None
) -> None:
    """Remove a release without tracks, its release group if no other release uses it, and an
    album artist left without releases or recordings."""
    if await session.scalar(select(exists().where(Track.release_id == release.id))):
        raise ValueError("release still has tracks")
    album_artist = await session.get_one(Artist, release.album_artist_id)
    group_id = release.release_group_id
    await session.delete(release)
    album_artist.release_count -= 1
    await session.flush()
    await adjust_counter(session, Counter.RELEASES, -1)
    await _changed(session, "release", release.id, ChangeOperation.DELETE)
    await _changed(session, "artist", album_artist.id)
    await _audit(
        session, "release", release.id, "delete", user_id, {"title": [release.title, None]}
    )
    if not await session.scalar(select(exists().where(Release.release_group_id == group_id))):
        group = await session.get(ReleaseGroup, group_id)
        if group is not None:
            await session.delete(group)
            await session.flush()
            await _changed(session, "release_group", group_id, ChangeOperation.DELETE)
    await remove_if_orphaned(session, album_artist, user_id=user_id)


async def remove_if_orphaned(
    session: AsyncSession, artist: Artist, *, user_id: uuid.UUID | None = None
) -> bool:
    """Remove an artist that no recording or release references any more."""
    referenced = await session.scalar(
        select(
            or_(
                exists().where(Recording.artist_id == artist.id),
                exists().where(Release.album_artist_id == artist.id),
            )
        )
    )
    if referenced:
        return False
    await session.delete(artist)
    await session.flush()
    await adjust_counter(session, Counter.ARTISTS, -1)
    await _changed(session, "artist", artist.id, ChangeOperation.DELETE)
    await _audit(session, "artist", artist.id, "delete", user_id, {"name": [artist.name, None]})
    return True


def _public(diff: dict[str, list[Any]]) -> dict[str, list[Any]]:
    """Audit diff without the derived sort columns."""
    return {key: value for key, value in diff.items() if not key.startswith("sort_")}


# --- managed and referenced originals -----------------------------------------------------


class FileOperation(enum.StrEnum):
    MOVE = "move"
    RENAME = "rename"
    DELETE = "delete"
    WRITE_TAGS = "write_tags"
    # Taking a referenced original into managed storage (job adopt_originals only).
    ADOPT = "adopt"


class FileOperationRefused(Exception):
    """A file operation that the storage mode of the original does not allow."""

    def __init__(self, audio_file: AudioFile, operation: FileOperation) -> None:
        super().__init__(f"{operation} refused for {audio_file.path}")
        self.audio_file = audio_file
        self.operation = operation


def check_file_operation(audio_file: AudioFile, operation: FileOperation) -> None:
    """Refuse what Anthology must not do to a file (spec: library, Managed and referenced
    originals; Superseded referenced originals). Every file operation calls this first.

    Managed originals allow everything but adoption. Referenced files are never moved, renamed
    or deleted and written only with the opt-in; only adoption takes them into managed storage
    (after checksum verification). A superseded managed file may only be deleted (ADR 0021);
    superseded referenced files are never touched at all.
    """
    if audio_file.original_status == OriginalStatus.SUPERSEDED:
        if audio_file.storage_mode == StorageMode.MANAGED and operation == FileOperation.DELETE:
            return
        raise FileOperationRefused(audio_file, operation)
    if operation == FileOperation.ADOPT:
        if audio_file.storage_mode == StorageMode.REFERENCED:
            return
        raise FileOperationRefused(audio_file, operation)
    if audio_file.storage_mode == StorageMode.MANAGED:
        return
    if operation == FileOperation.WRITE_TAGS and audio_file.tag_writes_allowed:
        return
    raise FileOperationRefused(audio_file, operation)


async def active_original(session: AsyncSession, recording_id: uuid.UUID) -> AudioFile | None:
    """The one file used for playback, transcoding and downloads of a recording."""
    return await session.scalar(
        select(AudioFile).where(
            AudioFile.recording_id == recording_id,
            AudioFile.original_status == OriginalStatus.ACTIVE,
        )
    )


class ReplacementNotSupported(Exception):
    pass


async def replace_original(
    session: AsyncSession,
    recording: Recording,
    audio: AudioFileInfo,
    *,
    allow_referenced: bool = False,
    user_id: uuid.UUID | None = None,
) -> tuple[AudioFile, AudioFile | None]:
    """Make ``audio`` the active original of ``recording``; returns (new, superseded).

    The old active original is kept unchanged, marked superseded and listed in the report of
    superseded files (spec: library, Quality-based replacement). A superseded managed file may
    be deleted afterwards with ``delete_superseded`` (ADR 0021); referenced ones never.
    Whether the new file is better is decided by the caller (effective quality); track
    contexts stay as they are. A referenced replacement is allowed only for imports in a
    referenced mode (``allow_referenced``); acquisitions store managed files.
    """
    if audio.storage_mode != StorageMode.MANAGED and not allow_referenced:
        raise ReplacementNotSupported("a downloaded or ripped original is always managed")
    current = await active_original(session, recording.id)

    replacement = _audio_file(
        recording.id, audio, current.home_track_id if current is not None else None
    )
    if current is not None:
        # The partial unique index allows one active file: supersede first, then insert.
        current.original_status = OriginalStatus.SUPERSEDED
        current.superseded_at = utcnow()
        await session.flush()
    session.add(replacement)
    await session.flush()
    await _referenced(session, replacement, +1)
    await _quality_counted(session, replacement, +1)
    await _changed(session, "audio_file", replacement.id, ChangeOperation.INSERT)
    if current is not None:
        current.superseded_by_id = replacement.id
        await session.flush()
        await _referenced(session, current, -1)
        await _quality_counted(session, current, -1)
        await _superseded_counted(session, current, +1)
        await _changed(session, "audio_file", current.id)
        await _changed(session, SUPERSEDED_FILE, current.id, ChangeOperation.INSERT)
    await _audit(
        session,
        "recording",
        recording.id,
        "replace_original",
        user_id,
        {"original": [current.path if current else None, replacement.path]},
    )
    # Every context of the recording shows the new file's format.
    track_ids = await session.scalars(select(Track.id).where(Track.recording_id == recording.id))
    await _rows_changed(session, "track", list(track_ids))
    return replacement, current


async def _superseded_counted(session: AsyncSession, audio_file: AudioFile, sign: int) -> None:
    await adjust_counter(session, Counter.SUPERSEDED_FILES, sign)
    await adjust_counter(session, Counter.SUPERSEDED_BYTES, sign * audio_file.size_bytes)
    if audio_file.storage_mode == StorageMode.MANAGED:
        await adjust_counter(session, Counter.SUPERSEDED_MANAGED_FILES, sign)
        await adjust_counter(
            session, Counter.SUPERSEDED_MANAGED_BYTES, sign * audio_file.size_bytes
        )


async def delete_superseded(
    session: AsyncSession, audio_file: AudioFile, *, user_id: uuid.UUID | None = None
) -> str:
    """Remove a superseded managed file's entry; returns its path, which the caller deletes
    after the commit. The caller has verified the replacing original (ADR 0021)."""
    check_file_operation(audio_file, FileOperation.DELETE)
    path = audio_file.path
    await _superseded_counted(session, audio_file, -1)
    await session.execute(
        update(AudioFile)
        .where(AudioFile.superseded_by_id == audio_file.id)
        .values(superseded_by_id=audio_file.superseded_by_id)
        .execution_options(synchronize_session=False)
    )
    await session.delete(audio_file)
    await session.flush()
    await _changed(session, "audio_file", audio_file.id, ChangeOperation.DELETE)
    await _changed(session, SUPERSEDED_FILE, audio_file.id, ChangeOperation.DELETE)
    await _audit(
        session,
        "recording",
        audio_file.recording_id,
        "delete_superseded",
        user_id,
        {"original": [path, None]},
    )
    return path


# --- merging recordings ----------------------------------------------------------------------


async def merge_recordings(
    session: AsyncSession,
    source: Recording,
    target: Recording,
    *,
    keep_source_original: bool,
    user_id: uuid.UUID | None = None,
) -> AudioFile | None:
    """Merge ``source`` into ``target`` after a user confirmed they are one recording (spec:
    review, Same recording); returns the original that became superseded, if any.

    Every track context of ``source`` moves to ``target`` and keeps what it showed (title and
    artist become context values where they differ). One original stays active: the source's
    with ``keep_source_original`` (the caller compared the effective quality), otherwise the
    target's; the other is superseded, never deleted here. Identifiers the target lacks are
    taken from the source; then the source is deleted.
    """
    source_active = await active_original(session, source.id)
    target_active = await active_original(session, target.id)
    superseded: AudioFile | None = None
    if source_active is not None and target_active is not None:
        loser, winner = (
            (target_active, source_active)
            if keep_source_original
            else (source_active, target_active)
        )
        loser.original_status = OriginalStatus.SUPERSEDED
        loser.superseded_at = utcnow()
        loser.superseded_by_id = winner.id
        await session.flush()
        await _referenced(session, loser, -1)
        await _quality_counted(session, loser, -1)
        await _superseded_counted(session, loser, +1)
        await _changed(session, SUPERSEDED_FILE, loser.id, ChangeOperation.INSERT)
        superseded = loser
    # All files of the source (the active one and earlier superseded ones) move along.
    moved_files = list(
        await session.scalars(select(AudioFile.id).where(AudioFile.recording_id == source.id))
    )
    await session.execute(
        update(AudioFile)
        .where(AudioFile.recording_id == source.id)
        .values(recording_id=target.id)
        .execution_options(synchronize_session=False)
    )
    await _rows_changed(session, "audio_file", moved_files)

    # Track contexts keep their title and artist.
    source_artist = await session.get_one(Artist, source.artist_id)
    target_artist = await session.get_one(Artist, target.artist_id)
    tracks = list(await session.scalars(select(Track).where(Track.recording_id == source.id)))
    for track in tracks:
        track.recording_id = target.id
        if track.context_title is None and source.title != target.title:
            track.context_title = source.title
        if track.context_artist is None and source.artist_display != target.artist_display:
            track.context_artist = source.artist_display
        track.sort_title = sort_key(track.context_title or target.title)
        track.sort_artist = (
            sort_key(track.context_artist) if track.context_artist else target_artist.sort_name
        )
    if source_artist.id != target_artist.id:
        source_artist.track_count -= len(tracks)
        target_artist.track_count += len(tracks)
        await _changed(session, "artist", source_artist.id)
        await _changed(session, "artist", target_artist.id)
    await session.flush()

    # Identifiers the target lacks; the MusicBrainz ID is unique, so the source lets go first.
    taken = {
        name: getattr(source, name)
        for name in ("isrc", "mb_recording_id", "acoust_id")
        if getattr(target, name) is None and getattr(source, name) is not None
    }
    source_status = source.identification_status
    source.mb_recording_id = None
    await session.flush()
    diff = _apply(target, taken)
    if "mb_recording_id" in taken:
        await adjust_counter(session, IDENTIFICATION_COUNTERS[target.identification_status], -1)
        await adjust_counter(session, IDENTIFICATION_COUNTERS[source_status], +1)
        target.identification_status = source_status
        target.identification_checked_at = source.identification_checked_at
        await register_external_ref(
            session,
            entity_type="recording",
            entity_id=target.id,
            mbid=taken["mb_recording_id"],
            checked_at=source.identification_checked_at or utcnow(),
        )
        await _changed(session, IDENTIFICATION, IDENTIFICATION_SUMMARY_ID)
    await unregister_external_ref(session, entity_type="recording", entity_id=source.id)
    await session.execute(
        update(Recording)
        .where(Recording.identification_duplicate_of_id == source.id, Recording.id != target.id)
        .values(identification_duplicate_of_id=target.id)
        .execution_options(synchronize_session=False)
    )

    await adjust_counter(session, IDENTIFICATION_COUNTERS[source_status], -1)
    await adjust_counter(session, Counter.RECORDINGS, -1)
    await session.delete(source)
    await session.flush()
    await _changed(session, "recording", source.id, ChangeOperation.DELETE)
    await _changed(session, "recording", target.id)
    await _changed(session, IDENTIFICATION, IDENTIFICATION_SUMMARY_ID)
    await _audit(
        session,
        "recording",
        target.id,
        "merge",
        user_id,
        {
            "merged_recording": [str(source.id), None],
            "superseded_original": [superseded.path if superseded else None, None],
            **_public(diff),
        },
    )
    await remove_if_orphaned(session, source_artist, user_id=user_id)
    target_tracks = await session.scalars(select(Track.id).where(Track.recording_id == target.id))
    await _rows_changed(session, "track", list(target_tracks))
    return superseded


async def separate_track(
    session: AsyncSession,
    track: Track,
    *,
    title: str,
    artist: Artist,
    duration_ms: int,
    audio: AudioFileInfo,
    isrc: str | None = None,
    recording_id: uuid.UUID | None = None,
    user_id: uuid.UUID | None = None,
) -> Recording:
    """Make ``track`` a recording of its own with ``audio`` as original, after a user decided
    that its file is not the recording it was matched to (spec: review, Import matches with a
    different title)."""
    previous = await session.get_one(Recording, track.recording_id)
    previous_artist = await session.get_one(Artist, previous.artist_id)
    recording = Recording(
        id=recording_id or uuid.uuid4(),
        title=title,
        artist_id=artist.id,
        artist_display=artist.name,
        duration_ms=duration_ms,
        isrc=isrc,
    )
    session.add(recording)
    await session.flush()
    await adjust_counter(session, Counter.RECORDINGS, +1)
    await adjust_counter(session, Counter.IDENTIFICATION_UNCHECKED, +1)
    await _changed(session, "recording", recording.id, ChangeOperation.INSERT)
    track.recording_id = recording.id
    track.sort_title = sort_key(track.context_title or recording.title)
    track.sort_artist = sort_key(track.context_artist) if track.context_artist else artist.sort_name
    if previous_artist.id != artist.id:
        previous_artist.track_count -= 1
        artist.track_count += 1
        await _changed(session, "artist", previous_artist.id)
        await _changed(session, "artist", artist.id)
    audio_file = _audio_file(recording.id, audio, track.id)
    session.add(audio_file)
    await session.flush()
    await _referenced(session, audio_file, +1)
    await _quality_counted(session, audio_file, +1)
    await _changed(session, "audio_file", audio_file.id, ChangeOperation.INSERT)
    await _changed(session, "track", track.id)
    await _audit(
        session,
        "track",
        track.id,
        "separate",
        user_id,
        {"recording_id": [str(previous.id), str(recording.id)]},
    )
    return recording


# --- identification -------------------------------------------------------------------------

# Change entries of the identification summary (stream library.identification).
IDENTIFICATION = "identification"
IDENTIFICATION_SUMMARY_ID = uuid.UUID("2b0d3f4e-8c71-4f0e-9d55-6a7c1e3b9f20")


async def record_identification(
    session: AsyncSession,
    recording: Recording,
    status: IdentificationStatus,
    *,
    checked_at: datetime,
    mb_recording_id: uuid.UUID | None = None,
    acoust_id: uuid.UUID | None = None,
    note: str | None = None,
    duplicate_of_id: uuid.UUID | None = None,
    user_id: uuid.UUID | None = None,
) -> None:
    """Store the outcome of an identification check (spec: library, Identification outcome).

    Only identifiers are set (spec: Identifiers only); identified recordings are registered
    for the periodic refresh of metadata-lookup.
    """
    previous = recording.identification_status
    if previous != status:
        await adjust_counter(session, IDENTIFICATION_COUNTERS[previous], -1)
        await adjust_counter(session, IDENTIFICATION_COUNTERS[status], +1)
    recording.identification_status = status
    recording.identification_checked_at = checked_at
    recording.identification_note = note
    recording.identification_duplicate_of_id = duplicate_of_id
    diff: dict[str, list[Any]] = {}
    if mb_recording_id is not None:
        diff |= _apply(recording, {"mb_recording_id": mb_recording_id})
        await register_external_ref(
            session,
            entity_type="recording",
            entity_id=recording.id,
            mbid=mb_recording_id,
            checked_at=checked_at,
        )
    if acoust_id is not None:
        diff |= _apply(recording, {"acoust_id": acoust_id})
    await session.flush()
    await _changed(session, "recording", recording.id)
    await _changed(session, IDENTIFICATION, IDENTIFICATION_SUMMARY_ID)
    if diff:
        await _audit(session, "recording", recording.id, "identify", user_id, _public(diff))


async def clear_identification(
    session: AsyncSession, recording: Recording, *, user_id: uuid.UUID | None = None
) -> None:
    """Remove a recording's MusicBrainz ID (an editor cleared it); it is checked again."""
    previous = recording.identification_status
    if previous != IdentificationStatus.UNCHECKED:
        await adjust_counter(session, IDENTIFICATION_COUNTERS[previous], -1)
        await adjust_counter(session, IDENTIFICATION_COUNTERS[IdentificationStatus.UNCHECKED], +1)
    diff = _apply(recording, {"mb_recording_id": None})
    recording.identification_status = IdentificationStatus.UNCHECKED
    recording.identification_checked_at = None
    recording.identification_note = None
    recording.identification_duplicate_of_id = None
    await session.flush()
    await unregister_external_ref(session, entity_type="recording", entity_id=recording.id)
    await _changed(session, "recording", recording.id)
    await _changed(session, IDENTIFICATION, IDENTIFICATION_SUMMARY_ID)
    if diff:
        await _audit(session, "recording", recording.id, "identify", user_id, _public(diff))


async def store_fingerprint(
    session: AsyncSession, audio_file: AudioFile, fingerprint: str, duration_s: int
) -> None:
    audio_file.fingerprint = fingerprint
    audio_file.fingerprint_duration_s = duration_s
    await session.flush()


async def adopt_original(
    session: AsyncSession,
    audio_file: AudioFile,
    *,
    path: str,
    content_hash: str,
    user_id: uuid.UUID | None = None,
) -> None:
    """Make a referenced original managed after its bytes were verified at ``path``."""
    check_file_operation(audio_file, FileOperation.ADOPT)
    old_path = audio_file.path
    await _referenced(session, audio_file, -1)
    audio_file.path = path
    audio_file.content_hash = content_hash
    audio_file.storage_mode = StorageMode.MANAGED
    audio_file.tag_writes_allowed = False
    await session.flush()
    await _changed(session, "audio_file", audio_file.id)
    await _audit(
        session,
        "audio_file",
        audio_file.id,
        "adopt",
        user_id,
        {"path": [old_path, path], "storage_mode": ["referenced", "managed"]},
    )


# --- lookups for imports and acquisition ------------------------------------------------------

DURATION_TOLERANCE_MS = 2_000


async def file_rewritten(
    session: AsyncSession, audio_file: AudioFile, *, size_bytes: int, content_hash: str | None
) -> None:
    """Record a file whose tags were written: new size and content hash, the audio data (and
    so the audio hash) is unchanged."""
    delta = size_bytes - audio_file.size_bytes
    audio_file.size_bytes = size_bytes
    audio_file.content_hash = content_hash
    await session.flush()
    if delta and audio_file.original_status == OriginalStatus.ACTIVE:
        if audio_file.storage_mode == StorageMode.REFERENCED:
            await adjust_counter(session, Counter.REFERENCED_BYTES, delta)
            await _changed(session, STORAGE, STORAGE_SUMMARY_ID)
    await _changed(session, "audio_file", audio_file.id)


async def original_by_audio_hash(session: AsyncSession, audio_hash: str) -> AudioFile | None:
    """An active original with the same audio data (tags excluded)."""
    return await session.scalar(
        select(AudioFile)
        .where(
            AudioFile.audio_hash == audio_hash,
            AudioFile.original_status == OriginalStatus.ACTIVE,
        )
        .limit(1)
    )


async def recording_by_identifiers(
    session: AsyncSession, *, mb_recording_id: uuid.UUID | None, isrc: str | None, duration_ms: int
) -> Recording | None:
    """The recording with this MusicBrainz ID, else one with this ISRC within ±2 seconds."""
    if mb_recording_id is not None:
        found = await session.scalar(
            select(Recording).where(Recording.mb_recording_id == mb_recording_id)
        )
        if found is not None:
            return found
    if isrc:
        return await session.scalar(
            select(Recording)
            .where(
                Recording.isrc == isrc,
                func.abs(Recording.duration_ms - duration_ms) <= DURATION_TOLERANCE_MS,
            )
            .limit(1)
        )
    return None


async def recordings_by_name(
    session: AsyncSession, artist_key: str, title_key: str, duration_ms: int, *, limit: int = 5
) -> list[uuid.UUID]:
    """Recordings shown with this artist and title (sort keys) within ±2 seconds."""
    query = (
        select(Track.recording_id)
        .join(Recording, Recording.id == Track.recording_id)
        .where(
            Track.sort_artist == artist_key,
            Track.sort_title == title_key,
            func.abs(Recording.duration_ms - duration_ms) <= DURATION_TOLERANCE_MS,
        )
        .distinct()
        .limit(limit)
    )
    return list(await session.scalars(query))


async def track_of(
    session: AsyncSession, release_id: uuid.UUID, recording_id: uuid.UUID
) -> Track | None:
    return await session.scalar(
        select(Track).where(Track.release_id == release_id, Track.recording_id == recording_id)
    )


async def has_track(session: AsyncSession, release_id: uuid.UUID, recording_id: uuid.UUID) -> bool:
    found = await session.scalar(
        select(Track.id)
        .where(Track.release_id == release_id, Track.recording_id == recording_id)
        .limit(1)
    )
    return found is not None


async def get_release(session: AsyncSession, release_id: uuid.UUID) -> Release | None:
    return await session.get(Release, release_id)


async def get_recording(session: AsyncSession, recording_id: uuid.UUID) -> Recording | None:
    return await session.get(Recording, recording_id)


async def get_audio_file(session: AsyncSession, audio_file_id: uuid.UUID) -> AudioFile | None:
    return await session.get(AudioFile, audio_file_id)


# --- quality analysis --------------------------------------------------------------------------


async def apply_quality(
    session: AsyncSession,
    audio_hash: str,
    status: QualityStatus,
    effective_quality: QualityTier | None,
) -> int:
    """Store the analysis result on every file with this audio data (spec: quality-analysis,
    Stored result); returns the number of files changed. ``effective_quality`` is None unless
    the result has high confidence. Track rows of the files' recordings receive deltas."""
    files = list(
        await session.scalars(
            select(AudioFile).where(AudioFile.audio_hash == audio_hash).with_for_update()
        )
    )
    changed: list[AudioFile] = []
    for audio_file in files:
        if (audio_file.quality_status, audio_file.effective_quality) == (status, effective_quality):
            continue
        if audio_file.original_status == OriginalStatus.ACTIVE:
            await _quality_counted(session, audio_file, -1)
        audio_file.quality_status = status
        audio_file.effective_quality = effective_quality
        if audio_file.original_status == OriginalStatus.ACTIVE:
            await _quality_counted(session, audio_file, +1)
        changed.append(audio_file)
    if not changed:
        return 0
    await session.flush()
    for audio_file in changed:
        await _changed(session, "audio_file", audio_file.id)
    recordings = {audio_file.recording_id for audio_file in changed}
    tracks = await session.scalars(select(Track.id).where(Track.recording_id.in_(recordings)))
    await _rows_changed(session, "track", list(tracks))
    return len(changed)


async def release_year(session: AsyncSession, audio_file: AudioFile) -> int | None:
    """Year of the release of the file's home track context (old recordings are judged more
    tolerantly)."""
    if audio_file.home_track_id is None:
        return None
    released = await session.scalar(
        select(Release.release_date)
        .join(Track, Track.release_id == Release.id)
        .where(Track.id == audio_file.home_track_id)
    )
    return released.year if released else None


async def audio_hashes(
    session: AsyncSession,
    *,
    without,
    limit: int,
    after: str | None = None,
    first: str | None = None,
    last: str | None = None,
) -> list[str]:
    """Audio hashes of active originals in order (after ``after``, or from ``first`` to
    ``last``), except those selected by ``without`` (a select of hashes, e.g. the analysed)."""
    query = (
        select(AudioFile.audio_hash)
        .where(
            AudioFile.original_status == OriginalStatus.ACTIVE,
            AudioFile.audio_hash.not_in(without),
        )
        .distinct()
        .order_by(AudioFile.audio_hash)
        .limit(limit)
    )
    if after is not None:
        query = query.where(AudioFile.audio_hash > after)
    if first is not None:
        query = query.where(AudioFile.audio_hash >= first)
    if last is not None:
        query = query.where(AudioFile.audio_hash <= last)
    return list(await session.scalars(query))
