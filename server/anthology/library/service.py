"""Library writes: the only place that changes library data (spec: library).

Every write keeps the denormalized sort keys, the maintained counters and the change log
consistent, so callers (import, tagging, metadata lookup) cannot forget them. A change that
alters what other list rows show or sort by writes a change entry for each of those rows
(spec: Deltas for derived values).
"""

import unicodedata
import uuid
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
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
from anthology.library.models import (
    Artist,
    AudioFile,
    AudioFormat,
    Counter,
    LibraryCounter,
    QualityTier,
    Recording,
    Release,
    ReleaseGroup,
    ReleaseGroupType,
    Track,
)

# Change entry written when a release leaves the list of its former album artist.
RELEASE_MOVED = "release.moved"
# Change entry written when a track moves to another release (written by tag editing).
TRACK_MOVED = "track.moved"


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


async def counters(session: AsyncSession) -> dict[str, int]:
    """The maintained library counters (missing rows count as 0)."""
    values = {counter.value: 0 for counter in Counter}
    for row in await session.scalars(select(LibraryCounter)):
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
    user_id: uuid.UUID | None = None,
) -> Track:
    """Create a recording with its original and its home track context on ``release``."""
    recording = Recording(
        id=uuid.uuid4(),
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
    audio_file = AudioFile(
        id=uuid.uuid4(),
        recording_id=recording.id,
        path=audio.path,
        format=audio.format,
        codec=audio.codec,
        bitrate_kbps=audio.bitrate_kbps,
        sample_rate_hz=audio.sample_rate_hz,
        bit_depth=audio.bit_depth,
        channels=audio.channels,
        size_bytes=audio.size_bytes,
        audio_hash=audio.audio_hash,
        declared_quality=audio.declared_quality,
        home_track_id=track.id,
    )
    session.add(audio_file)
    await session.flush()
    await _changed(session, "audio_file", audio_file.id, ChangeOperation.INSERT)
    return track


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
