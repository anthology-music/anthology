"""Downloads of originals with the tags of their context (spec: library, Context-tagged
downloads, Tagged copy cache, Album download; design of change context-tags-on-delivery).

A track download is the cached tagged copy of the track's active original, served with range
requests. An album download is a zip streamed while it is written: each track is its cached
copy or a temporary one that is deleted once it is in the archive, so an album does not fill
the cache. Without the tagger the untagged originals are delivered and the client says so.
"""

import asyncio
import contextlib
import io
import os
import re
import uuid
import zipfile
from collections.abc import AsyncIterator
from datetime import datetime, timedelta
from pathlib import Path
from typing import Annotated
from urllib.parse import quote, urlencode

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from anthology.api.deps import CurrentSession, MediaAccess
from anthology.core.services import ServiceState
from anthology.db import get_session
from anthology.db.types import utcnow
from anthology.library.models import AudioFile, OriginalStatus, Recording, Release, Track
from anthology.transcoding.service import Transcoder

router = APIRouter(tags=["library"])

Session = Annotated[AsyncSession, Depends(get_session)]

# Download URLs live as long as playback URLs (spec: sync-protocol, Short-lived client media
# URLs).
URL_TTL_SECONDS = 3_600
CHUNK = 1024 * 1024
TAGGER_UNAVAILABLE = "tagger_unavailable"
# Invalid in file names on Windows, macOS or Linux, and control characters.
_INVALID = re.compile(r'[\x00-\x1f<>:"/\\|?*]')


class DownloadOut(BaseModel):
    url: str
    expires_at: datetime
    file_name: str
    # False: the file(s) carry no context tags (``notice`` says why).
    tagged: bool
    notice: str | None = None


def safe_name(name: str) -> str:
    cleaned = _INVALID.sub("_", name).strip().rstrip(".")
    return cleaned[:150] or "_"


def track_file_name(title: str, disc: int, number: int, discs: int, suffix: str) -> str:
    """``NN Title.ext``, ``D-NN Title.ext`` on albums with more than one disc."""
    prefix = f"{disc}-{number:02d}" if discs > 1 else f"{number:02d}"
    return f"{prefix} {safe_name(title)}{suffix}"


def attachment(name: str) -> str:
    """A ``Content-Disposition`` header as Starlette's ``FileResponse`` writes it."""
    quoted = quote(name)
    if quoted != name:
        return f"attachment; filename*=utf-8''{quoted}"
    return f'attachment; filename="{name}"'


def _uuid(value: str) -> uuid.UUID:
    try:
        return uuid.UUID(value)
    except ValueError as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail="invalid_id") from error


async def _track(session: AsyncSession, track_id: uuid.UUID):
    """The track, its release, its title in context and its active original."""
    row = (
        await session.execute(
            select(Track, Release, Recording.title, AudioFile)
            .join(Release, Release.id == Track.release_id)
            .join(Recording, Recording.id == Track.recording_id)
            .join(
                AudioFile,
                (AudioFile.recording_id == Track.recording_id)
                & (AudioFile.original_status == OriginalStatus.ACTIVE),
            )
            .where(Track.id == track_id)
        )
    ).first()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="unknown_track")
    track, release, title, original = row
    # Detached, so that they stay readable after the transaction ends (the tagger may take a
    # while, the zip is written after the response started).
    session.expunge_all()
    name = track_file_name(
        track.context_title or title,
        track.disc_number,
        track.track_number,
        release.disc_count,
        Path(original.path).suffix.lower(),
    )
    return track, original, name


def _signed(request: Request, current: CurrentSession, name: str, **params: str) -> tuple:
    path = request.app.url_path_for(name, **params)
    query = request.app.state.media_signer.sign(
        path, current.user_id, current.user_device_id, URL_TTL_SECONDS
    )
    return f"{path}?{urlencode(query)}", utcnow() + timedelta(seconds=URL_TTL_SECONDS)


@router.post("/library/tracks/{track_id}/download")
async def download_track(
    request: Request, session: Session, current: CurrentSession, track_id: str
) -> DownloadOut:
    """A signed URL of a track's original with the tags of this context; the copy is written
    here, so that the answer says whether it carries them."""
    track, original, name = await _track(session, _uuid(track_id))
    await session.rollback()  # no transaction while the tagger writes
    transcoder: Transcoder = request.app.state.transcoder
    copy = await transcoder.original_copy(original, track.id)
    url, expires_at = _signed(request, current, "media_download_track", track_id=str(track.id))
    return DownloadOut(
        url=url,
        expires_at=expires_at,
        file_name=name,
        tagged=copy is not None,
        notice=None if copy is not None else TAGGER_UNAVAILABLE,
    )


@router.get("/media/downloads/tracks/{track_id}", name="media_download_track")
async def media_download_track(
    request: Request, session: Session, _grant: MediaAccess, track_id: str
) -> FileResponse:
    """The tagged copy (or, without the tagger, the original) as an attachment, with range
    requests, so that an interrupted download continues."""
    track, original, name = await _track(session, _uuid(track_id))
    await session.rollback()
    transcoder: Transcoder = request.app.state.transcoder
    copy = await transcoder.original_copy(original, track.id)
    path = transcoder.file(copy) if copy is not None else Path(original.path)
    if not await asyncio.to_thread(path.is_file):
        if copy is not None:
            await transcoder.forget(copy)
            path = Path(original.path)
        if not await asyncio.to_thread(path.is_file):
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="missing_file")
    return FileResponse(
        path,
        filename=name,
        media_type="application/octet-stream",
        headers={"Cache-Control": "private, no-store"},
    )


async def _release(session: AsyncSession, release_id: uuid.UUID):
    release = await session.get(Release, release_id)
    if release is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="unknown_release")
    rows = (
        await session.execute(
            select(Track, Recording.title, AudioFile)
            .join(Recording, Recording.id == Track.recording_id)
            .join(
                AudioFile,
                (AudioFile.recording_id == Track.recording_id)
                & (AudioFile.original_status == OriginalStatus.ACTIVE),
            )
            .where(Track.release_id == release_id)
            .order_by(Track.disc_number, Track.track_number, Track.id)
        )
    ).all()
    tracks = [
        (
            track.id,
            original,
            track_file_name(
                track.context_title or title,
                track.disc_number,
                track.track_number,
                release.disc_count,
                Path(original.path).suffix.lower(),
            ),
        )
        for track, title, original in rows
    ]
    session.expunge_all()
    name = safe_name(f"{release.album_artist_display} - {release.title}")
    return name, tracks


def _tagger_available(request: Request) -> bool:
    monitor = getattr(request.app.state, "tagger_monitor", None)
    if request.app.state.transcoder.tagger is None:
        return False
    return monitor is None or monitor.state in (None, ServiceState.AVAILABLE)


@router.post("/library/releases/{release_id}/download")
async def download_release(
    request: Request, session: Session, current: CurrentSession, release_id: str
) -> DownloadOut:
    """A signed URL of the album as a zip of tagged copies."""
    name, tracks = await _release(session, _uuid(release_id))
    if not tracks:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="no_tracks")
    url, expires_at = _signed(request, current, "media_download_release", release_id=release_id)
    tagged = _tagger_available(request)
    return DownloadOut(
        url=url,
        expires_at=expires_at,
        file_name=f"{name}.zip",
        tagged=tagged,
        notice=None if tagged else TAGGER_UNAVAILABLE,
    )


@router.get("/media/downloads/releases/{release_id}", name="media_download_release")
async def media_download_release(
    request: Request, session: Session, _grant: MediaAccess, release_id: str
) -> StreamingResponse:
    """The album as a zip, streamed while it is written (no range requests)."""
    name, tracks = await _release(session, _uuid(release_id))
    await session.rollback()
    if not tracks:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="no_tracks")
    zip_name = f"{name}.zip"
    return StreamingResponse(
        album_zip(request.app.state.transcoder, name, tracks),
        media_type="application/zip",
        headers={"Content-Disposition": attachment(zip_name), "Cache-Control": "private, no-store"},
    )


class _Pipe(io.RawIOBase):
    """A non-seekable sink: ``zipfile`` then writes data descriptors after each file."""

    def __init__(self) -> None:
        self._chunks: list[bytes] = []

    def writable(self) -> bool:
        return True

    def write(self, data) -> int:
        self._chunks.append(bytes(data))
        return len(data)

    def take(self) -> bytes:
        data = b"".join(self._chunks)
        self._chunks.clear()
        return data


async def album_zip(
    transcoder: Transcoder, folder: str, tracks: list[tuple[uuid.UUID, AudioFile, str]]
) -> AsyncIterator[bytes]:
    """A stored (uncompressed) zip with one folder: audio is compressed already."""
    pipe = _Pipe()
    archive = zipfile.ZipFile(pipe, "w", compression=zipfile.ZIP_STORED, allowZip64=True)
    for track_id, original, name in tracks:
        source, temporary = await _album_source(transcoder, original, track_id)
        try:
            handle = await asyncio.to_thread(open, source, "rb")
        except OSError:
            continue  # a missing file is left out
        try:
            info = zipfile.ZipInfo(f"{folder}/{name}", date_time=datetime.now().timetuple()[:6])
            info.compress_type = zipfile.ZIP_STORED
            with archive.open(info, "w", force_zip64=True) as entry:
                while data := await asyncio.to_thread(handle.read, CHUNK):
                    entry.write(data)
                    if chunk := pipe.take():
                        yield chunk
            if chunk := pipe.take():
                yield chunk
        finally:
            await asyncio.to_thread(handle.close)
            if temporary:
                with contextlib.suppress(FileNotFoundError):
                    await asyncio.to_thread(os.unlink, source)
    archive.close()
    yield pipe.take()


async def _album_source(
    transcoder: Transcoder, original: AudioFile, track_id: uuid.UUID
) -> tuple[Path, bool]:
    """The cached tagged copy, else a temporary one, else the untagged original; and whether
    it is temporary."""
    cached = await transcoder.cached_copy(original.id, track_id)
    if cached is not None:
        return cached, False
    temporary = await transcoder.temporary_copy(original, track_id)
    if temporary is not None:
        return temporary, True
    return Path(original.path), False
