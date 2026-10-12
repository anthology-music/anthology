"""REST routes of the jobs domain."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from anthology.api.deps import CurrentSession
from anthology.db import get_session
from anthology.jobs import schemas, service
from anthology.jobs.demo import DEMO_TYPE
from anthology.jobs.models import Job
from anthology.users.models import Role

router = APIRouter(tags=["jobs"])

Session = Annotated[AsyncSession, Depends(get_session)]

_STATUS = {
    service.JobNotFoundError: status.HTTP_404_NOT_FOUND,
    service.JobForbiddenError: status.HTTP_403_FORBIDDEN,
    service.InvalidTransitionError: status.HTTP_409_CONFLICT,
}


def _http(error: service.JobsError) -> HTTPException:
    return HTTPException(status_code=_STATUS[type(error)], detail=error.code)


@router.get("/jobs/{job_id}")
async def get_job(session: Session, _current: CurrentSession, job_id: uuid.UUID) -> schemas.JobOut:
    job = await session.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not_found")
    return schemas.JobOut.model_validate(job)


async def _control(action, session: AsyncSession, current, job_id: uuid.UUID) -> schemas.JobOut:
    try:
        job = await action(session, current, job_id)
    except service.JobsError as error:
        raise _http(error) from error
    return schemas.JobOut.model_validate(job)


@router.post("/jobs/{job_id}/pause")
async def pause(session: Session, current: CurrentSession, job_id: uuid.UUID) -> schemas.JobOut:
    return await _control(service.pause_job, session, current, job_id)


@router.post("/jobs/{job_id}/resume")
async def resume(session: Session, current: CurrentSession, job_id: uuid.UUID) -> schemas.JobOut:
    return await _control(service.resume_job, session, current, job_id)


@router.post("/jobs/{job_id}/cancel")
async def cancel(session: Session, current: CurrentSession, job_id: uuid.UUID) -> schemas.JobOut:
    return await _control(service.cancel_job, session, current, job_id)


@router.post("/dev/jobs/demo", status_code=status.HTTP_201_CREATED, tags=["dev"])
async def create_demo_job(
    request: Request, session: Session, current: CurrentSession, body: schemas.DemoJobRequest
) -> schemas.JobOut:
    """Start a demo job (developer installations with ANTHOLOGY_DEV_DEMO=true only)."""
    if not request.app.state.settings.dev_demo:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not_found")
    if current.role == Role.LISTENER:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="forbidden")
    async with session.begin():
        job = await service.create_job(
            session,
            type_=DEMO_TYPE,
            title=f"Demo · {body.items} items",
            items=[f"Demo item {index + 1}" for index in range(body.items)],
            created_by=current.user_id,
            params={"seconds_per_item": body.seconds_per_item},
            parallel_items=body.parallel_items,
        )
    return schemas.JobOut.model_validate(job)
