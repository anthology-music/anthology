"""Source services against the fake service (spec: sources; external-source-services 3.1;
effective-quality-duplicate-checks 3.1)."""

import asyncio

import httpx
import pytest
from anthology_fake_source.app import Settings as FakeSettings
from anthology_fake_source.app import create_app as fake_app
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy import select, update

from anthology.core.config import Settings
from anthology.library.models import AudioFile, QualityTier, Recording
from anthology.sources import api as sources_api
from anthology.sources.models import SourceCredential, SourceService
from anthology.sources.service import SourceServices
from tests.library_helpers import album
from tests.users_helpers import create_user, login, setup_admin
from tests.ws_helpers import ws_connect

pytestmark = pytest.mark.usefixtures("clean_db")

FAKE = "http://fake.test"
OTHER = "http://other.test"
OLD = "http://old.test"
CLOSED = "http://127.0.0.1:9"


class Swappable(httpx.AsyncBaseTransport):
    """An in-process transport whose app can be replaced (a restarted service) or slowed."""

    def __init__(self, app: FastAPI) -> None:
        self.app = app
        self.delay = 0.0

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        await asyncio.sleep(self.delay)
        return await httpx.ASGITransport(app=self.app).handle_async_request(request)


async def connect(
    app: FastAPI, settings: Settings, fakes: dict[str, FastAPI | None]
) -> tuple[SourceServices, dict[str, Swappable]]:
    """Source services for ``fakes`` (None: an unreachable URL), checked once."""
    transports = {url: Swappable(fake) for url, fake in fakes.items() if fake is not None}
    configured = settings.model_copy(update={"source_services": ",".join(fakes)})
    services = SourceServices(app.state.sessionmaker, configured, transports.get)
    app.state.sources = services
    await services.register()
    await services.check_all()
    return services, transports


def fake(**settings) -> FastAPI:
    return fake_app(FakeSettings(delay=0.01, **settings))


async def rows(app: FastAPI, token: str) -> list[dict]:
    async with ws_connect(app) as ws:
        await ws.hello(token)
        meta = await ws.subscribe("s", "sources.services")
        return await ws.rows("s", meta["data"]["total"])


async def test_detection_and_status_for_every_user(
    app: FastAPI, client: AsyncClient, settings: Settings
) -> None:
    admin = await setup_admin(client)
    await create_user(client, admin, "kid")
    kid = await login(client, "kid")
    services, _ = await connect(app, settings, {FAKE: fake(), OLD: fake(interface=2), CLOSED: None})

    seen = await rows(app, kid.access_token)

    assert [row["name"] for row in seen] == ["Fake", "Fake", CLOSED]
    available, old, closed = seen
    assert available["available"] is True and available["problem"] is None
    assert available["source"] == "fake" and available["short"] == "FK"
    assert available["qualities"] == ["best", "flac_hires", "flac_cd", "aac_256"]
    assert old["available"] is False and old["problem"] == "incompatible"
    assert closed["available"] is False and closed["problem"] == "unreachable"
    await services.stop()


async def test_logins_are_encrypted_and_renewed(
    app: FastAPI, client: AsyncClient, settings: Settings
) -> None:
    admin = await setup_admin(client)
    services, transports = await connect(app, settings, {FAKE: fake(login="anna:geheim")})
    async with app.state.sessionmaker() as session:
        row = await session.scalar(select(SourceService))
    path = f"/api/v1/sources/services/{row.id}/login"

    missing = row.problem
    shown = await client.get(path, headers=admin.headers)
    wrong = await client.put(
        path, headers=admin.headers, json={"fields": {"username": "anna", "password": "x"}}
    )
    right = await client.put(
        path, headers=admin.headers, json={"fields": {"username": "anna", "password": "geheim"}}
    )
    unknown = await client.put(path, headers=admin.headers, json={"fields": {"token": "x"}})
    kept_user = await client.put(
        path, headers=admin.headers, json={"fields": {"username": "", "password": "falsch"}}
    )
    relogin = await client.put(
        path, headers=admin.headers, json={"fields": {"username": "", "password": "geheim"}}
    )
    async with app.state.sessionmaker() as session:
        stored = await session.scalar(select(SourceCredential))
    # The service restarts and has forgotten its session: the core logs in again.
    transports[FAKE].app = fake(login="anna:geheim")
    again = await services.check(FAKE)

    assert missing == "login_missing"
    assert shown.json() == {
        "fields": [
            {"name": "username", "label": "Benutzername", "secret": False},
            {"name": "password", "label": "Passwort", "secret": True},
        ],
        "stored": False,
        "stored_fields": [],
        "logged_in": False,
        "problem": "login_missing",
    }
    assert wrong.json()["problem"] == "login_failed"
    assert right.json() == {
        **shown.json(),
        "stored": True,
        "stored_fields": ["password", "username"],
        "logged_in": True,
        "problem": None,
    }
    # A changed password alone: the stored user name stays.
    assert kept_user.json()["logged_in"] is False and kept_user.json()["stored_fields"] == [
        "password",
        "username",
    ]
    assert relogin.json()["logged_in"] is True
    assert unknown.status_code == 422
    assert b"geheim" not in stored.ciphertext and b"anna" not in stored.ciphertext
    assert again is True
    await services.stop()


async def test_search_across_services(
    app: FastAPI, client: AsyncClient, settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    admin = await setup_admin(client)
    await create_user(client, admin, "kid")
    kid = await login(client, "kid")
    services, transports = await connect(app, settings, {FAKE: fake(), OTHER: fake()})
    async with app.state.sessionmaker() as session:
        first, second = await session.scalars(
            select(SourceService).order_by(SourceService.position)
        )
    monkeypatch.setattr(sources_api, "SEARCH_TIMEOUT", 0.2)

    both = await client.post(
        "/api/v1/sources/search", headers=admin.headers, json={"query": "polar"}
    )
    transports[OTHER].delay = 1.0
    one_slow = await client.post(
        "/api/v1/sources/search", headers=admin.headers, json={"query": "polar"}
    )
    only_first = await client.post(
        "/api/v1/sources/search",
        headers=admin.headers,
        json={"query": "polar", "service": str(first.id), "kinds": ["album"]},
    )
    forbidden = await client.post(
        "/api/v1/sources/search", headers=kid.headers, json={"query": "polar"}
    )

    assert [answer["service"] for answer in both.json()] == [str(first.id), str(second.id)]
    assert both.json()[0]["results"][0]["title"] == "Polarnacht"
    assert one_slow.json()[1] == {
        "service": str(second.id),
        "results": [],
        "next_page": None,
        "error": "timeout",
    }
    assert len(one_slow.json()[0]["results"]) == 4
    assert [result["kind"] for result in only_first.json()[0]["results"]] == ["album"]
    assert forbidden.status_code == 403
    await services.stop()


def statuses(answer: dict) -> list[tuple]:
    return [
        (track["title"], track["status"], track["existing_quality"]) for track in answer["tracks"]
    ]


async def test_links_show_the_duplicate_status(
    app: FastAPI, client: AsyncClient, settings: Settings
) -> None:
    admin = await setup_admin(client)
    async with app.state.sessionmaker() as session, session.begin():
        _release, tracks = await album(session, "Nordlicht", "Polarnacht", ["Eisfeld", "Treibeis"])
        # Eisfeld by ISRC (as FLAC: present), Treibeis by name (as lossy: a better offer).
        await session.execute(
            update(Recording)
            .where(Recording.id == tracks[0].recording_id)
            .values(isrc="DEA012400001", duration_ms=1_000)
        )
        await session.execute(
            update(Recording)
            .where(Recording.id == tracks[1].recording_id)
            .values(duration_ms=9_500)
        )
        await session.execute(
            update(AudioFile)
            .where(AudioFile.recording_id == tracks[1].recording_id)
            .values(declared_quality=QualityTier.LOSSY_HIGH)
        )
    services, _ = await connect(app, settings, {FAKE: fake()})
    async with app.state.sessionmaker() as session:
        row = await session.scalar(select(SourceService))

    by_link = await client.post(
        "/api/v1/sources/resolve",
        headers=admin.headers,
        json={"url": "https://fake.example/album/1"},
    )
    by_ref = await client.post(
        "/api/v1/sources/resolve",
        headers=admin.headers,
        json={"service": str(row.id), "ref": "track:103"},
    )
    foreign = await client.post(
        "/api/v1/sources/resolve", headers=admin.headers, json={"url": "https://elsewhere/1"}
    )

    assert by_link.status_code == 200 and by_link.json()["item"]["title"] == "Polarnacht"
    assert statuses(by_link.json()) == [
        ("Eisfeld", "present", "cd_lossless"),
        ("Treibeis", "better", "lossy_high"),
        ("Driftlinie", "new", None),
    ]
    assert by_link.json()["tracks"][0]["recording_id"] == str(tracks[0].recording_id)
    assert statuses(by_ref.json()) == [("Driftlinie", "new", None)]
    assert foreign.status_code == 422 and foreign.json()["detail"] == "no_source_for_link"
    await services.stop()
