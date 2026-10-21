"""REST routes of the library domain."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from anthology.api.deps import require_role
from anthology.db import get_session
from anthology.library import identification
from anthology.users.models import Role
from anthology.users.service import SessionInfo

router = APIRouter(tags=["library"])

Session = Annotated[AsyncSession, Depends(get_session)]
Editor = Annotated[SessionInfo, Depends(require_role(Role.ADMIN, Role.EDITOR))]


class IdentificationStart(BaseModel):
    full: bool = False


class IdentificationStarted(BaseModel):
    job_id: str | None


@router.post("/library/identification", status_code=status.HTTP_202_ACCEPTED)
async def start_identification(
    session: Session, current: Editor, request: IdentificationStart
) -> IdentificationStarted:
    """Start identifying the recordings without MusicBrainz ID (spec: Identification job)."""
    try:
        job_id = await identification.start(session, created_by=current.user_id, full=request.full)
    except identification.IdentificationRunning as error:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="identification_running") from error
    await session.commit()
    return IdentificationStarted(job_id=str(job_id) if job_id else None)
