"""Recording identification (spec: library, Identification job and following). MusicBrainz and
AcoustID answers are recorded (generated); audio is generated sine tones."""

import json
import uuid
from datetime import timedelta
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy import delete, select, update

from anthology.core.config import Settings
from anthology.db.types import utcnow
from anthology.jobs.handlers import ItemContext
from anthology.library import identification, service
from anthology.library.fingerprint import FingerprintError, compute
from anthology.library.identification import Identifier, by_fingerprint, by_isrc
from anthology.library.models import (
    IDENTIFICATION_COUNTERS,
    AudioFile,
    IdentificationStatus,
    Recording,
)
from anthology.library.seed import seed_library
from anthology.metadata_lookup.models import ExternalRef, LookupCache, LookupSchedule
from anthology.metadata_lookup.service import LookupService
from tests.library_helpers import assert_consistent, audio
from tests.lookup_helpers import FakeClock, FakeWeb, ok
from tests.media_helpers import require_ffmpeg, tone_wav
from tests.users_helpers import create_user, login, setup_admin
from tests.ws_helpers import ws_connect

pytestmark = pytest.mark.usefixtures("clean_db")

MB = "musicbrainz.org"
ACOUSTID = "api.acoustid.org"


def mb_recording(length_ms: int | None = 200_000) -> dict:
    return {"id": str(uuid.uuid4()), "title": "Eisfeld", "length": length_ms}


def acoustid_answer(score: float, *recording_ids: str) -> dict:
    return {
        "status": "ok",
        "results": [
            {
                "id": str(uuid.uuid4()),
                "score": score,
                "recordings": [{"id": recording_id} for recording_id in recording_ids],
            }
        ],
    }


@pytest.fixture
async def quiet_app(settings: Settings, engine):
    """An app without background tasks: the job runner must not run the items under test."""
    from anthology.api.app import create_app

    app = create_app(settings.model_copy(update={"background_tasks": False}))
    async with app.router.lifespan_context(app):
        yield app


@pytest.fixture
def web() -> FakeWeb:
    return FakeWeb(FakeClock())


@pytest.fixture
async def lookups(app: FastAPI, settings: Settings, web: FakeWeb):
    async with app.state.sessionmaker() as session, session.begin():
        await session.execute(delete(LookupCache))
        await session.execute(update(LookupSchedule).values(next_slot_at=web.clock()))
    service_ = LookupService(
        settings.model_copy(update={"acoustid_api_key": "app-key"}),
        app.state.sessionmaker,
        transport=httpx.MockTransport(web.handler),
        clock=web.clock,
        sleep=web.clock.sleep,
    )
    yield service_
    await service_.aclose()


def identifier(app: FastAPI, settings: Settings, lookups: LookupService, **overrides) -> Identifier:
    return Identifier(app.state.sessionmaker, lookups, settings.model_copy(update=overrides))


async def one_recording(
    app: FastAPI,
    *,
    isrc: str | None = None,
    path: str | None = None,
    fingerprint: str | None = None,
    title: str = "Eisfeld",
) -> uuid.UUID:
    async with app.state.sessionmaker() as session, session.begin():
        artist = await service.get_or_create_artist(session, "Nordlicht")
        release = await service.create_release(session, title="Polarnacht", album_artist=artist)
        track = await service.add_recording(
            session,
            release=release,
            title=title,
            artist=artist,
            duration_ms=200_000,
            track_number=1,
            audio=audio(path),
            isrc=isrc,
        )
        if fingerprint is not None:
            original = await service.active_original(session, track.recording_id)
            await service.store_fingerprint(session, original, fingerprint, 200)
        return track.recording_id


async def recording(app: FastAPI, recording_id: uuid.UUID) -> Recording:
    async with app.state.sessionmaker() as session:
        return await session.get_one(Recording, recording_id)


# --- fingerprints -----------------------------------------------------------------------------


async def test_same_audio_gives_the_same_fingerprint(tmp_path: Path) -> None:
    require_ffmpeg()
    first = await compute(str(tone_wav(tmp_path / "a.wav", [440, 550, 660])))
    again = await compute(str(tone_wav(tmp_path / "b.wav", [440, 550, 660])))
    other = await compute(str(tone_wav(tmp_path / "c.wav", [300, 900, 1200, 500])))

    assert first.fingerprint == again.fingerprint
    assert first.fingerprint != other.fingerprint
    assert first.duration_s == 20


async def test_missing_or_broken_files_cannot_be_fingerprinted(tmp_path: Path) -> None:
    require_ffmpeg()
    broken = tmp_path / "broken.flac"
    broken.write_bytes(b"not audio at all")

    with pytest.raises(FingerprintError) as missing:
        await compute(str(tmp_path / "gone.flac"))
    with pytest.raises(FingerprintError) as failed:
        await compute(str(broken))

    assert missing.value.reason == "file_missing"
    assert failed.value.reason == "fingerprint_failed"


async def test_fingerprint_is_computed_once(
    app: FastAPI, settings: Settings, lookups: LookupService, web: FakeWeb, tmp_path: Path
) -> None:
    require_ffmpeg()
    path = tone_wav(tmp_path / "Eisfeld.wav", [440, 550, 660])
    recording_id = await one_recording(app, path=str(path))
    web.answer(ACOUSTID, "/v2/lookup", ok({"status": "ok", "results": []}))

    await identifier(app, settings, lookups).identify(recording_id)
    async with app.state.sessionmaker() as session:
        stored = (await service.active_original(session, recording_id)).fingerprint
        await session.execute(
            update(Recording).values(identification_checked_at=None)
        )  # check again
    # A second run cannot start FFmpeg and still uses the stored fingerprint.
    status = await identifier(app, settings, lookups, ffmpeg_path="/nonexistent/ffmpeg").identify(
        recording_id
    )

    assert stored
    assert status == IdentificationStatus.NO_MATCH
    sent = [request for _, request in web.requests if request.url.host == ACOUSTID]
    assert len(sent) == 1  # the second lookup came from the cache with the same fingerprint


# --- decision rules ---------------------------------------------------------------------------


def test_isrc_rules() -> None:
    single = mb_recording()
    near, far = mb_recording(201_500), mb_recording(260_000)

    assert by_isrc({"recordings": [single]}, 200_000) == uuid.UUID(single["id"])
    assert by_isrc({"recordings": [near, far]}, 200_000) == uuid.UUID(near["id"])
    assert by_isrc({"recordings": [far, mb_recording(260_500)]}, 200_000) is None
    assert by_isrc({"recordings": [near, mb_recording(199_000)]}, 200_000) is None
    assert by_isrc(None, 200_000) is None


def test_fingerprint_rules() -> None:
    mbid = str(uuid.uuid4())
    assert by_fingerprint(acoustid_answer(0.95, mbid))[0] == uuid.UUID(mbid)
    assert by_fingerprint(acoustid_answer(0.85, mbid)) is None
    assert by_fingerprint(acoustid_answer(0.99, mbid, str(uuid.uuid4()))) is None
    assert by_fingerprint({"status": "ok", "results": []}) is None


async def test_identified_by_isrc_without_fingerprint(
    app: FastAPI, settings: Settings, lookups: LookupService, web: FakeWeb
) -> None:
    match = mb_recording()
    web.answer(MB, "/ws/2/isrc/XXA012600001", ok({"recordings": [match]}))
    recording_id = await one_recording(app, isrc="XXA012600001", title="Eisfeld (Remaster)")

    status = await identifier(app, settings, lookups).identify(recording_id)

    identified = await recording(app, recording_id)
    assert status == IdentificationStatus.ISRC
    assert identified.mb_recording_id == uuid.UUID(match["id"])
    assert identified.title == "Eisfeld (Remaster)"  # identifiers only
    assert identified.identification_checked_at is not None
    assert {request.url.host for _, request in web.requests} == {MB}
    async with app.state.sessionmaker() as session:
        original = await service.active_original(session, recording_id)
        assert original.fingerprint is None
        ref = await session.scalar(select(ExternalRef).where(ExternalRef.entity_id == recording_id))
        assert ref is not None and ref.mbid == uuid.UUID(match["id"])
        await assert_consistent(session)


async def test_ambiguous_isrc_falls_back_to_the_fingerprint(
    app: FastAPI, settings: Settings, lookups: LookupService, web: FakeWeb
) -> None:
    mbid = str(uuid.uuid4())
    web.answer(
        MB,
        "/ws/2/isrc/XXA012600002",
        ok({"recordings": [mb_recording(150_000), mb_recording(260_000)]}),
    )
    web.answer(ACOUSTID, "/v2/lookup", ok(acoustid_answer(0.95, mbid)))
    recording_id = await one_recording(app, isrc="XXA012600002", fingerprint="AQAAstored")

    status = await identifier(app, settings, lookups).identify(recording_id)

    identified = await recording(app, recording_id)
    assert status == IdentificationStatus.FINGERPRINT
    assert identified.mb_recording_id == uuid.UUID(mbid)
    assert identified.acoust_id is not None


@pytest.mark.parametrize(
    ("answer", "status"),
    [
        (acoustid_answer(0.6, str(uuid.uuid4())), IdentificationStatus.NO_MATCH),
        ({"status": "ok", "results": []}, IdentificationStatus.NO_MATCH),
    ],
)
async def test_weak_fingerprint_results_are_no_match(
    app: FastAPI,
    settings: Settings,
    lookups: LookupService,
    web: FakeWeb,
    answer: dict,
    status: IdentificationStatus,
) -> None:
    web.answer(ACOUSTID, "/v2/lookup", ok(answer))
    recording_id = await one_recording(app, fingerprint="AQAAstored")

    assert await identifier(app, settings, lookups).identify(recording_id) == status
    assert (await recording(app, recording_id)).mb_recording_id is None


async def test_without_acoustid_key_identification_is_not_possible(
    app: FastAPI, settings: Settings, web: FakeWeb
) -> None:
    recording_id = await one_recording(app, fingerprint="AQAAstored")
    no_key = LookupService(
        settings.model_copy(update={"acoustid_api_key": ""}),
        app.state.sessionmaker,
        transport=httpx.MockTransport(web.handler),
        clock=web.clock,
        sleep=web.clock.sleep,
    )

    status = await Identifier(app.state.sessionmaker, no_key, settings).identify(recording_id)

    checked = await recording(app, recording_id)
    assert status == IdentificationStatus.NOT_POSSIBLE
    assert checked.identification_note == "no_acoustid_key"
    assert web.requests == []
    await no_key.aclose()


async def test_missing_original_file_is_not_possible(
    app: FastAPI, settings: Settings, lookups: LookupService, tmp_path: Path
) -> None:
    recording_id = await one_recording(app, path=str(tmp_path / "gone.flac"))

    status = await identifier(app, settings, lookups).identify(recording_id)

    assert status == IdentificationStatus.NOT_POSSIBLE
    assert (await recording(app, recording_id)).identification_note == "file_missing"


async def test_identified_duplicates_stay_separate(
    app: FastAPI, settings: Settings, lookups: LookupService, web: FakeWeb
) -> None:
    match = mb_recording()
    web.answer(MB, "/ws/2/isrc/XXA012600003", ok({"recordings": [match]}))
    first = await one_recording(app, isrc="XXA012600003")
    second = await one_recording(app, isrc="XXA012600003")
    ident = identifier(app, settings, lookups)

    assert await ident.identify(first) == IdentificationStatus.ISRC
    assert await ident.identify(second) == IdentificationStatus.DUPLICATE

    kept, duplicate = await recording(app, first), await recording(app, second)
    assert kept.mb_recording_id == uuid.UUID(match["id"])
    assert duplicate.mb_recording_id is None
    assert duplicate.identification_duplicate_of_id == first
    async with app.state.sessionmaker() as session:
        await assert_consistent(session)
        counts = await service.counters(session, tuple(IDENTIFICATION_COUNTERS.values()))
    assert counts["identification_isrc"] == 1
    assert counts["identification_duplicate"] == 1
    assert counts["identification_unchecked"] == 0


# --- the job ----------------------------------------------------------------------------------


def _context(job_params: dict, position: int, *, stop: bool = False) -> ItemContext:
    async def write_progress(progress: float, message: str | None) -> None:
        return None

    async def check_cancelled() -> bool:
        return stop

    return ItemContext(
        job_id=uuid.uuid4(),
        item_id=uuid.uuid4(),
        position=position,
        title=f"item {position}",
        params=job_params,
        _write_progress=write_progress,
        _check_cancelled=check_cancelled,
    )


async def _job_params(app: FastAPI, job_id: uuid.UUID) -> dict:
    from anthology.jobs.models import Job

    async with app.state.sessionmaker() as session:
        job = await session.get_one(Job, job_id)
    return json.loads(job.params_json)


async def test_job_checks_due_recordings_in_batches(
    quiet_app: FastAPI, settings: Settings, web: FakeWeb, engine
) -> None:
    app = quiet_app
    async with AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as quiet_client:
        admin_id = uuid.UUID((await setup_admin(quiet_client)).user["id"])
    lookups = LookupService(
        settings.model_copy(update={"acoustid_api_key": "app-key"}),
        app.state.sessionmaker,
        transport=httpx.MockTransport(web.handler),
        clock=web.clock,
        sleep=web.clock.sleep,
    )
    await seed_library(engine, 600)  # generated: no ISRCs, no files
    async with app.state.sessionmaker() as session:
        total = len(list(await session.scalars(select(Recording.id))))
    handler = identification.IdentifyRecordingsHandler()
    handler.bind(identifier(app, settings, lookups))

    async with app.state.sessionmaker() as session, session.begin():
        job_id = await identification.start(session, created_by=admin_id)
    params = await _job_params(app, job_id)
    results = [
        await handler.run_item(_context(params, index)) for index in range(len(params["batches"]))
    ]
    # An item that runs again (e.g. after a takeover) finds nothing left to check.
    repeated = await handler.run_item(_context(params, 0))

    assert len(params["batches"]) == -(-total // identification.BATCH)
    assert sum(sum(result.result.values()) for result in results) == total
    assert repeated.result == {}
    async with app.state.sessionmaker() as session:
        counts = await service.counters(session, tuple(IDENTIFICATION_COUNTERS.values()))
        # Within 30 days nothing is due again.
        assert await identification._batches(session, utcnow() - identification.RETRY_AFTER) == []
    assert counts["identification_not_possible"] == total  # files of the generator do not exist
    assert counts["identification_unchecked"] == 0
    await lookups.aclose()


async def test_recordings_are_due_again_after_30_days(
    app: FastAPI, client: AsyncClient, settings: Settings, lookups: LookupService
) -> None:
    admin = await setup_admin(client)
    recording_id = await one_recording(app, path="/nonexistent/Eisfeld.flac")
    await identifier(app, settings, lookups).identify(recording_id)

    async with app.state.sessionmaker() as session, session.begin():
        assert await identification.start(session, created_by=uuid.UUID(admin.user["id"])) is None
        checked = await session.get_one(Recording, recording_id)
        checked.identification_checked_at -= timedelta(days=31)
    async with app.state.sessionmaker() as session, session.begin():
        assert (
            await identification.start(session, created_by=uuid.UUID(admin.user["id"])) is not None
        )


async def test_full_re_run_and_one_job_at_a_time(
    app: FastAPI, client: AsyncClient, settings: Settings, lookups: LookupService
) -> None:
    admin = await setup_admin(client)
    recording_id = await one_recording(app, path="/nonexistent/Eisfeld.flac")
    await identifier(app, settings, lookups).identify(recording_id)

    async with app.state.sessionmaker() as session, session.begin():
        job_id = await identification.start(
            session, created_by=uuid.UUID(admin.user["id"]), full=True
        )
    async with app.state.sessionmaker() as session:
        with pytest.raises(identification.IdentificationRunning):
            await identification.start(session, created_by=uuid.UUID(admin.user["id"]), full=True)

    assert job_id is not None


async def test_editors_start_identification_over_the_api_and_it_runs_to_the_end(
    app: FastAPI, client: AsyncClient
) -> None:
    admin = await setup_admin(client)
    await create_user(client, admin, "editor", role="editor")
    await create_user(client, admin, "kid")
    editor, kid = await login(client, "editor"), await login(client, "kid")
    await one_recording(app, path="/nonexistent/Eisfeld.flac")

    refused = await client.post("/api/v1/library/identification", headers=kid.headers, json={})
    started = await client.post("/api/v1/library/identification", headers=editor.headers, json={})
    again = await client.post("/api/v1/library/identification", headers=editor.headers, json={})
    job_id = started.json()["job_id"]
    for _ in range(100):
        job = (await client.get(f"/api/v1/jobs/{job_id}", headers=editor.headers)).json()
        if job["status"] == "done":
            break
        await _pause()

    assert refused.status_code == 403
    assert started.status_code == 202
    assert again.status_code == 409
    assert job["status"] == "done"


async def _pause() -> None:
    import asyncio

    await asyncio.sleep(0.1)


async def test_identification_counts_stream(
    app: FastAPI, client: AsyncClient, settings: Settings, lookups: LookupService
) -> None:
    admin = await setup_admin(client)
    recording_id = await one_recording(app, path="/nonexistent/Eisfeld.flac")

    async with ws_connect(app) as ws:
        await ws.hello(admin.access_token)
        meta = await ws.subscribe("i", "library.identification")
        [row] = await ws.rows("i", 1)
        await identifier(app, settings, lookups).identify(recording_id)
        while True:
            delta = (await ws.recv_type("delta", "i"))["data"]
            if delta["row"]["not_possible"] == 1:
                break

    assert meta["data"]["total"] == 1
    assert meta["data"]["counters"]["unchecked"] == 1
    assert row["unchecked"] == 1
    assert delta["row"]["unchecked"] == 0


async def test_stored_fingerprint_survives_on_the_file(app: FastAPI) -> None:
    recording_id = await one_recording(app, fingerprint="AQAAstored")
    async with app.state.sessionmaker() as session:
        original = await session.scalar(
            select(AudioFile).where(AudioFile.recording_id == recording_id)
        )
    assert (original.fingerprint, original.fingerprint_duration_s) == ("AQAAstored", 200)
