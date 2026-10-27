"""REST routes of playback (spec: playback): the queue of the requesting device, media URLs
and the signed media endpoint for originals (spec: sync-protocol, Signed media URLs)."""

import asyncio
import os
import uuid
from datetime import timedelta
from typing import Annotated
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from anthology.api.deps import CurrentSession, MediaAccess
from anthology.db import get_session
from anthology.db.types import utcnow
from anthology.library import service as library
from anthology.library.models import AudioFile, AudioFormat, OriginalStatus, Recording, Track
from anthology.playback import service
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

router = APIRouter(tags=["playback"])

Session = Annotated[AsyncSession, Depends(get_session)]

# Client URLs live at most an hour (spec: sync-protocol, Short-lived client media URLs).
URL_TTL_SECONDS = 3_600
MEDIA_TYPES = {
    AudioFormat.FLAC: "audio/flac",
    AudioFormat.WAV: "audio/wav",
    AudioFormat.AIFF: "audio/aiff",
    AudioFormat.ALAC: "audio/mp4",
    AudioFormat.MP3: "audio/mpeg",
    AudioFormat.AAC: "audio/mp4",
    AudioFormat.OPUS: "audio/ogg",
    AudioFormat.VORBIS: "audio/ogg",
}


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
    return await service.queue_of(session, current.user_id, current.device_id)


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
    """Signed URLs of the originals of queue entries (valid for an hour)."""
    ids = [_entry_id(value) for value in body.entry_ids]
    queue = await service.find_queue(session, current.user_id, current.device_id)
    if queue is None:
        return [MediaUrl(entry_id=str(i), url=None, expires_at=None, format=None) for i in ids]
    rows = await session.execute(
        select(PlayQueueEntry.id, AudioFile.id, AudioFile.format)
        .join(Track, Track.id == PlayQueueEntry.track_id)
        .join(Recording, Recording.id == Track.recording_id)
        .join(
            AudioFile,
            (AudioFile.recording_id == Recording.id)
            & (AudioFile.original_status == OriginalStatus.ACTIVE),
        )
        .where(PlayQueueEntry.queue_id == queue.id, PlayQueueEntry.id.in_(ids))
    )
    originals = {entry_id: (file_id, audio_format) for entry_id, file_id, audio_format in rows}
    signer = request.app.state.media_signer
    expires_at = utcnow() + timedelta(seconds=URL_TTL_SECONDS)
    result = []
    for entry_id in ids:
        if entry_id not in originals:
            result.append(MediaUrl(entry_id=str(entry_id), url=None, expires_at=None, format=None))
            continue
        file_id, audio_format = originals[entry_id]
        path = request.app.url_path_for("media_original", audio_file_id=str(file_id))
        params = signer.sign(path, current.user_id, current.user_device_id, URL_TTL_SECONDS)
        result.append(
            MediaUrl(
                entry_id=str(entry_id),
                url=f"{path}?{urlencode(params)}",
                expires_at=expires_at,
                format=audio_format,
            )
        )
    return result


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
