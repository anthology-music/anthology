"""The zone player (spec: playback, Zone play queue, Remote control, Delivery to outputs;
design of change raumfeld-output).

The zone queue in the database is the truth: clients change it, the player carries it out.
One process runs a zone's player (lease in ``registry.py``). The player hands the current
entry to the zone with a URL valid for the track plus one hour, follows the zone's transport
state, writes the position at most every few seconds, starts the next entry when a track ends,
and pauses the queue when the zone plays something that is not Anthology's.

A difference between the queue and what the player last applied or wrote is a command (play,
pause, another entry, a seek); the player's own writes are remembered, so they are not.
"""

import logging
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from urllib.parse import urlencode

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from anthology.core.media_urls import IMAGE_PREFIX
from anthology.library.models import AudioFile, AudioFormat, OriginalStatus, Recording, Release
from anthology.library.models import Track as LibraryTrack
from anthology.playback import service
from anthology.playback.media import MEDIA_TYPES, TRANSCODE_MEDIA_TYPE
from anthology.playback.models import OutputSystem, OutputZone, PlayQueue, PlayQueueEntry
from anthology.playback.outputs.base import (
    OutputAdapter,
    OutputError,
    TrackMetadata,
    Transport,
    ZoneRef,
)
from anthology.tagging.writer import context_tags
from anthology.transcoding import delivery
from anthology.transcoding import service as transcoding
from anthology.users.models import BitrateSetting

logger = logging.getLogger(__name__)

# The position is written at most this often while playing (and on every state change).
POSITION_WRITE_SECONDS = 5
# A URL handed to a zone lives for the track plus this (spec: Delivery to outputs).
URL_MARGIN_SECONDS = 3_600
# A zone reporting "stopped" this long after a handover finished the track (before, it may
# still be loading it).
STOPPED_GRACE_SECONDS = 10
# Undeliverable entries skipped in a row before the player gives up and pauses.
MAX_SKIPS = 20


@dataclass(frozen=True)
class Applied:
    """The queue state the player last carried out or wrote itself."""

    entry_id: int | None
    position_ms: int
    playing: bool


@dataclass(frozen=True)
class Handed:
    """What the player handed to the zone."""

    entry_id: int
    uri: str
    expires_at: datetime
    at: datetime
    duration_ms: int = 0


@dataclass(frozen=True)
class Delivery:
    path: str
    mime_type: str
    duration_ms: int
    metadata: TrackMetadata
    next_audio: tuple[uuid.UUID, delivery.Variant | None] | None = None
    # The image ID of the cover in the track's context.
    cover: uuid.UUID | None = None


class Undeliverable(Exception):
    """The entry has no original or its transcode failed: it is skipped."""


@dataclass
class Media:
    """What the player needs from the server: paths, signing, transcodes, the URL base."""

    sign: Callable[[str, uuid.UUID, uuid.UUID, int], dict[str, str]]
    path_for: Callable[..., str]
    transcoder: transcoding.Transcoder
    base_url: Callable[[str], Awaitable[str]]
    max_ttl_seconds: int


class ZonePlayer:
    def __init__(
        self,
        zone_id: uuid.UUID,
        adapter: OutputAdapter,
        sessionmaker: async_sessionmaker[AsyncSession],
        media: Media,
        clock: Callable[[], datetime],
    ) -> None:
        self.zone_id = zone_id
        self._adapter = adapter
        self._sessionmaker = sessionmaker
        self._media = media
        self._clock = clock
        self.applied: Applied | None = None
        self.handed: Handed | None = None
        # The zone reported playing what was handed over (a later stop is its end).
        self._seen_playing = False
        self._written_at: datetime | None = None

    @property
    def idle(self) -> bool:
        """Nothing to follow: the queue is paused and the zone was told so."""
        return self.applied is not None and not self.applied.playing

    async def tick(self) -> None:
        """Carry out a changed queue, then follow the zone while it plays."""
        async with self._sessionmaker() as session:
            zone = await session.get(OutputZone, self.zone_id)
            queue = await session.scalar(
                select(PlayQueue)
                .where(PlayQueue.output_zone_id == self.zone_id)
                .execution_options(populate_existing=True)
            )
            if zone is None or queue is None:
                return
            ref = await _ref(session, zone)
            wanted = Applied(queue.current_entry_id, queue.position_ms, queue.playing)
            formats = frozenset(AudioFormat(value) for value in zone.formats or ())
        try:
            if wanted != self.applied:
                await self._apply(ref, wanted, formats)
            elif wanted.playing:
                await self._follow(ref, formats)
        except OutputError as error:
            logger.warning("zone %s: %s", self.zone_id, error)

    async def stop(self, ref: ZoneRef) -> None:
        self.handed = None
        await self._adapter.stop_zone(ref)

    # --- commands -------------------------------------------------------------------------

    async def _apply(self, ref: ZoneRef, wanted: Applied, formats) -> None:
        previous, self.applied = self.applied, wanted
        if not wanted.playing:
            if self.handed is not None and (previous is None or previous.playing):
                state = await self._adapter.state(ref)
                if state.uri == self.handed.uri and state.transport != Transport.STOPPED:
                    await self._adapter.pause(ref)
            return
        if wanted.entry_id is None:
            return
        handed = self.handed
        if handed is None or handed.entry_id != wanted.entry_id or self._expired(handed):
            await self._hand_over(ref, wanted.entry_id, wanted.position_ms, formats)
            return
        state = await self._adapter.state(ref)
        if state.uri != handed.uri:
            await self._hand_over(ref, wanted.entry_id, wanted.position_ms, formats)
            return
        if previous is None or previous.position_ms != wanted.position_ms:
            await self._adapter.seek(ref, wanted.position_ms)
        if state.transport != Transport.PLAYING:
            await self._adapter.resume(ref)

    def _expired(self, handed: Handed) -> bool:
        # A minute of slack: the zone must still be able to fetch the stream.
        return handed.expires_at - timedelta(minutes=1) <= self._clock()

    async def _hand_over(self, ref: ZoneRef, entry_id: int, start_ms: int, formats) -> None:
        """Hand the entry to the zone; skip entries that cannot be delivered."""
        for _attempt in range(MAX_SKIPS):
            try:
                user_id, found = await self._delivery(entry_id, formats)
            except Undeliverable:
                logger.info(
                    "zone %s: entry %s cannot be delivered, skipped", self.zone_id, entry_id
                )
                entry_id = await self._write(skip=True)
                start_ms = 0
                if entry_id is None:
                    return
                continue
            if user_id is None:
                await self._write(playing=False)
                return
            ttl = min(found.duration_ms // 1000 + URL_MARGIN_SECONDS, self._media.max_ttl_seconds)
            params = self._media.sign(found.path, user_id, self.zone_id, ttl)
            base = await self._media.base_url(ref.address)
            uri = f"{base}{found.path}?{urlencode(params)}"
            metadata = found.metadata
            if found.cover is not None:
                # One grant for the image prefix, bound to the zone like the track URL.
                grant = self._media.sign(IMAGE_PREFIX, user_id, self.zone_id, ttl)
                art = f"{base}{IMAGE_PREFIX}/{found.cover}/600?format=jpeg&{urlencode(grant)}"
                metadata = replace(metadata, art_uri=art)
            await self._adapter.play(ref, uri, metadata, start_ms)
            now = self._clock()
            self.handed = Handed(
                entry_id, uri, now + timedelta(seconds=ttl), now, found.duration_ms
            )
            self._seen_playing = False
            if found.next_audio is not None:
                await self._prepare(*found.next_audio)
            return
        await self._write(playing=False)

    async def _prepare(self, audio_file_id: uuid.UUID, variant: delivery.Variant | None) -> None:
        """Start the next entry's transcode, so that it is ready (spec: Prepared next track)."""
        if variant is None:
            return
        try:
            await self._media.transcoder.ensure(audio_file_id, variant)
        except transcoding.TranscodeFailed:
            pass

    # --- following the zone ---------------------------------------------------------------

    async def _follow(self, ref: ZoneRef, formats) -> None:
        handed = self.handed
        if handed is None:
            self.applied = None  # hand over on the next tick
            return
        state = await self._adapter.state(ref)
        if state.uri is not None and state.uri != handed.uri:
            # The Raumfeld app (or another controller) plays something else.
            logger.info("zone %s plays a foreign source; the queue pauses", self.zone_id)
            self.handed = None
            await self._write(playing=False)
            return
        if state.transport == Transport.PLAYING:
            self._seen_playing = True
            now = self._clock()
            if self._written_at is None or now - self._written_at >= timedelta(
                seconds=POSITION_WRITE_SECONDS
            ):
                await self._write(position_ms=state.position_ms)
            return
        # A stop right after the handover may be the renderer loading; later it is the end.
        settled = self._seen_playing or self._clock() - handed.at > timedelta(
            seconds=STOPPED_GRACE_SECONDS
        )
        if state.transport == Transport.STOPPED and settled:
            # The track played to its end (it may complete a play).
            entry_id = await self._write(skip=True, position_ms=handed.duration_ms)
            if entry_id is not None and self.applied is not None and self.applied.playing:
                await self._hand_over(ref, entry_id, 0, formats)

    async def _write(
        self, *, position_ms: int | None = None, playing: bool | None = None, skip: bool = False
    ) -> int | None:
        """Write the player's own change and remember it; returns the current entry."""
        async with self._sessionmaker() as session, session.begin():
            queue = await service.zone_queue(session, self.zone_id)
            if skip:
                await service.skip(session, queue, 1, position_ms=position_ms)
            else:
                await service.set_state(
                    session,
                    queue,
                    current_entry_id=queue.current_entry_id,
                    position_ms=queue.position_ms if position_ms is None else position_ms,
                    playing=queue.playing if playing is None else playing,
                )
            self.applied = Applied(queue.current_entry_id, queue.position_ms, queue.playing)
        self._written_at = self._clock()
        return self.applied.entry_id

    # --- what to deliver ------------------------------------------------------------------

    async def _delivery(self, entry_id: int, formats) -> tuple[uuid.UUID | None, Delivery]:
        async with self._sessionmaker() as session:
            queue = await session.scalar(
                select(PlayQueue).where(PlayQueue.output_zone_id == self.zone_id)
            )
            entry = await session.get(PlayQueueEntry, entry_id)
            if queue is None or entry is None:
                raise Undeliverable(entry_id)
            found = await _original(session, entry.track_id)
            if found is None:
                raise Undeliverable(entry_id)
            track, recording, release, audio = found
            variant = _variant(audio, formats)
            following = await service.neighbour(session, queue, 1)
            next_audio = None
            if following is not None:
                next_entry = await session.get(PlayQueueEntry, following)
                next_found = await _original(session, next_entry.track_id) if next_entry else None
                if next_found is not None:
                    next_audio = (next_found[3].id, _variant(next_found[3], formats))
            tags = context_tags(recording, track, release)
            user_id = queue.controlled_by
        if variant is None:
            path = self._media.path_for("media_original", audio_file_id=str(audio.id))
            mime = MEDIA_TYPES.get(audio.format, "application/octet-stream")
        else:
            try:
                await self._media.transcoder.ensure(audio.id, variant)
            except transcoding.TranscodeFailed as error:
                raise Undeliverable(entry_id) from error
            path = self._media.path_for(
                "media_transcode", track_id=str(track.id), variant=variant.name
            )
            mime = TRANSCODE_MEDIA_TYPE
        metadata = TrackMetadata(
            title=tags.title or "",
            artist=tags.artist or "",
            album=tags.album or "",
            album_artist=tags.album_artist or "",
            track_number=tags.track_number,
            duration_ms=recording.duration_ms,
            mime_type=mime,
        )
        cover = recording.front_image_id or release.front_image_id
        return user_id, Delivery(path, mime, recording.duration_ms, metadata, next_audio, cover)


def _variant(audio: AudioFile, formats) -> delivery.Variant | None:
    """The original if the zone reports its format, else a compatibility transcode."""
    return delivery.decide(
        delivery.Original(
            audio.format, audio.bitrate_kbps, audio.declared_quality, audio.effective_quality
        ),
        BitrateSetting.ORIGINAL,
        formats,
    )


async def _original(session: AsyncSession, track_id: uuid.UUID):
    row = (
        await session.execute(
            select(LibraryTrack, Recording, Release, AudioFile)
            .join(Recording, Recording.id == LibraryTrack.recording_id)
            .join(Release, Release.id == LibraryTrack.release_id)
            .join(
                AudioFile,
                (AudioFile.recording_id == LibraryTrack.recording_id)
                & (AudioFile.original_status == OriginalStatus.ACTIVE),
            )
            .where(LibraryTrack.id == track_id)
        )
    ).first()
    return tuple(row) if row is not None else None


async def _ref(session: AsyncSession, zone: OutputZone) -> ZoneRef:
    system = await session.get_one(OutputSystem, zone.system_id)
    return ZoneRef(address=system.address, external_id=zone.external_id, control=zone.control)
