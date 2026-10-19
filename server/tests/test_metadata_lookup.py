"""Metadata lookups (spec: metadata-lookup). External services are replaced by recorded
(generated) responses; time runs on a fake clock."""

import asyncio
import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy import delete, update

from anthology import __version__
from anthology.core.config import Settings
from anthology.core.services import ServiceState
from anthology.metadata_lookup.models import LookupCache, LookupSchedule
from anthology.metadata_lookup.service import (
    LookupFailed,
    LookupNotConfigured,
    LookupService,
    Priority,
    Turns,
    check_mirror,
    estimate_seconds,
    recommend_mirror,
)
from tests.users_helpers import create_user, login, setup_admin

pytestmark = pytest.mark.usefixtures("clean_db")

START = datetime(2026, 10, 19, 12, 0, tzinfo=UTC)
MIRROR = "http://musicbrainz.mirror.test:5000"


class FakeClock:
    def __init__(self) -> None:
        self.now = START

    def __call__(self) -> datetime:
        return self.now

    async def sleep(self, seconds: float) -> None:
        self.now += timedelta(seconds=seconds)
        await asyncio.sleep(0)

    def elapsed(self, at: datetime) -> float:
        return (at - START).total_seconds()


class FakeWeb:
    """Recorded answers by host and path; every request is logged with the fake time."""

    def __init__(self, clock: FakeClock) -> None:
        self.clock = clock
        self.requests: list[tuple[float, httpx.Request]] = []
        self.answers: dict[tuple[str, str], list[Callable[[httpx.Request], httpx.Response]]] = {}

    def answer(self, host: str, path: str, *responses: Callable[[httpx.Request], httpx.Response]):
        self.answers[(host, path)] = list(responses)

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append((self.clock.elapsed(self.clock.now), request))
        queue = self.answers.get((request.url.host, request.url.path))
        if not queue:
            return httpx.Response(404, json={"error": "Not Found"})
        respond = queue.pop(0) if len(queue) > 1 else queue[0]
        return respond(request)

    def hosts(self) -> list[str]:
        return [request.url.host for _, request in self.requests]


def ok(body: dict) -> Callable[[httpx.Request], httpx.Response]:
    return lambda _request: httpx.Response(200, json=body)


def status(code: int, **headers: str) -> Callable[[httpx.Request], httpx.Response]:
    return lambda _request: httpx.Response(code, headers=headers, json={"error": "busy"})


def fail(_request: httpx.Request) -> httpx.Response:
    raise httpx.ConnectError("connection refused")


def release(mbid: str, title: str = "Polarnacht") -> dict:
    """A generated release in the shape of the MusicBrainz JSON API (fictional data)."""
    return {"id": mbid, "title": title, "media": [{"tracks": [{"title": "Eisfeld"}]}]}


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def web(clock: FakeClock) -> FakeWeb:
    return FakeWeb(clock)


def lookups(
    app: FastAPI,
    settings: Settings,
    clock: FakeClock,
    web: FakeWeb,
    *,
    mirror_state: Callable[[], ServiceState | None] = lambda: None,
    on_mirror_failure: Callable[[], None] = lambda: None,
    **overrides,
) -> LookupService:
    return LookupService(
        settings.model_copy(update=overrides),
        app.state.sessionmaker,
        transport=httpx.MockTransport(web.handler),
        clock=clock,
        sleep=clock.sleep,
        mirror_state=mirror_state,
        on_mirror_failure=on_mirror_failure,
    )


@pytest.fixture
async def reset_schedule(app: FastAPI) -> None:
    async with app.state.sessionmaker() as session, session.begin():
        await session.execute(delete(LookupCache))
        await session.execute(
            update(LookupSchedule).values(next_slot_at=datetime(2000, 1, 1, tzinfo=UTC))
        )


pytestmark = [pytest.mark.usefixtures("clean_db", "reset_schedule")]


# --- respectful use -----------------------------------------------------------------------------


async def test_musicbrainz_gets_one_request_per_second_across_processes(
    app: FastAPI, settings: Settings, clock: FakeClock, web: FakeWeb
) -> None:
    ids = [str(uuid.uuid4()) for _ in range(4)]
    for mbid in ids:
        web.answer("musicbrainz.org", f"/ws/2/release/{mbid}", ok(release(mbid)))
    # Two lookup services stand for two server processes sharing the database.
    first = lookups(app, settings, clock, web)
    second = lookups(app, settings, clock, web)

    results = await asyncio.gather(
        first.musicbrainz.release(ids[0]),
        second.musicbrainz.release(ids[1]),
        first.musicbrainz.release(ids[2]),
        second.musicbrainz.release(ids[3]),
    )

    times = sorted(at for at, _ in web.requests)
    assert all(result.found and not result.cached for result in results)
    assert times == [0.0, 1.0, 2.0, 3.0]
    await first.aclose()
    await second.aclose()


async def test_acoustid_gets_three_requests_per_second_with_the_key(
    app: FastAPI, settings: Settings, clock: FakeClock, web: FakeWeb
) -> None:
    web.answer(
        "api.acoustid.org",
        "/v2/lookup",
        ok({"status": "ok", "results": [{"id": "x", "recordings": [{"id": "r"}]}]}),
    )
    service = lookups(app, settings, clock, web, acoustid_api_key="app-key")

    await asyncio.gather(*(service.acoustid.lookup(f"AQAD{n}", 200 + n) for n in range(4)))

    times = sorted(at for at, _ in web.requests)
    assert times == pytest.approx([0.0, 1 / 3, 2 / 3, 1.0], abs=1e-5)
    _, request = web.requests[0]
    assert request.method == "POST"
    assert b"client=app-key" in request.content
    await service.aclose()


async def test_acoustid_without_key_is_skipped(
    app: FastAPI, settings: Settings, clock: FakeClock, web: FakeWeb
) -> None:
    service = lookups(app, settings, clock, web, acoustid_api_key="")

    with pytest.raises(LookupNotConfigured):
        await service.acoustid.lookup("AQAD", 200)
    assert web.requests == []
    await service.aclose()


async def test_user_agent_names_version_and_contact(
    app: FastAPI, settings: Settings, clock: FakeClock, web: FakeWeb
) -> None:
    mbid = str(uuid.uuid4())
    web.answer("musicbrainz.org", f"/ws/2/release/{mbid}", ok(release(mbid)))
    service = lookups(app, settings, clock, web, musicbrainz_contact="admin@example.org")

    await service.musicbrainz.release(mbid)

    _, request = web.requests[0]
    assert request.headers["User-Agent"] == f"Anthology/{__version__} ( admin@example.org )"
    assert request.url.params["fmt"] == "json"
    await service.aclose()


async def test_overload_waits_and_retries_instead_of_failing(
    app: FastAPI, settings: Settings, clock: FakeClock, web: FakeWeb
) -> None:
    mbid = str(uuid.uuid4())
    web.answer(
        "musicbrainz.org",
        f"/ws/2/release/{mbid}",
        status(503),
        status(503, **{"Retry-After": "10"}),
        ok(release(mbid)),
    )
    service = lookups(app, settings, clock, web)

    result = await service.musicbrainz.release(mbid)

    assert result.found
    # 1st try at 0 s; back-off 2 s -> 2nd try at 2 s; Retry-After 10 s -> 3rd try at 12 s.
    assert [at for at, _ in web.requests] == [0.0, 2.0, 12.0]
    async with app.state.sessionmaker() as session:
        schedule = await session.get_one(LookupSchedule, "musicbrainz")
    assert schedule.next_slot_at == START + timedelta(seconds=13)  # shared with all processes
    await service.aclose()


async def test_repeated_failures_fail_the_lookup(
    app: FastAPI, settings: Settings, clock: FakeClock, web: FakeWeb
) -> None:
    mbid = str(uuid.uuid4())
    web.answer("musicbrainz.org", f"/ws/2/release/{mbid}", status(500))
    service = lookups(app, settings, clock, web)

    with pytest.raises(LookupFailed):
        await service.musicbrainz.release(mbid)
    assert len(web.requests) == 3
    await service.aclose()


# --- cache ----------------------------------------------------------------------------------


async def test_repeated_lookups_are_answered_from_the_cache(
    app: FastAPI, settings: Settings, clock: FakeClock, web: FakeWeb
) -> None:
    mbid = str(uuid.uuid4())
    web.answer("musicbrainz.org", f"/ws/2/release/{mbid}", ok(release(mbid)))
    service = lookups(app, settings, clock, web)

    first = await service.musicbrainz.release(mbid)
    clock.now += timedelta(days=7)  # re-import a week later
    again = await lookups(app, settings, clock, web).musicbrainz.release(mbid)

    assert (first.cached, again.cached) == (False, True)
    assert again.data == release(mbid)
    assert len(web.requests) == 1

    clock.now += timedelta(days=24)  # entities expire after 30 days
    await service.musicbrainz.release(mbid)
    assert len(web.requests) == 2
    await service.aclose()


async def test_not_found_is_cached_for_a_day(
    app: FastAPI, settings: Settings, clock: FakeClock, web: FakeWeb
) -> None:
    service = lookups(app, settings, clock, web)

    missing = await service.musicbrainz.isrc("XXA012600001")
    again = await service.musicbrainz.isrc("XXA012600001")
    clock.now += timedelta(days=1, seconds=1)
    await service.musicbrainz.isrc("XXA012600001")

    assert (missing.found, again.found, again.cached) == (False, False, True)
    assert len(web.requests) == 2
    await service.aclose()


# --- priority -------------------------------------------------------------------------------


class _GatedSchedule:
    """The first slot comes only when the test opens the gate; later ones right away."""

    def __init__(self) -> None:
        self.gate = asyncio.Event()
        self.calls = 0

    async def wait_for_slot(self, target: str) -> None:
        self.calls += 1
        if self.calls == 1:
            await self.gate.wait()


async def test_interactive_lookups_take_their_turn_first() -> None:
    schedule = _GatedSchedule()
    turns = Turns("musicbrainz", schedule)  # type: ignore[arg-type]
    order: list[str] = []

    async def take(name: str, priority: Priority) -> None:
        await turns.turn(priority)
        order.append(name)

    # A large import has queued its lookups; the first one waits for its slot.
    background = [asyncio.create_task(take(f"bg{n}", Priority.BACKGROUND)) for n in range(5)]
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    assert turns.pending == 4  # bg0 has its turn and waits for the slot
    # A user inserts a CD: the disc ID lookup is performed next.
    disc = asyncio.create_task(take("disc id", Priority.INTERACTIVE))
    await asyncio.sleep(0)
    schedule.gate.set()
    await asyncio.gather(*background, disc)

    assert order == ["bg0", "disc id", "bg1", "bg2", "bg3", "bg4"]


# --- mirror ---------------------------------------------------------------------------------


async def test_mirror_is_used_without_rate_limit(
    app: FastAPI, settings: Settings, clock: FakeClock, web: FakeWeb
) -> None:
    ids = [str(uuid.uuid4()) for _ in range(5)]
    for mbid in ids:
        web.answer("musicbrainz.mirror.test", f"/ws/2/release/{mbid}", ok(release(mbid)))
    service = lookups(
        app,
        settings,
        clock,
        web,
        musicbrainz_url=MIRROR,
        mirror_state=lambda: ServiceState.AVAILABLE,
    )

    await asyncio.gather(*(service.musicbrainz.release(mbid) for mbid in ids))

    assert set(web.hosts()) == {"musicbrainz.mirror.test"}
    assert [at for at, _ in web.requests] == [0.0] * 5
    await service.aclose()


async def test_unavailable_mirror_falls_back_to_the_public_api(
    app: FastAPI, settings: Settings, clock: FakeClock, web: FakeWeb
) -> None:
    mbid = str(uuid.uuid4())
    web.answer("musicbrainz.org", f"/ws/2/release/{mbid}", ok(release(mbid)))
    service = lookups(
        app,
        settings,
        clock,
        web,
        musicbrainz_url=MIRROR,
        mirror_state=lambda: ServiceState.UNAVAILABLE,
    )

    result = await service.musicbrainz.release(mbid)

    assert result.found
    assert web.hosts() == ["musicbrainz.org"]
    await service.aclose()


async def test_failing_mirror_falls_back_and_asks_for_a_check(
    app: FastAPI, settings: Settings, clock: FakeClock, web: FakeWeb
) -> None:
    mbid = str(uuid.uuid4())
    web.answer("musicbrainz.mirror.test", f"/ws/2/release/{mbid}", fail)
    web.answer("musicbrainz.org", f"/ws/2/release/{mbid}", ok(release(mbid)))
    checks: list[str] = []
    service = lookups(
        app,
        settings,
        clock,
        web,
        musicbrainz_url=MIRROR,
        mirror_state=lambda: ServiceState.AVAILABLE,
        on_mirror_failure=lambda: checks.append("check"),
    )

    result = await service.musicbrainz.release(mbid)

    assert result.found
    assert web.hosts() == ["musicbrainz.mirror.test", "musicbrainz.org"]
    assert checks == ["check"]
    await service.aclose()


async def test_request_the_mirror_cannot_answer_goes_to_the_public_api(
    app: FastAPI, settings: Settings, clock: FakeClock, web: FakeWeb
) -> None:
    mbid = str(uuid.uuid4())
    # A text search on a mirror without search indexes fails; entity lookups work.
    web.answer("musicbrainz.mirror.test", "/ws/2/recording", status(503))
    web.answer("musicbrainz.org", "/ws/2/recording", ok({"recordings": []}))
    web.answer("musicbrainz.mirror.test", f"/ws/2/release/{mbid}", ok(release(mbid)))
    service = lookups(
        app,
        settings,
        clock,
        web,
        musicbrainz_url=MIRROR,
        mirror_state=lambda: ServiceState.AVAILABLE,
    )

    search = await service.musicbrainz.search_recordings('recording:"Eisfeld"')
    entity = await service.musicbrainz.release(mbid)

    assert search.found and entity.found
    assert web.hosts() == ["musicbrainz.mirror.test", "musicbrainz.org", "musicbrainz.mirror.test"]
    await service.aclose()


async def test_mirror_health_check(clock: FakeClock, web: FakeWeb) -> None:
    various_artists = "/ws/2/artist/89ad4ac3-39f7-470e-963a-56509c546377"
    web.answer("musicbrainz.mirror.test", various_artists, ok({"name": "Various Artists"}))
    async with httpx.AsyncClient(
        base_url=MIRROR, transport=httpx.MockTransport(web.handler)
    ) as http:
        up = await check_mirror(http)
        web.answer("musicbrainz.mirror.test", various_artists, fail)
        down = await check_mirror(http)

    assert up.status == ServiceState.AVAILABLE
    assert down.status == ServiceState.UNAVAILABLE


# --- estimate and recommendation --------------------------------------------------------------


def test_estimate_and_recommendation_threshold() -> None:
    day = 24 * 60 * 60
    assert estimate_seconds(200_000, 1.0) == 200_000
    assert recommend_mirror(200_000, mirror_available=False) is True
    assert recommend_mirror(day, mirror_available=False) is False
    assert recommend_mirror(day + 1, mirror_available=False) is True
    assert recommend_mirror(200_000, mirror_available=True) is False


async def test_status_recommends_a_mirror_for_a_large_import(
    app: FastAPI, settings: Settings, clock: FakeClock, web: FakeWeb
) -> None:
    service = lookups(app, settings, clock, web)
    queued = 200_000

    async def backlog() -> int:
        return queued

    service.register_backlog("library-import", backlog)
    large = await service.status()
    queued = 50_000
    small = await service.status()

    assert (large.queued, large.estimated_seconds, large.mirror_recommended) == (
        200_000,
        200_000,
        True,
    )
    assert small.mirror_recommended is False
    assert large.mirror_configured is False
    await service.aclose()


async def test_status_endpoint_is_for_admins(app: FastAPI, client: AsyncClient) -> None:
    admin = await setup_admin(client)
    await create_user(client, admin, "editor", role="editor")
    editor = await login(client, "editor")

    answer = await client.get("/api/v1/metadata-lookup/status", headers=admin.headers)
    refused = await client.get("/api/v1/metadata-lookup/status", headers=editor.headers)

    assert answer.status_code == 200
    assert answer.json() == {
        "mirror_configured": False,
        "mirror_status": None,
        "queued_requests": 0,
        "estimated_seconds": 0.0,
        "mirror_recommended": False,
    }
    assert refused.status_code == 403
