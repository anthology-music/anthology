"""Schedules of recurring jobs (spec: jobs, Scheduled maintenance; Maintenance configuration)."""

import asyncio
import uuid
from datetime import UTC, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from pydantic import BaseModel
from sqlalchemy import func, select, update

from anthology.core.config import Settings
from anthology.db import create_engine, create_sessionmaker
from anthology.jobs import schedules
from anthology.jobs import service as jobs
from anthology.jobs.models import Job, JobSchedule, JobStatus, ScheduleFrequency
from anthology.jobs.schedules import ScheduleConfig, Scheduler, ScheduleRegistry, ScheduleSpec
from anthology.library import maintenance
from tests.import_helpers import client_for, import_app
from tests.users_helpers import create_user, login, setup_admin

pytestmark = pytest.mark.usefixtures("clean_db")

BERLIN = ZoneInfo("Europe/Berlin")
DAILY_3 = ScheduleConfig(True, ScheduleFrequency.DAILY, time(3))


def utc(*args) -> datetime:
    return datetime(*args, tzinfo=UTC)


# --- computing the next run ---------------------------------------------------------------------


def test_daily_runs_today_or_tomorrow() -> None:
    assert schedules.next_run(DAILY_3, utc(2026, 10, 23, 0, 30), BERLIN) == utc(2026, 10, 23, 1)
    # Strictly after: the time just run is not due again.
    assert schedules.next_run(DAILY_3, utc(2026, 10, 23, 1, 0, 1), BERLIN) == utc(2026, 10, 24, 1)


def test_weekly_on_the_weekday() -> None:
    sunday_4 = ScheduleConfig(True, ScheduleFrequency.WEEKLY, time(4), weekday=6)
    friday = utc(2026, 10, 23, 12)
    assert schedules.next_run(sunday_4, friday, BERLIN) == utc(2026, 10, 25, 3)  # 04:00 CET
    # On the Sunday after 04:00: one week later.
    assert schedules.next_run(sunday_4, utc(2026, 10, 25, 4), BERLIN) == utc(2026, 11, 1, 3)


def test_daylight_saving() -> None:
    # 2026-03-29: Berlin skips 02:00-03:00; 02:30 does not exist and runs at 03:30 CEST.
    half_past_2 = ScheduleConfig(True, ScheduleFrequency.DAILY, time(2, 30))
    assert schedules.next_run(half_past_2, utc(2026, 3, 28, 12), BERLIN) == utc(2026, 3, 29, 1, 30)
    # 2026-10-25: 02:30 occurs twice; the first occurrence (CEST) is taken.
    assert schedules.next_run(half_past_2, utc(2026, 10, 24, 12), BERLIN) == utc(
        2026, 10, 25, 0, 30
    )
    # 03:00 local is 01:00 UTC in summer and 02:00 UTC in winter.
    assert schedules.next_run(DAILY_3, utc(2026, 10, 25, 0), BERLIN) == utc(2026, 10, 25, 2)


def test_switched_off_has_no_next_run() -> None:
    off = ScheduleConfig(False, ScheduleFrequency.DAILY, time(3))
    assert schedules.next_run(off, utc(2026, 10, 23), BERLIN) is None


def test_weekly_needs_a_weekday() -> None:
    with pytest.raises(schedules.InvalidSchedule):
        schedules.validate(ScheduleConfig(True, ScheduleFrequency.WEEKLY, time(3)))


# --- claiming due schedules ----------------------------------------------------------------------


class Options(BaseModel):
    note: str = "default"


class Clock:
    def __init__(self, now: datetime) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now


def spec() -> ScheduleSpec:
    async def start(session, options, created_by: uuid.UUID) -> uuid.UUID:
        job = await jobs.create_job(
            session,
            type_="test_scheduled",
            title=f"Scheduled {options.note}",
            items=["one"],
            created_by=created_by,
        )
        return job.id

    return ScheduleSpec("test_scheduled", DAILY_3, Options, start)


def registry() -> ScheduleRegistry:
    result = ScheduleRegistry()
    result.register(spec())
    return result


async def admin_app(settings: Settings, tmp_path: Path):
    return import_app(settings, tmp_path / "imports", tmp_path / "library")


async def scheduled_jobs(app) -> list[Job]:
    async with app.state.sessionmaker() as session:
        return list(await session.scalars(select(Job).where(Job.type == "test_scheduled")))


async def test_first_check_computes_the_time_then_runs_once(
    settings: Settings, tmp_path: Path
) -> None:
    async with await admin_app(settings, tmp_path) as app, client_for(app) as client:
        await setup_admin(client)
        clock = Clock(utc(2026, 10, 23, 12))
        scheduler = Scheduler(app.state.sessionmaker, registry(), BERLIN, clock=clock)
        first = await scheduler.run_once()  # computes the first time only
        clock.now = utc(2026, 10, 24, 0, 59)
        early = await scheduler.run_once()
        clock.now = utc(2026, 10, 24, 1, 0, 30)
        due = await scheduler.run_once()
        again = await scheduler.run_once()
        async with app.state.sessionmaker() as session:
            row = await session.get_one(JobSchedule, "test_scheduled")
        created = await scheduled_jobs(app)

    assert first == [] and early == [] and again == []
    assert len(due) == 1 and [job.id for job in created] == due
    assert row.last_job_id == due[0]
    assert row.next_run_at == utc(2026, 10, 25, 2)  # 03:00 CET after the clock change


async def test_two_processes_create_exactly_one_job(settings: Settings, tmp_path: Path) -> None:
    async with await admin_app(settings, tmp_path) as app, client_for(app) as client:
        await setup_admin(client)
        clock = Clock(utc(2026, 10, 23, 12))
        # The second scheduler has its own engine, as in a second server process.
        engine = create_engine(app.state.settings)
        try:
            first = Scheduler(app.state.sessionmaker, registry(), BERLIN, clock=clock)
            second = Scheduler(create_sessionmaker(engine), registry(), BERLIN, clock=clock)
            await first.run_once()
            clock.now = utc(2026, 10, 24, 1, 0, 30)
            results = await asyncio.gather(
                *(scheduler.run_once() for scheduler in (first, second, first, second))
            )
        finally:
            await engine.dispose()
        created = await scheduled_jobs(app)

    assert sum(len(result) for result in results) == 1
    assert len(created) == 1


async def test_occurrence_skipped_while_a_job_is_unfinished(
    settings: Settings, tmp_path: Path
) -> None:
    async with await admin_app(settings, tmp_path) as app, client_for(app) as client:
        await setup_admin(client)
        clock = Clock(utc(2026, 10, 23, 12))
        scheduler = Scheduler(app.state.sessionmaker, registry(), BERLIN, clock=clock)
        await scheduler.run_once()
        clock.now = utc(2026, 10, 24, 1, 1)
        [job_id] = await scheduler.run_once()
        clock.now = utc(2026, 10, 25, 2, 1)  # the next night, the first job still queued
        skipped = await scheduler.run_once()
        async with app.state.sessionmaker() as session, session.begin():
            await session.execute(update(Job).where(Job.id == job_id).values(status=JobStatus.DONE))
        clock.now = utc(2026, 10, 26, 2, 1)
        third = await scheduler.run_once()
        async with app.state.sessionmaker() as session:
            row = await session.get_one(JobSchedule, "test_scheduled")

    assert skipped == []
    assert len(third) == 1
    assert row.next_run_at == utc(2026, 10, 27, 2)


async def test_switched_off_and_without_admin_nothing_runs(
    settings: Settings, tmp_path: Path
) -> None:
    async with await admin_app(settings, tmp_path) as app:
        clock = Clock(utc(2026, 10, 23, 12))
        scheduler = Scheduler(app.state.sessionmaker, registry(), BERLIN, clock=clock)
        await scheduler.run_once()
        clock.now = utc(2026, 10, 24, 1, 1)
        no_admin = await scheduler.run_once()  # fresh installation: nobody to run it for
        async with app.state.sessionmaker() as session, session.begin():
            row = await schedules.get_row(session, spec())
            await schedules.update_schedule(
                session,
                spec(),
                ScheduleConfig(False, ScheduleFrequency.DAILY, time(3)),
                Options(),
                zone=BERLIN,
                updated_by=None,
                now=clock.now,
            )
        clock.now = utc(2026, 10, 30, 1, 1)
        off = await scheduler.run_once()
        async with app.state.sessionmaker() as session:
            count = await session.scalar(select(func.count()).select_from(Job))
            row = await session.get_one(JobSchedule, "test_scheduled")

    assert no_admin == [] and off == []
    assert count == 0
    assert row.next_run_at is None


async def test_migration_creates_the_maintenance_schedule(engine) -> None:
    # clean_db removed the migrated row; the scheduler recreates it with the defaults.
    from sqlalchemy.ext.asyncio import async_sessionmaker

    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    async with sessionmaker() as session, session.begin():
        row = await schedules.get_row(session, maintenance.SCHEDULE)
        options = schedules.options_of(maintenance.SCHEDULE, row)

    assert (row.enabled, row.frequency, row.time_of_day) == (True, ScheduleFrequency.DAILY, time(3))
    assert options == maintenance.MaintenanceOptions()
    assert (options.action, options.grace_hours, options.safety_share_percent) == (
        "delete",
        24,
        1.0,
    )


# --- API ---------------------------------------------------------------------------------------


async def test_schedule_api_defaults_change_and_roles(settings: Settings, tmp_path: Path) -> None:
    settings = settings.model_copy(update={"time_zone": "Europe/Berlin"})
    async with await admin_app(settings, tmp_path) as app, client_for(app) as client:
        owner = await setup_admin(client)
        await create_user(client, owner, "editor", role="editor")
        editor = await login(client, "editor")
        defaults = await client.get("/api/v1/maintenance/schedule", headers=owner.headers)
        weekly = {
            "enabled": True,
            "frequency": "weekly",
            "time": "04:00",
            "weekday": 6,
            "options": {"action": "report", "grace_hours": 48, "safety_share_percent": None},
        }
        changed = await client.put(
            "/api/v1/maintenance/schedule", headers=owner.headers, json=weekly
        )
        invalid = [
            await client.put(
                "/api/v1/maintenance/schedule",
                headers=owner.headers,
                json={**weekly, **change},
            )
            for change in (
                {"weekday": None},
                {"time": "25:00"},
                {"options": {"grace_hours": 0}},
                {"options": {"grace_hours": 169}},
                {"options": {"safety_share_percent": 0}},
                {"options": {"action": "shred"}},
            )
        ]
        refused = [
            await client.get("/api/v1/maintenance/schedule", headers=editor.headers),
            await client.put("/api/v1/maintenance/schedule", headers=editor.headers, json=weekly),
        ]
        stored = await client.get("/api/v1/maintenance/schedule", headers=owner.headers)

    assert defaults.status_code == 200
    body = defaults.json()
    assert (body["enabled"], body["frequency"], body["time"], body["weekday"]) == (
        True,
        "daily",
        "03:00",
        None,
    )
    assert body["options"] == {"action": "delete", "grace_hours": 24, "safety_share_percent": 1.0}
    assert body["time_zone"] == "Europe/Berlin"
    assert body["next_run_at"] is not None
    assert changed.status_code == 200
    next_run = datetime.fromisoformat(changed.json()["next_run_at"]).astimezone(BERLIN)
    assert (next_run.weekday(), next_run.hour, next_run.minute) == (6, 4, 0)
    assert next_run - datetime.now(BERLIN) <= timedelta(days=7)
    assert stored.json()["options"]["safety_share_percent"] is None
    assert [response.status_code for response in invalid] == [422] * 6
    assert [response.status_code for response in refused] == [403, 403]


def test_unknown_time_zone_is_refused() -> None:
    with pytest.raises(ValueError, match="time zone"):
        Settings(time_zone="Mars/Olympus")
