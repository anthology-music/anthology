"""REST routes of the quality analysis."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from anthology.api.deps import require_role
from anthology.db import get_session
from anthology.quality_analysis import service
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
