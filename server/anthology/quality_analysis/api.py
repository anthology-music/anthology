"""REST routes of the quality analysis."""

import asyncio
import os
import re
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from anthology.api.deps import require_role
from anthology.db import get_session
from anthology.library import service as library
from anthology.quality_analysis import service, spectrogram
from anthology.quality_analysis.analysis import DecodeError
from anthology.quality_analysis.schemas import AnalysisStart, AnalysisStarted
from anthology.users.models import Role
from anthology.users.service import SessionInfo

router = APIRouter(tags=["quality-analysis"])

Session = Annotated[AsyncSession, Depends(get_session)]
Editor = Annotated[SessionInfo, Depends(require_role(Role.ADMIN, Role.EDITOR))]


@router.post("/quality-analysis", status_code=status.HTTP_202_ACCEPTED)
async def start_analysis(
    session: Session, current: Editor, request: AnalysisStart
) -> AnalysisStarted:
    """Analyse the effective quality of all files without a result (spec: Analysis job)."""
    try:
        job_id = await service.start(session, created_by=current.user_id, full=request.full)
    except service.AnalysisRunning as error:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="analysis_running") from error
    await session.commit()
    return AnalysisStarted(job_id=str(job_id) if job_id else None)


AUDIO_HASH = re.compile(r"^[0-9a-f]{16,128}$")


def _write(target: Path, data: bytes) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(f".{target.name}.part")
    temporary.write_bytes(data)
    os.replace(temporary, target)


@router.get(
    "/quality-analysis/{audio_hash}/spectrogram.png",
    response_class=Response,
    responses={200: {"content": {"image/png": {}}}},
)
async def get_spectrogram(
    request: Request, session: Session, _current: Editor, audio_hash: str
) -> Response:
    """The spectrogram of an audio hash as evidence in the review list (spec: review, Quality
    findings); rendered on first request and cached."""
    if not AUDIO_HASH.match(audio_hash):
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="not_found")
    settings = request.app.state.settings
    cached = settings.data_dir / "spectrograms" / audio_hash[:2] / f"{audio_hash}.png"
    if not await asyncio.to_thread(cached.is_file):
        original = await library.original_by_audio_hash(session, audio_hash)
        if original is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="not_found")
        recording = await library.get_recording(session, original.recording_id)
        path, duration_s = original.path, recording.duration_ms / 1000
        await session.close()
        if not await asyncio.to_thread(Path(path).is_file):
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="file_missing")
        try:
            image = await spectrogram.render(path, duration_s, ffmpeg=settings.ffmpeg_path)
        except DecodeError as error:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail=error.reason) from error
        await asyncio.to_thread(_write, cached, image)
    else:
        image = await asyncio.to_thread(cached.read_bytes)
    return Response(image, media_type="image/png", headers={"Cache-Control": "private"})
