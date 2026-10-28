"""REST routes of playback (spec: playback): the queue of the requesting device (or of the zone
it controls, spec: Remote control), media URLs and the signed media endpoint for originals
(spec: sync-protocol, Signed media URLs)."""

import asyncio
import os
import uuid
from datetime import timedelta
from typing import Annotated
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from anthology.api.deps import CurrentSession, MediaAccess
from anthology.db import get_session
from anthology.db.types import utcnow
from anthology.library import service as library
from anthology.library.models import AudioFile, AudioFormat, OriginalStatus, Track
from anthology.playback import service
from anthology.playback.media import MEDIA_TYPES
from anthology.playback.models import PlayQueueEntry
from anthology.playback.schemas import (
    MediaUrl,
    MoveIn,
    SkipIn,
    SkipOut,
    StartIn,
    StartOut,
    StateIn,
    UrlsIn,
)
from anthology.transcoding import delivery
from anthology.transcoding import service as transcoding
from anthology.transcoding.models import CacheStatus
from anthology.users import service as users

router = APIRouter(tags=["playback"])

Session = Annotated[AsyncSession, Depends(get_session)]

CACHE_HEADERS = {"Cache-Control": "private, max-age=3600"}
FORMATS = frozenset(audio_format.value for audio_format in AudioFormat)
# Client URLs live at most an hour (spec: sync-protocol, Short-lived client media URLs).
URL_TTL_SECONDS = 3_600


def _invalid(detail: str) -> HTTPException:
    return HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail=detail)


def _uuid(value: str) -> uuid.UUID:
    try:
        return uuid.UUID(value)
    except ValueError as error:
        raise _invalid("invalid_id") from error


def _entry_id(value: str) -> int:
    if not value.isdigit():
        raise _invalid("invalid_id")
    return int(value)


async def _queue(session: AsyncSession, current: CurrentSession):
    """The queue this device's commands act on (the zone's while it controls one)."""
    return await service.controlled_queue(
        session, current.user_id, current.user_device_id, current.device_id
    )


@router.post("/playback/queue")
async def start(session: Session, current: CurrentSession, body: StartIn) -> StartOut:
    """Play tracks (spec: playback, Starting playback)."""
    ids = [_uuid(value) for value in body.ids] if body.ids is not None else None
    rule = body.rule.model_dump() if body.rule is not None else None
    start_track = _uuid(body.start) if body.start else None
    if rule is not None:
        for name in ("release_id", "artist_id"):
            if rule.get(name):
                _uuid(rule[name])
    queue = await _queue(session, current)
    started = await service.start(
        session, queue, mode=body.mode, ids=ids, rule=rule, start_track=start_track
    )
    await session.commit()
    return StartOut(entries=started.entries, shortened=started.shortened)


@router.put("/playback/state", status_code=status.HTTP_204_NO_CONTENT)
async def set_state(session: Session, current: CurrentSession, body: StateIn) -> None:
    """The client's report of the current entry, its position and whether it plays."""
    entry_id = _entry_id(body.current_entry_id) if body.current_entry_id is not None else None
    queue = await _queue(session, current)
    try:
        await service.set_state(
            session,
            queue,
            current_entry_id=entry_id,
            position_ms=body.position_ms,
            playing=body.playing,
        )
    except service.QueueError as error:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="unknown_entry") from error
    await session.commit()


@router.post("/playback/skip")
async def skip(session: Session, current: CurrentSession, body: SkipIn) -> SkipOut:
    """Next (``by`` = 1) or previous (-1) entry of the queue, from its start."""
    queue = await _queue(session, current)
    queue.playing = body.playing
    entry_id = await service.skip(session, queue, body.by)
    await session.commit()
    return SkipOut(current_entry_id=str(entry_id) if entry_id is not None else None)


@router.delete("/playback/queue/entries/{entry_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove(session: Session, current: CurrentSession, entry_id: str) -> None:
    queue = await _queue(session, current)
    try:
        await service.remove(session, queue, _entry_id(entry_id))
    except service.QueueError as error:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="unknown_entry") from error
    await session.commit()


@router.post("/playback/queue/entries/{entry_id}/move", status_code=status.HTTP_204_NO_CONTENT)
async def move(session: Session, current: CurrentSession, entry_id: str, body: MoveIn) -> None:
    after = _entry_id(body.after) if body.after is not None else None
    queue = await _queue(session, current)
    try:
        await service.move(session, queue, _entry_id(entry_id), after)
    except service.QueueError as error:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="unknown_entry") from error
    await session.commit()


@router.delete("/playback/queue", status_code=status.HTTP_204_NO_CONTENT)
async def clear(session: Session, current: CurrentSession) -> None:
    await service.clear(session, await _queue(session, current))
    await session.commit()


@router.post("/playback/urls")
async def urls(
    request: Request, session: Session, current: CurrentSession, body: UrlsIn
) -> list[MediaUrl]:
    """Signed URLs (valid for an hour) of what this device receives for queue entries: the
    original or a transcode (spec: transcoding). Transcodes are started here, so the next
    entry is ready before it plays (spec: Prepared next track)."""
    ids = [_entry_id(value) for value in body.entry_ids]
    missing = {i: MediaUrl(entry_id=str(i), url=None, expires_at=None, format=None) for i in ids}
    queue = await service.find_queue(session, current.user_id, current.device_id)
    if queue is None:
        return list(missing.values())
    rows = await session.execute(
        select(PlayQueueEntry.id, Track.id, AudioFile)
        .join(Track, Track.id == PlayQueueEntry.track_id)
        .join(
            AudioFile,
            (AudioFile.recording_id == Track.recording_id)
            & (AudioFile.original_status == OriginalStatus.ACTIVE),
        )
        .where(PlayQueueEntry.queue_id == queue.id, PlayQueueEntry.id.in_(ids))
    )
    originals = {entry_id: (track_id, audio) for entry_id, track_id, audio in rows}
    setting, reported = await users.delivery_profile(
        session, current.user_device_id, current.device_id
    )
    formats = frozenset(AudioFormat(value) for value in reported or () if value in FORMATS)
    signer = request.app.state.media_signer
    transcoder = request.app.state.transcoder
    expires_at = utcnow() + timedelta(seconds=URL_TTL_SECONDS)
    result = []
    for entry_id in ids:
        if entry_id not in originals:
            result.append(missing[entry_id])
            continue
        track_id, audio = originals[entry_id]
        variant = delivery.decide(
            delivery.Original(
                audio.format, audio.bitrate_kbps, audio.declared_quality, audio.effective_quality
            ),
            setting,
            formats,
        )
        if variant is None:
            path = request.app.url_path_for("media_original", audio_file_id=str(audio.id))
        else:
            try:
                await transcoder.ensure(audio.id, variant)
            except transcoding.TranscodeFailed:
                result.append(missing[entry_id])
                continue
            path = request.app.url_path_for(
                "media_transcode", track_id=str(track_id), variant=variant.name
            )
        params = signer.sign(path, current.user_id, current.user_device_id, URL_TTL_SECONDS)
        result.append(
            MediaUrl(
                entry_id=str(entry_id),
                url=f"{path}?{urlencode(params)}",
                expires_at=expires_at,
                format=audio.format if variant is None else variant.format,
                transcoded=variant is not None,
            )
        )
    return result


@router.get("/media/transcodes/{track_id}/{variant}", name="media_transcode", response_model=None)
async def media_transcode(
    request: Request, session: Session, _grant: MediaAccess, track_id: str, variant: str
) -> FileResponse | StreamingResponse:
    """A transcode of a track's original: complete with range requests, or streamed while
    FFmpeg writes it (spec: transcoding, Streaming while transcoding)."""
    wanted = delivery.Variant.parse(variant)
    track = await session.get(Track, _uuid(track_id))
    original = await library.active_original(session, track.recording_id) if track else None
    if wanted is None or original is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="unknown_transcode")
    transcoder = request.app.state.transcoder
    try:
        entry = await transcoder.ensure(original.id, wanted)
        if entry.status == CacheStatus.READY:
            # The copy with this track's context tags, if the tagger wrote it in time.
            copy = await transcoder.tagged(entry, track.id)
            if copy is not None and await asyncio.to_thread(transcoder.file(copy).is_file):
                return FileResponse(
                    transcoder.file(copy), media_type="audio/mp4", headers=CACHE_HEADERS
                )
            path = transcoder.file(entry)
            if await asyncio.to_thread(path.is_file):
                return FileResponse(path, media_type="audio/mp4", headers=CACHE_HEADERS)
            await transcoder.forget(entry)
            entry = await transcoder.ensure(original.id, wanted)
    except transcoding.TranscodeFailed as error:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="transcode_failed") from error
    return StreamingResponse(
        transcoder.follow(entry), media_type="audio/mp4", headers={"Cache-Control": "no-store"}
    )


@router.get("/media/originals/{audio_file_id}", name="media_original")
async def media_original(session: Session, _grant: MediaAccess, audio_file_id: str) -> FileResponse:
    """The bytes of an active original, with range requests (spec: playback, Playback on this
    device). Every signed-in user may play every library item; the grant is checked by
    ``MediaAccess`` (signature, expiry, revocation)."""
    audio_file = await library.get_audio_file(session, _uuid(audio_file_id))
    if audio_file is None or audio_file.original_status != OriginalStatus.ACTIVE:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="unknown_original")
    if not await asyncio.to_thread(os.path.isfile, audio_file.path):
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="missing_file")
    return FileResponse(
        audio_file.path,
        media_type=MEDIA_TYPES.get(audio_file.format, "application/octet-stream"),
        headers={"Cache-Control": "private, max-age=3600"},
    )
