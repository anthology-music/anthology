"""REST routes of the library domain."""

import uuid
from datetime import time
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from anthology.api.deps import AdminSession, require_role
from anthology.core.config import Settings
from anthology.db import get_session
from anthology.jobs import schedules
from anthology.jobs.models import ScheduleFrequency
from anthology.library import adoption, identification, maintenance, superseded
from anthology.library.models import MaintenanceTrigger
from anthology.library.storage import TransferMode
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


class AdoptionStart(BaseModel):
    # Never hardlink: the bytes would stay shared with the referenced file.
    mode: Literal["move", "copy", "reflink"]
    folder: str | None = None


class AdoptionStarted(BaseModel):
    job_id: str | None


@router.post("/library/adoption", status_code=status.HTTP_202_ACCEPTED)
async def start_adoption(
    session: Session, current: AdminSession, request: AdoptionStart
) -> AdoptionStarted:
    """Adopt referenced originals (below ``folder``, or all) into managed storage."""
    try:
        job_id = await adoption.start(
            session,
            mode=TransferMode(request.mode),
            folder=request.folder,
            created_by=current.user_id,
        )
    except adoption.AdoptionRunning as error:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="adoption_running") from error
    await session.commit()
    return AdoptionStarted(job_id=str(job_id) if job_id else None)


class DeletionStarted(BaseModel):
    job_id: str | None


@router.post("/library/superseded/deletion", status_code=status.HTTP_202_ACCEPTED)
async def start_superseded_deletion(session: Session, current: AdminSession) -> DeletionStarted:
    """Delete all superseded managed originals whose replacement verifies (ADR 0021)."""
    try:
        job_id = await superseded.start(session, created_by=current.user_id)
    except superseded.DeletionRunning as error:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="deletion_running") from error
    await session.commit()
    return DeletionStarted(job_id=str(job_id) if job_id else None)


# --- maintenance (spec: jobs, Maintenance configuration; library, Maintenance result) ---------


def _settings(request: Request) -> Settings:
    return request.app.state.settings


class MaintenanceSchedule(BaseModel):
    enabled: bool
    frequency: ScheduleFrequency
    # Local time of the installation's time zone, "HH:MM".
    time: str = Field(pattern=r"^([01][0-9]|2[0-3]):[0-5][0-9]$")
    # 0 = Monday … 6 = Sunday; required for weekly schedules.
    weekday: int | None = Field(default=None, ge=0, le=6)
    options: maintenance.MaintenanceOptions


class MaintenanceScheduleOut(MaintenanceSchedule):
    next_run_at: str | None
    time_zone: str


def _schedule_out(row, settings: Settings) -> MaintenanceScheduleOut:
    return MaintenanceScheduleOut(
        **schedules.schedule_payload(row, maintenance.SCHEDULE, settings.zone),
        time_zone=settings.time_zone,
    )


@router.get("/maintenance/schedule")
async def get_maintenance_schedule(
    session: Session, current: AdminSession, settings: Annotated[Settings, Depends(_settings)]
) -> MaintenanceScheduleOut:
    """The maintenance schedule and options with the next run (admins)."""
    row = await schedules.get_row(session, maintenance.SCHEDULE)
    await session.commit()
    return _schedule_out(row, settings)


@router.put("/maintenance/schedule")
async def put_maintenance_schedule(
    session: Session,
    current: AdminSession,
    settings: Annotated[Settings, Depends(_settings)],
    request: MaintenanceSchedule,
) -> MaintenanceScheduleOut:
    """Change the maintenance schedule and options; they apply from the next run on."""
    hours, minutes = (int(part) for part in request.time.split(":"))
    config = schedules.ScheduleConfig(
        enabled=request.enabled,
        frequency=request.frequency,
        time_of_day=time(hours, minutes),
        weekday=request.weekday,
    )
    try:
        row = await schedules.update_schedule(
            session,
            maintenance.SCHEDULE,
            config,
            request.options,
            zone=settings.zone,
            updated_by=current.user_id,
        )
    except schedules.InvalidSchedule as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(error)) from error
    await session.commit()
    return _schedule_out(row, settings)


class MaintenanceStarted(BaseModel):
    job_id: str


@router.post("/maintenance/runs", status_code=status.HTTP_202_ACCEPTED)
async def start_maintenance(session: Session, current: AdminSession) -> MaintenanceStarted:
    """Run the maintenance now with the configured options; 409 while a run is active."""
    row = await schedules.get_row(session, maintenance.SCHEDULE)
    options = schedules.options_of(maintenance.SCHEDULE, row)
    try:
        job_id = await maintenance.start(
            session, options=options, created_by=current.user_id, trigger=MaintenanceTrigger.MANUAL
        )
    except maintenance.MaintenanceRunning as error:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="maintenance_running") from error
    await session.commit()
    return MaintenanceStarted(job_id=str(job_id))


@router.post("/maintenance/runs/{run_id}/confirm", status_code=status.HTTP_202_ACCEPTED)
async def confirm_maintenance(
    session: Session, current: AdminSession, run_id: uuid.UUID
) -> MaintenanceStarted:
    """Delete the findings of a run the safety limit held back."""
    try:
        job_id = await maintenance.confirm(session, run_id, created_by=current.user_id)
    except maintenance.RunNotFound as error:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="not_found") from error
    except maintenance.RunNotHeld as error:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="not_held") from error
    except maintenance.MaintenanceRunning as error:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="maintenance_running") from error
    await session.commit()
    return MaintenanceStarted(job_id=str(job_id))
