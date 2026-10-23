"""Library maintenance: orphaned files, leftovers, missing originals and the safety limit (spec:
library, Orphaned files in managed storage; Maintenance safety limit; Missing originals;
Maintenance result; jobs, Scheduled maintenance; UC-001). Files are random bytes on a
temporary storage."""

import dataclasses
import os
import time
import uuid
from datetime import UTC, datetime
from datetime import time as clock_time
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from fastapi import FastAPI
from sqlalchemy import func, select, update

from anthology.core.config import Settings
from anthology.jobs import schedules
from anthology.jobs.models import Job, JobStatus, ScheduleFrequency
from anthology.library import maintenance, service, storage
from anthology.library.maintenance import MaintenanceOptions
from anthology.library.models import (
    AudioFile,
    FindingKind,
    FindingOutcome,
    MaintenanceAction,
    MaintenanceFinding,
    MaintenanceRun,
    MaintenanceStatus,
    MaintenanceTrigger,
    StorageMode,
)
from tests.import_helpers import client_for, context, import_app, run_job
from tests.library_helpers import audio
from tests.users_helpers import create_user, login, setup_admin
from tests.ws_helpers import ws_connect

pytestmark = pytest.mark.usefixtures("clean_db")

TWO_DAYS = 2 * 24 * 3600


def write(path: Path, size: int = 1_000, age_seconds: float = TWO_DAYS) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(os.urandom(size))
    stamp = time.time() - age_seconds
    os.utime(path, (stamp, stamp))
    return path


def originals(library: Path) -> Path:
    return storage.originals_dir(library)


async def add_original(app: FastAPI, path: Path, mode=StorageMode.MANAGED) -> uuid.UUID:
    """A recording whose original is ``path``; returns the audio file ID."""
    info = dataclasses.replace(audio(str(path)), storage_mode=mode, size_bytes=1_000)
    async with app.state.sessionmaker() as session, session.begin():
        artist = await service.get_or_create_artist(session, "Nordlicht")
        release = await service.create_release(session, title="Polarnacht", album_artist=artist)
        track = await service.add_recording(
            session,
            release=release,
            title=path.stem,
            artist=artist,
            duration_ms=200_000,
            track_number=1,
            audio=info,
        )
        return (await service.active_original(session, track.recording_id)).id


async def admin(app: FastAPI) -> uuid.UUID:
    async with client_for(app) as client:
        return uuid.UUID((await setup_admin(client)).user["id"])


async def run_to_end(app: FastAPI, job_id: uuid.UUID) -> None:
    """Run the job's items and finish it, as the runner does."""
    await run_job(app, job_id)
    async with app.state.sessionmaker() as session, session.begin():
        await session.execute(update(Job).where(Job.id == job_id).values(status=JobStatus.DONE))


async def run(app: FastAPI, user: uuid.UUID, **options) -> MaintenanceRun:
    async with app.state.sessionmaker() as session, session.begin():
        job_id = await maintenance.start(
            session,
            options=MaintenanceOptions(**options),
            created_by=user,
            trigger=MaintenanceTrigger.MANUAL,
        )
    await run_to_end(app, job_id)
    return await latest(app)


async def latest(app: FastAPI) -> MaintenanceRun:
    async with app.state.sessionmaker() as session:
        return await session.scalar(
            select(MaintenanceRun).order_by(MaintenanceRun.started_at.desc()).limit(1)
        )


async def findings(app: FastAPI, run_id: uuid.UUID) -> dict[str, MaintenanceFinding]:
    async with app.state.sessionmaker() as session:
        rows = await session.scalars(
            select(MaintenanceFinding).where(MaintenanceFinding.run_id == run_id)
        )
        return {Path(finding.path).name: finding for finding in rows}


@pytest.fixture
def library(tmp_path: Path) -> Path:
    return tmp_path / "library"


@pytest.fixture
async def app(settings: Settings, tmp_path: Path, library: Path):
    async with import_app(settings, tmp_path / "imports", library) as app:
        yield app


def test_safety_limit_share_minimum_and_off() -> None:
    assert maintenance.safety_limit(1.0, 50_000) == 500
    assert maintenance.safety_limit(1.0, 300) == 10  # at least 10 files
    assert maintenance.safety_limit(0.5, 12_345) == 62  # rounded up
    assert maintenance.safety_limit(None, 50_000) is None


async def test_orphans_and_leftovers_are_deleted_others_kept(
    app: FastAPI, library: Path, tmp_path: Path
) -> None:
    user = await admin(app)
    store = originals(library)
    kept = write(store / "ab" / "kept.flac")
    await add_original(app, kept)
    orphan = write(store / "cd" / "orphan.flac", size=4_000)
    part = write(store / "cd" / ".new.flac.part", size=500)
    probe = write(store / ".probe-1234", size=0)
    young = write(store / "ef" / "young.flac", age_seconds=3600)  # a running import's file
    outside = write(tmp_path / "music" / "referenced.flac")
    await add_original(app, outside, StorageMode.REFERENCED)
    stray = write(tmp_path / "music" / "not-in-library.flac")
    missing = store / "01" / "missing.flac"
    missing_id = await add_original(app, missing)  # its file was deleted by hand

    result = await run(app, user)
    found = await findings(app, result.id)
    async with app.state.sessionmaker() as session:
        entry = await session.get(AudioFile, missing_id)

    assert result.status == MaintenanceStatus.DONE
    assert {name: finding.kind for name, finding in found.items()} == {
        "orphan.flac": FindingKind.ORPHAN,
        ".new.flac.part": FindingKind.LEFTOVER,
        ".probe-1234": FindingKind.LEFTOVER,
        "missing.flac": FindingKind.MISSING,
    }
    assert {name: finding.outcome for name, finding in found.items()} == {
        "orphan.flac": FindingOutcome.DELETED,
        ".new.flac.part": FindingOutcome.DELETED,
        ".probe-1234": FindingOutcome.DELETED,
        "missing.flac": FindingOutcome.LISTED,
    }
    assert not orphan.exists() and not part.exists() and not probe.exists()
    assert kept.exists() and young.exists() and outside.exists() and stray.exists()
    assert entry is not None  # the missing original stays in the library
    assert (result.orphan_files, result.orphan_bytes) == (1, 4_000)
    assert (result.leftover_files, result.leftover_bytes) == (2, 500)
    assert (result.deleted_files, result.deleted_bytes) == (3, 4_500)
    assert (result.missing_files, result.missing_bytes) == (1, 1_000)
    assert result.listed_files == 0
    assert result.finished_at is not None


async def test_report_only_lists_and_keeps(app: FastAPI, library: Path) -> None:
    user = await admin(app)
    orphan = write(originals(library) / "cd" / "orphan.flac")

    result = await run(app, user, action=MaintenanceAction.REPORT)
    found = await findings(app, result.id)

    assert result.status == MaintenanceStatus.REPORTED
    assert found["orphan.flac"].outcome == FindingOutcome.LISTED
    assert orphan.exists()
    assert (result.listed_files, result.deleted_files) == (1, 0)


async def test_nothing_found_is_done(app: FastAPI, library: Path) -> None:
    user = await admin(app)
    await add_original(app, write(originals(library) / "ab" / "kept.flac"))

    reported = await run(app, user, action=MaintenanceAction.REPORT)

    assert reported.status == MaintenanceStatus.DONE


async def test_grace_period_is_configurable(app: FastAPI, library: Path) -> None:
    user = await admin(app)
    two_hours = write(originals(library) / "cd" / "recent.flac", age_seconds=2 * 3600)

    result = await run(app, user, grace_hours=1)

    assert not two_hours.exists()
    assert result.deleted_files == 1


async def test_safety_limit_holds_and_confirmation_deletes(app: FastAPI, library: Path) -> None:
    user = await admin(app)
    store = originals(library)
    for index in range(20):
        await add_original(app, write(store / "ab" / f"kept-{index}.flac"))
    orphans = [write(store / "cd" / f"orphan-{index}.flac") for index in range(11)]

    held = await run(app, user)  # limit max(10, 1 % of 20) = 10 < 11
    async with app.state.sessionmaker() as session, session.begin():
        job_id = await maintenance.confirm(session, held.id, created_by=user)
    await run_to_end(app, job_id)
    confirmed = await latest(app)

    assert (held.status, held.safety_limit, held.managed_files) == (
        MaintenanceStatus.HELD,
        10,
        20,
    )
    assert held.listed_files == 11 and held.deleted_files == 0
    assert confirmed.id == held.id
    assert confirmed.status == MaintenanceStatus.DONE
    assert confirmed.deleted_files == 11
    assert not any(orphan.exists() for orphan in orphans)


async def test_small_library_and_limit_off(app: FastAPI, library: Path) -> None:
    user = await admin(app)
    store = originals(library)
    few = [write(store / "cd" / f"few-{index}.flac") for index in range(4)]
    small = await run(app, user)
    many = [write(store / "ef" / f"many-{index}.flac") for index in range(15)]
    off = await run(app, user, safety_share_percent=None)

    assert small.status == MaintenanceStatus.DONE and small.deleted_files == 4
    assert off.status == MaintenanceStatus.DONE and off.safety_limit is None
    assert off.deleted_files == 15
    assert not any(path.exists() for path in few + many)


async def test_file_referenced_meanwhile_is_kept(app: FastAPI, library: Path) -> None:
    user = await admin(app)
    orphan = write(originals(library) / "cd" / "late.flac")
    async with app.state.sessionmaker() as session, session.begin():
        job_id = await maintenance.start(
            session,
            options=MaintenanceOptions(),
            created_by=user,
            trigger=MaintenanceTrigger.MANUAL,
        )

    handler = app.state.job_handlers.get(maintenance.JOB_TYPE)
    params = {"run_id": str((await latest(app)).id)}
    await handler.run_item(context(job_id, params, 0))
    await handler.run_item(context(job_id, params, 1))
    await add_original(app, orphan)  # an import registered it after the walk
    await handler.run_item(context(job_id, params, 2))
    result = await latest(app)
    found = await findings(app, result.id)

    assert found["late.flac"].outcome == FindingOutcome.REFERENCED
    assert orphan.exists()
    assert result.listed_files == 1 and result.deleted_files == 0


async def test_interrupted_items_run_again_without_duplicates(app: FastAPI, library: Path) -> None:
    user = await admin(app)
    store = originals(library)
    write(store / "cd" / "orphan.flac")
    await add_original(app, store / "01" / "missing.flac")
    async with app.state.sessionmaker() as session, session.begin():
        job_id = await maintenance.start(
            session,
            options=MaintenanceOptions(),
            created_by=user,
            trigger=MaintenanceTrigger.MANUAL,
        )

    handler = app.state.job_handlers.get(maintenance.JOB_TYPE)
    params = {"run_id": str((await latest(app)).id)}
    for position in (0, 0, 1, 1, 2, 2):  # every item repeated, as after a crash
        await handler.run_item(context(job_id, params, position))
    result = await latest(app)
    async with app.state.sessionmaker() as session:
        count = await session.scalar(
            select(func.count())
            .select_from(MaintenanceFinding)
            .where(MaintenanceFinding.run_id == result.id)
        )

    assert count == 2
    assert result.orphan_files == 1 and result.missing_files == 1
    assert result.deleted_files == 1


async def test_unavailable_storage_fails_without_deleting(
    app: FastAPI, library: Path, tmp_path: Path
) -> None:
    user = await admin(app)
    await add_original(app, originals(library) / "ab" / "gone.flac")  # no _originals folder

    result = await run(app, user)

    assert result.status == MaintenanceStatus.FAILED
    assert result.error.startswith("storage_unavailable")
    assert result.deleted_files == 0


async def test_empty_installation_is_done(app: FastAPI) -> None:
    result = await run(app, await admin(app))

    assert result.status == MaintenanceStatus.DONE


async def test_delete_orphans_refuses_entries_and_paths_outside(
    app: FastAPI, library: Path, tmp_path: Path
) -> None:
    store = originals(library)
    entry = write(store / "ab" / "entry.flac")
    await add_original(app, entry)
    outside = write(tmp_path / "elsewhere.flac")
    link = store / "cd" / "link.flac"
    link.parent.mkdir(parents=True)
    link.symlink_to(outside)
    async with app.state.sessionmaker() as session:
        outcomes = await maintenance.delete_orphans(
            session, library, [str(entry), str(outside), str(link)], grace_hours=24
        )

    assert outcomes[str(entry)][0] == FindingOutcome.REFERENCED
    assert outcomes[str(outside)][0] == FindingOutcome.OUTSIDE
    assert outcomes[str(link)][0] == FindingOutcome.OUTSIDE
    assert entry.exists() and outside.exists() and link.is_symlink()


async def test_old_runs_are_pruned(app: FastAPI) -> None:
    user = await admin(app)
    for _ in range(maintenance.KEEP_RUNS + 2):
        await run(app, user)
    async with app.state.sessionmaker() as session:
        count = await session.scalar(select(func.count()).select_from(MaintenanceRun))

    assert count == maintenance.KEEP_RUNS


# --- API ---------------------------------------------------------------------------------------


async def test_run_and_confirm_api(app: FastAPI, library: Path) -> None:
    async with client_for(app) as client:
        owner = await setup_admin(client)
        await create_user(client, owner, "editor", role="editor")
        editor = await login(client, "editor")
        refused = await client.post("/api/v1/maintenance/runs", headers=editor.headers)
        started = await client.post("/api/v1/maintenance/runs", headers=owner.headers)
        again = await client.post("/api/v1/maintenance/runs", headers=owner.headers)
        running = await latest(app)
        not_held = await client.post(
            f"/api/v1/maintenance/runs/{running.id}/confirm", headers=owner.headers
        )
        await run_job(app, uuid.UUID(started.json()["job_id"]))
        unknown = await client.post(
            f"/api/v1/maintenance/runs/{uuid.uuid4()}/confirm", headers=owner.headers
        )
        editor_confirm = await client.post(
            f"/api/v1/maintenance/runs/{running.id}/confirm", headers=editor.headers
        )

    assert refused.status_code == 403
    assert started.status_code == 202 and started.json()["job_id"]
    assert again.status_code == 409 and again.json()["detail"] == "maintenance_running"
    assert running.trigger == MaintenanceTrigger.MANUAL
    assert not_held.status_code == 409 and not_held.json()["detail"] == "not_held"
    assert unknown.status_code == 404
    assert editor_confirm.status_code == 403


async def test_scheduled_run_uses_the_stored_options(app: FastAPI) -> None:
    user = await admin(app)
    zone = ZoneInfo("UTC")
    async with app.state.sessionmaker() as session, session.begin():
        await schedules.update_schedule(
            session,
            maintenance.SCHEDULE,
            schedules.ScheduleConfig(True, ScheduleFrequency.DAILY, clock_time(3)),
            MaintenanceOptions(action=MaintenanceAction.REPORT, grace_hours=6),
            zone=zone,
            updated_by=user,
            now=datetime(2026, 10, 23, 12, tzinfo=UTC),
        )
    scheduler = schedules.Scheduler(
        app.state.sessionmaker,
        app.state.schedules,
        zone,
        clock=lambda: datetime(2026, 10, 24, 3, 0, 5, tzinfo=UTC),
    )
    [job_id] = await scheduler.run_once()
    await run_to_end(app, job_id)
    result = await latest(app)

    assert result.trigger == MaintenanceTrigger.SCHEDULE
    assert (result.action, result.grace_hours) == (MaintenanceAction.REPORT, 6)
    assert result.job_id == job_id


# --- streams (spec: library, Maintenance result) -------------------------------------------------


async def test_streams_snapshot_paging_and_delta(
    settings: Settings, tmp_path: Path, library: Path
) -> None:
    store = originals(library)
    for name in ("a.flac", "b.flac", "c.flac"):
        write(store / "cd" / name)
    async with (
        import_app(settings, tmp_path / "imports", library, background_tasks=True) as app,
        client_for(app) as client,
    ):
        owner = await setup_admin(client)
        await create_user(client, owner, "editor", role="editor")
        editor = await login(client, "editor")
        async with ws_connect(app) as ws:
            await ws.hello(owner.access_token)
            empty = await ws.subscribe("r", "library.maintenance")
            await client.post("/api/v1/maintenance/runs", headers=owner.headers)
            while True:  # the runner works through the job; the run's row follows live
                delta = (await ws.recv_type("delta", "r"))["data"]
                if delta.get("row", {}).get("status") == "done":
                    break
            run_id = delta["id"]
            meta = await ws.subscribe("f", "library.maintenance.findings", end=2, run_id=run_id)
            first = await ws.rows("f", 2)
            await ws.subscribe("g", "library.maintenance.findings", start=2, end=3, run_id=run_id)
            rest = await ws.rows("g", 1)
            runs = await ws.subscribe("s", "library.maintenance")
            [row] = await ws.rows("s", 1)
        async with ws_connect(app) as ws:
            await ws.hello(editor.access_token)
            await ws.send("subscribe", "e", stream="library.maintenance", start=0, end=10)
            refused = await ws.recv_type("error")

    assert empty["data"]["total"] == 0
    assert delta["row"]["deleted_files"] == 3
    assert meta["data"]["total"] == 3 and meta["data"]["counters"]["deleted_files"] == 3
    assert [Path(r["path"]).name for r in first + rest] == ["a.flac", "b.flac", "c.flac"]
    assert {r["outcome"] for r in first + rest} == {"deleted"}
    assert runs["data"]["total"] == 1
    assert (row["status"], row["trigger"], row["action"]) == ("done", "manual", "delete")
    assert refused["data"]["code"] == "forbidden"
