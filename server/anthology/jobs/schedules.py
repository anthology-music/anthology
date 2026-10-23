"""Schedules of recurring jobs (spec: jobs, Scheduled maintenance; Maintenance configuration).

A job type that may run on a schedule registers a ``ScheduleSpec``: its default schedule, the
pydantic model of its options and the function that starts a job. One row per type in
``job_schedules`` holds the configuration and the next run (UTC). Every process checks the
due schedules once a minute; a process claims an occurrence by moving ``next_run_at`` with a
compare-and-swap update, so exactly one process creates the job. An occurrence reached while
a job of the type is unfinished is skipped.

Times of day are local to ``ANTHOLOGY_TIME_ZONE``. A local time that does not exist on a day
(daylight saving starts) runs at the corresponding later time; a time that occurs twice runs
at its first occurrence.
"""

import asyncio
import contextlib
import json
import logging
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from pydantic import BaseModel
from sqlalchemy import update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from anthology.db.types import utcnow
from anthology.jobs import service
from anthology.jobs.models import JobSchedule, ScheduleFrequency
from anthology.users import service as users

logger = logging.getLogger(__name__)

CHECK_INTERVAL = 60.0

Clock = Callable[[], datetime]
# Starts a job with the validated options on behalf of ``created_by``; returns its ID.
Starter = Callable[[AsyncSession, BaseModel, uuid.UUID], Awaitable[uuid.UUID | None]]


@dataclass(frozen=True)
class ScheduleConfig:
    enabled: bool
    frequency: ScheduleFrequency
    time_of_day: time
    weekday: int | None = None  # 0 = Monday … 6 = Sunday, weekly only


@dataclass(frozen=True)
class ScheduleSpec:
    type: str
    default: ScheduleConfig
    options: type[BaseModel]
    start: Starter


class ScheduleRegistry:
    def __init__(self) -> None:
        self._specs: dict[str, ScheduleSpec] = {}

    def register(self, spec: ScheduleSpec) -> None:
        if spec.type in self._specs:
            raise ValueError(f"schedule {spec.type!r} already registered")
        self._specs[spec.type] = spec

    def get(self, type_: str) -> ScheduleSpec | None:
        return self._specs.get(type_)

    def all(self) -> list[ScheduleSpec]:
        return list(self._specs.values())


class InvalidSchedule(ValueError):
    pass


def validate(config: ScheduleConfig) -> ScheduleConfig:
    if config.frequency == ScheduleFrequency.WEEKLY:
        if config.weekday is None or not 0 <= config.weekday <= 6:
            raise InvalidSchedule("weekday_required")
        return config
    return ScheduleConfig(config.enabled, config.frequency, config.time_of_day, None)


def _local(day, at: time, zone: ZoneInfo) -> datetime:
    """``day`` at ``at`` in ``zone`` as UTC; a non-existent local time moves forward."""
    local = datetime.combine(day, at.replace(tzinfo=None), tzinfo=zone)
    # fold=0 interprets a time in the gap with the offset before the change: as UTC that is
    # the later wall-clock time after the change. A repeated time takes its first occurrence.
    return local.astimezone(UTC)


def next_run(config: ScheduleConfig, after: datetime, zone: ZoneInfo) -> datetime | None:
    """The first scheduled time strictly after ``after`` (UTC), or None when switched off."""
    if not config.enabled:
        return None
    day = after.astimezone(zone).date()
    for offset in range(8 if config.frequency == ScheduleFrequency.WEEKLY else 2):
        candidate_day = day + timedelta(days=offset)
        if (
            config.frequency == ScheduleFrequency.WEEKLY
            and candidate_day.weekday() != config.weekday
        ):
            continue
        candidate = _local(candidate_day, config.time_of_day, zone)
        if candidate > after:
            return candidate
    raise AssertionError("a daily or weekly time recurs within eight days")


def config_of(row: JobSchedule) -> ScheduleConfig:
    return ScheduleConfig(row.enabled, row.frequency, row.time_of_day, row.weekday)


def options_of(spec: ScheduleSpec, row: JobSchedule) -> BaseModel:
    """The stored options, completed with the defaults of the job type."""
    try:
        return spec.options.model_validate(json.loads(row.options_json or "{}"))
    except ValueError:
        logger.warning("invalid stored options of schedule %s; using defaults", spec.type)
        return spec.options()


async def get_row(session: AsyncSession, spec: ScheduleSpec) -> JobSchedule:
    """The schedule row of ``spec``; created with the defaults if it is missing."""
    row = await session.get(JobSchedule, spec.type, populate_existing=True)
    if row is not None:
        return row
    insert = pg_insert if session.bind.dialect.name == "postgresql" else sqlite_insert
    await session.execute(
        insert(JobSchedule)
        .values(
            type=spec.type,
            enabled=spec.default.enabled,
            frequency=spec.default.frequency,
            time_of_day=spec.default.time_of_day,
            weekday=spec.default.weekday,
            options_json=spec.options().model_dump_json(),
        )
        .on_conflict_do_nothing(index_elements=["type"])
    )
    return await session.get_one(JobSchedule, spec.type, populate_existing=True)


async def update_schedule(
    session: AsyncSession,
    spec: ScheduleSpec,
    config: ScheduleConfig,
    options: BaseModel,
    *,
    zone: ZoneInfo,
    updated_by: uuid.UUID | None,
    now: datetime | None = None,
) -> JobSchedule:
    """Store a new configuration; it applies from the next run on."""
    config = validate(config)
    now = now or utcnow()
    row = await get_row(session, spec)
    row.enabled = config.enabled
    row.frequency = config.frequency
    row.time_of_day = config.time_of_day
    row.weekday = config.weekday
    row.options_json = options.model_dump_json()
    row.next_run_at = next_run(config, now, zone)
    row.updated_by = updated_by
    row.updated_at = now
    await session.flush()
    return row


class Scheduler:
    """Creates the jobs of due schedules; one per process, coordinated through the database."""

    def __init__(
        self,
        sessionmaker: async_sessionmaker,
        registry: ScheduleRegistry,
        zone: ZoneInfo,
        *,
        clock: Clock = utcnow,
    ) -> None:
        self._sessionmaker = sessionmaker
        self._registry = registry
        self._zone = zone
        self._clock = clock
        self._task: asyncio.Task | None = None

    async def start(self) -> None:
        self._task = asyncio.create_task(self._loop(), name="anthology-schedules")

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None

    async def _loop(self) -> None:
        while True:
            try:
                await self.run_once()
            except Exception:
                logger.warning("schedule check failed", exc_info=True)
            await asyncio.sleep(CHECK_INTERVAL)

    async def run_once(self) -> list[uuid.UUID]:
        """Create the jobs of all due schedules; returns the IDs of the created jobs."""
        created: list[uuid.UUID] = []
        for spec in self._registry.all():
            job_id = await self._check(spec)
            if job_id is not None:
                created.append(job_id)
        return created

    async def _check(self, spec: ScheduleSpec) -> uuid.UUID | None:
        now = self._clock()
        async with self._sessionmaker() as session, session.begin():
            row = await get_row(session, spec)
            seen = row.next_run_at
            config = config_of(row)
            if (seen is not None and seen > now) or (seen is None and not config.enabled):
                return None
            following = next_run(config, now, self._zone)
            # Compare-and-swap: only the process that moves the time it saw creates the job.
            moved = await session.execute(
                update(JobSchedule)
                .where(
                    JobSchedule.type == spec.type,
                    JobSchedule.next_run_at.is_(None)
                    if seen is None
                    else JobSchedule.next_run_at == seen,
                )
                .values(next_run_at=following)
                .execution_options(synchronize_session=False)
            )
            if not moved.rowcount or seen is None or not config.enabled:
                # Claimed by another process, the first time just computed, or switched off.
                return None
            if await service.has_unfinished_job(session, spec.type):
                logger.info("schedule %s skipped: a job is still unfinished", spec.type)
                return None
            # Scheduled jobs belong to the admin who last changed the schedule.
            created_by = await users.active_admin(session, row.updated_by)
            if created_by is None:
                logger.info("schedule %s skipped: no admin to run it for", spec.type)
                return None
            job_id = await spec.start(session, options_of(spec, row), created_by)
            if job_id is not None:
                await session.execute(
                    update(JobSchedule)
                    .where(JobSchedule.type == spec.type)
                    .values(last_job_id=job_id)
                    .execution_options(synchronize_session=False)
                )
            return job_id


def schedule_payload(row: JobSchedule, spec: ScheduleSpec, zone: ZoneInfo) -> dict[str, Any]:
    """The configuration as the API shows it; a first run not yet computed by a scheduler
    is shown as it will be computed."""
    next_run_at = row.next_run_at or next_run(config_of(row), utcnow(), zone)
    return {
        "enabled": row.enabled,
        "frequency": row.frequency,
        "time": row.time_of_day.strftime("%H:%M"),
        "weekday": row.weekday,
        "options": options_of(spec, row).model_dump(mode="json"),
        "next_run_at": next_run_at.isoformat() if next_run_at else None,
    }
