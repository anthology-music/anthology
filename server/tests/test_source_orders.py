"""Download orders against the fake source service, through the library import into the
library (spec: sources, Download orders, Downloads enter the library;
effective-quality-duplicate-checks 3.1/3.2)."""

import json
import uuid
from pathlib import Path

import httpx
import pytest
from anthology_fake_source.app import Settings as FakeSettings
from anthology_fake_source.app import create_app as fake_app
from fastapi import FastAPI
from sqlalchemy import select, update

from anthology.core.config import Settings
from anthology.jobs.models import ItemOutcome, Job, JobItem
from anthology.library.models import AudioFile, Recording
from anthology.library_import.models import ImportItem, ImportMode, ImportResult, LibraryImport
from anthology.library_import.models import ImportStatus as Status
from anthology.sources import orders
from anthology.sources.models import (
    DownloadOrder,
    DownloadOrderItem,
    OrderItemState,
    OrderStatus,
    Source,
    SourceService,
)
from anthology.sources.service import SourceServices
from tests.import_helpers import client_for, context, exists, import_app, make_dirs, settle
from tests.library_helpers import album
from tests.media_helpers import require_ffmpeg
from tests.test_sources import Swappable
from tests.users_helpers import setup_admin
from tests.ws_helpers import ws_connect

pytestmark = pytest.mark.usefixtures("clean_db")

FAKE = "http://fake.test"


async def connect(app: FastAPI, **fake_settings) -> tuple[SourceServices, Swappable]:
    transport = Swappable(fake_app(FakeSettings(delay=0.01, **fake_settings)))
    configured = app.state.settings.model_copy(update={"source_services": FAKE})
    services = SourceServices(app.state.sessionmaker, configured, {FAKE: transport}.get)
    app.state.sources = services
    app.state.job_handlers.get(orders.JOB_TYPE).bind(
        app.state.sessionmaker, services, app.state.settings
    )
    await services.register()
    await services.check_all()
    return services, transport


async def service_id(app: FastAPI) -> str:
    async with app.state.sessionmaker() as session:
        return str(await session.scalar(select(SourceService.id)))


async def run_order(app: FastAPI, job_id: uuid.UUID) -> DownloadOrder:
    """Run the download job's items, then the import it starts."""
    async with app.state.sessionmaker() as session:
        job = await session.get_one(Job, job_id)
    handler = app.state.job_handlers.get(job.type)
    params = json.loads(job.params_json)
    for position in range(job.total_items):
        await handler.run_item(context(job.id, params, position))
    async with app.state.sessionmaker() as session:
        order = await session.scalar(select(DownloadOrder).where(DownloadOrder.job_id == job_id))
    if order.import_id is not None:
        await settle(app, order.import_id)
    async with app.state.sessionmaker() as session:
        return await session.get_one(DownloadOrder, order.id, populate_existing=True)


async def order_items(app: FastAPI, order_id: uuid.UUID) -> list[DownloadOrderItem]:
    async with app.state.sessionmaker() as session:
        return list(
            await session.scalars(
                select(DownloadOrderItem)
                .where(DownloadOrderItem.order_id == order_id)
                .order_by(DownloadOrderItem.position)
            )
        )


async def test_an_album_order_enters_the_library(
    settings: Settings, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    require_ffmpeg()
    monkeypatch.setattr(orders, "POLL_SECONDS", 0.02)
    async with import_app(settings, tmp_path / "imports", tmp_path / "library") as app:
        async with client_for(app) as client:
            admin = await setup_admin(client)
            async with app.state.sessionmaker() as session, session.begin():
                # "Eisfeld" is present in CD quality: it is not downloaded.
                _release, [eisfeld] = await album(session, "Nordlicht", "Polarnacht", ["Eisfeld"])
                await session.execute(
                    update(Recording)
                    .where(Recording.id == eisfeld.recording_id)
                    .values(isrc="DEA012400001")
                )
            services, _ = await connect(app)
            started = await client.post(
                "/api/v1/sources/orders",
                headers=admin.headers,
                json={
                    "service": await service_id(app),
                    "ref": "album:1",
                    "tracks": ["track:101", "track:102", "track:103"],
                },
            )
            order = await run_order(app, uuid.UUID(started.json()["job_id"]))
            items = await order_items(app, order.id)
            async with app.state.sessionmaker() as session:
                library_import = await session.get_one(LibraryImport, order.import_id)
                downloaded = list(
                    await session.execute(
                        select(Recording.title, Source.kind, Source.external_id, AudioFile.path)
                        .join(AudioFile, AudioFile.recording_id == Recording.id)
                        .join(Source, Source.id == AudioFile.source_id)
                        .order_by(Recording.title)
                    )
                )
                job_outcomes = list(
                    await session.scalars(
                        select(JobItem.outcome)
                        .where(JobItem.job_id == order.job_id)
                        .order_by(JobItem.position)
                    )
                )
            async with ws_connect(app) as ws:
                await ws.hello(admin.access_token)
                meta = await ws.subscribe("t", "library.tracks")
                rows = {row["title"]: row for row in await ws.rows("t", meta["data"]["total"])}
            await services.stop()

    # Spec: Source shown.
    assert rows["Treibeis"]["source"] == "Fake" and rows["Treibeis"]["source_short"] == "FK"
    assert rows["Treibeis"]["retrieved_at"] and rows["Eisfeld"]["source"] is None
    assert started.status_code == 202
    assert started.json()["items"] == 3 and started.json()["already_present"] == 1
    assert order.status == OrderStatus.DONE
    assert library_import.mode == ImportMode.MOVE and library_import.confirm_automatically
    assert library_import.status == Status.DONE
    assert [(item.title, item.state, item.outcome) for item in items] == [
        ("Eisfeld", OrderItemState.SKIPPED, ItemOutcome.ALREADY_PRESENT),
        ("Treibeis", OrderItemState.DONE, ItemOutcome.NEW),
        ("Driftlinie", OrderItemState.DONE, ItemOutcome.NEW),
    ]
    assert [(title, kind, ref) for title, kind, ref, _path in downloaded] == [
        ("Driftlinie", "fake", "track:103"),
        ("Treibeis", "fake", "track:102"),
    ]
    # Managed originals now; the download folder is empty and gone.
    assert all("/_originals/" in path for *_rest, path in downloaded)
    assert not exists(order.folder)
    assert job_outcomes == [None, ItemOutcome.NEW, ItemOutcome.NEW]


def write(path: Path, data: bytes) -> None:
    path.write_bytes(data)


def names(folder: Path) -> list[str]:
    return sorted(path.name for path in folder.iterdir())


async def _order_with_items(app: FastAPI, admin_id: uuid.UUID, folder: Path, states: list[str]):
    """An order whose items are downloaded files ``<n>.flac`` in ``folder``."""
    make_dirs(folder)
    async with app.state.sessionmaker() as session, session.begin():
        order = DownloadOrder(
            service_url=FAKE,
            service_name="Fake",
            source="fake",
            short="FK",
            title="Polarnacht",
            quality="best",
            status=OrderStatus.IMPORTING,
            folder=str(folder),
            created_by=admin_id,
        )
        session.add(order)
        await session.flush()
        for position, _state in enumerate(states):
            write(folder / f"{position}.flac", b"fLaC")
            session.add(
                DownloadOrderItem(
                    order_id=order.id,
                    position=position,
                    ref=f"track:{position}",
                    title=f"Titel {position}",
                    duplicate="new",
                    state=OrderItemState.DOWNLOADED,
                    progress=1.0,
                    file=f"{position}.flac",
                )
            )
        return order.id


async def test_import_results_become_item_outcomes(app: FastAPI, client, tmp_path: Path) -> None:
    admin = await setup_admin(client)
    results = [
        ImportResult.NEW,
        ImportResult.REPLACES_LOWER_QUALITY,
        ImportResult.ALREADY_PRESENT,
        ImportResult.SUSPICIOUS_QUALITY,
        ImportResult.BROKEN,
    ]
    folder = tmp_path / "anthology-downloads" / "order"
    order_id = await _order_with_items(
        app, uuid.UUID(admin.user["id"]), folder, [result.value for result in results]
    )
    async with app.state.sessionmaker() as session, session.begin():
        _release, tracks = await album(session, "Nordlicht", "Polarnacht", ["A", "B"])
        originals = list(
            await session.scalars(
                select(AudioFile.id).where(
                    AudioFile.recording_id.in_([track.recording_id for track in tracks])
                )
            )
        )
        library_import = LibraryImport(
            source_path=str(folder),
            root=str(tmp_path),
            mode=ImportMode.MOVE,
            status=Status.IMPORTING,
            created_by=uuid.UUID(admin.user["id"]),
            confirm_automatically=True,
        )
        session.add(library_import)
        await session.flush()
        for position, result in enumerate(results):
            session.add(
                ImportItem(
                    import_id=library_import.id,
                    path=str(folder / f"{position}.flac"),
                    size_bytes=4,
                    mtime_ns=0,
                    result=result,
                    audio_file_id=originals[position] if position < 2 else None,
                )
            )
        await session.execute(
            update(DownloadOrder)
            .where(DownloadOrder.id == order_id)
            .values(import_id=library_import.id)
        )
    async with app.state.sessionmaker() as session, session.begin():
        row = await session.get_one(LibraryImport, library_import.id)
        row.status = Status.DONE
        await orders.import_ended(session, row)
    items = await order_items(app, order_id)
    async with app.state.sessionmaker() as session:
        sources = list(
            await session.scalars(select(AudioFile.source_id).where(AudioFile.id.in_(originals)))
        )
        order = await session.get_one(DownloadOrder, order_id)

    assert [item.outcome for item in items] == [
        ItemOutcome.NEW,
        ItemOutcome.REPLACED,
        ItemOutcome.NOT_BETTER_THAN_EXISTING,
        ItemOutcome.NEEDS_REVIEW,
        ItemOutcome.FAILED,
    ]
    assert all(source is not None for source in sources)
    # Not better and broken files are removed; the file waiting for a review decision stays.
    assert names(folder) == ["0.flac", "1.flac", "3.flac"]
    assert order.status == OrderStatus.DONE and order.finished_at is not None


async def test_rate_limited_orders_wait_and_lost_tasks_are_requested_again(
    settings: Settings, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    require_ffmpeg()
    monkeypatch.setattr(orders, "POLL_SECONDS", 0.02)
    async with import_app(settings, tmp_path / "imports", tmp_path / "library") as app:
        async with client_for(app) as client:
            admin = await setup_admin(client)
            services, transport = await connect(app)
            started = await client.post(
                "/api/v1/sources/orders",
                headers=admin.headers,
                json={
                    "service": await service_id(app),
                    "ref": "album:2",
                    "tracks": ["track:201", "track:202"],
                },
            )
            job_id = uuid.UUID(started.json()["job_id"])
            # The service forgets the task (a restart) and is rate-limited for a moment.
            async with app.state.sessionmaker() as session, session.begin():
                await session.execute(
                    update(DownloadOrder)
                    .where(DownloadOrder.job_id == job_id)
                    .values(task_id="lost")
                )
            await transport.handle_async_request(
                httpx.Request("POST", f"{FAKE}/test/rate-limit", json={"seconds": 0.3})
            )
            reports: list[str | None] = []
            async with app.state.sessionmaker() as session:
                job = await session.get_one(Job, job_id)
            handler = app.state.job_handlers.get(job.type)
            params = json.loads(job.params_json)
            for position in range(job.total_items):
                ctx = context(job.id, params, position)

                async def report(progress, message, _reports=reports):
                    _reports.append(message)

                ctx._write_progress = report
                ctx._last_report = -1e9
                await handler.run_item(ctx)
            async with app.state.sessionmaker() as session:
                order = await session.scalar(
                    select(DownloadOrder).where(DownloadOrder.job_id == job_id)
                )
            await settle(app, order.import_id)
            items = await order_items(app, order.id)
            await services.stop()

    assert any(message and message.startswith("waiting until") for message in reports)
    assert order.task_id not in (None, "lost")
    assert [item.outcome for item in items] == [ItemOutcome.NEW, ItemOutcome.NEW]


async def test_orders_need_an_available_service_and_known_tracks(app: FastAPI, client) -> None:
    admin = await setup_admin(client)
    services, _ = await connect(app)
    sid = await service_id(app)

    unknown = await client.post(
        "/api/v1/sources/orders",
        headers=admin.headers,
        json={"service": sid, "ref": "album:1", "tracks": ["track:999"]},
    )
    async with app.state.sessionmaker() as session, session.begin():
        await session.execute(update(SourceService).values(available=False))
    unavailable = await client.post(
        "/api/v1/sources/orders",
        headers=admin.headers,
        json={"service": sid, "ref": "album:1", "tracks": ["track:101"]},
    )

    assert unknown.status_code == 422
    assert unavailable.status_code == 409
    await services.stop()
