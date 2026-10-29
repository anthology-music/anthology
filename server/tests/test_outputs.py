"""Outputs and the Raumfeld adapter against the fake host (spec: playback, Output adapters,
Output discovery and addresses, Raumfeld support, Zone play queue, Remote control, Zone
management, Delivery to outputs; playable-delivery-format 3.3, signed-media-urls 3.2)."""

import asyncio
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
from anthology_fake_raumfeld.app import create_app as fake_host
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy import select, update

from anthology.core.config import Settings
from anthology.db.types import utcnow
from anthology.library import service as library
from anthology.library.models import AudioFormat
from anthology.playback import service
from anthology.playback.models import (
    OutputRoom,
    OutputSystem,
    OutputZone,
    PlayQueue,
    SystemOrigin,
    SystemState,
)
from anthology.playback.outputs.base import (
    Listener,
    OutputAdapter,
    RoomInfo,
    SystemSnapshot,
    Transport,
    TransportState,
    ZoneInfo,
)
from anthology.playback.outputs.player import Media
from anthology.playback.outputs.raumfeld import RaumfeldAdapter, ssdp
from anthology.playback.outputs.raumfeld.adapter import formats
from anthology.playback.outputs.registry import Outputs, media_base
from anthology.playback.schemas import PlaybackOutputRow
from anthology.transcoding.models import CacheStatus, TranscodeCacheEntry
from tests.library_helpers import album
from tests.media_helpers import require_ffmpeg, tone_wav
from tests.test_playback import _delta
from tests.users_helpers import Account, create_user, login, setup_admin
from tests.ws_helpers import ws_connect

pytestmark = pytest.mark.usefixtures("clean_db")

HOST = "raumfeld.test:47365"
MEDIA = "http://anthology.test"
ROOMS = {
    "rooms": [
        {"udn": "uuid:living", "name": "Living room"},
        {"udn": "uuid:kitchen", "name": "Kitchen"},
        {"udn": "uuid:bath", "name": "Bath"},
    ],
    "zones": [{"udn": "uuid:zone-living", "rooms": ["uuid:living"]}],
}
# What a Raumfeld host answers to an M-SEARCH for its configuration device.
SSDP_ANSWER = (
    b"HTTP/1.1 200 OK\r\n"
    b"CACHE-CONTROL: max-age=1800\r\n"
    b"EXT:\r\n"
    b"LOCATION: http://192.168.1.20:47365/description.xml\r\n"
    b"SERVER: Linux/2.6 UPnP/1.0 Raumfeld/1.0\r\n"
    b"ST: urn:schemas-raumfeld-com:device:ConfigDevice:1\r\n"
    b"USN: uuid:1d2c3b4a::urn:schemas-raumfeld-com:device:ConfigDevice:1\r\n\r\n"
)
OTHER_ANSWER = SSDP_ANSWER.replace(
    b"urn:schemas-raumfeld-com:device:ConfigDevice:1", b"upnp:rootdevice"
)
# A renderer's GetProtocolInfo sink (FLAC, MP3, AAC, WAV; no AIFF).
SINK = (
    "http-get:*:audio/flac:*,http-get:*:audio/x-flac:*,http-get:*:audio/mpeg:*,"
    "http-get:*:audio/mp4:*,http-get:*:audio/wav:DLNA.ORG_PN=LPCM,http-get:*:image/jpeg:*"
)


class Clock:
    def __init__(self) -> None:
        self.now = utcnow()

    def __call__(self) -> datetime:
        return self.now


@dataclass
class Rig:
    outputs: Outputs
    host: AsyncClient
    clock: Clock

    async def fake(self) -> dict[str, Any]:
        return (await self.host.get("/test/state")).json()

    async def advance(self, seconds: float) -> None:
        await self.host.post("/test/advance", json={"seconds": seconds})
        self.clock.now += timedelta(seconds=seconds)

    async def tick(self) -> None:
        await self.outputs.run_once()


def _media(app: FastAPI, settings: Settings) -> Media:
    return Media(
        sign=app.state.media_signer.sign,
        path_for=app.url_path_for,
        transcoder=app.state.transcoder,
        base_url=media_base(settings),
        max_ttl_seconds=settings.media_url_output_max_ttl_seconds,
    )


@pytest.fixture
async def rig(app: FastAPI, settings: Settings) -> AsyncIterator[Rig]:
    """A fake Raumfeld host whose speakers reach this app, followed by an adapter."""
    fake = fake_host(media_transport=httpx.ASGITransport(app=app))
    transport = httpx.ASGITransport(app=fake)
    configured = settings.model_copy(update={"output_media_url": MEDIA})
    adapter = RaumfeldAdapter(configured, transport=transport, discovery=False)
    clock = Clock()
    outputs = Outputs(
        app.state.sessionmaker,
        configured,
        {"raumfeld": adapter},
        _media(app, configured),
        clock=clock,
    )
    await app.state.outputs.stop()  # the app's own: it must not play the fake's zones
    app.state.outputs = outputs
    async with AsyncClient(transport=transport, base_url=f"http://{HOST}") as host:
        await host.post("/test/setup", json=ROOMS)
        await outputs.start(run_players=False)
        await outputs.add_system("raumfeld", HOST, SystemOrigin.MANUAL)
        rig = Rig(outputs, host, clock)
        await _until(app, lambda zones: len(zones) == 1)
        yield rig
        await outputs.stop()


async def _zones(app: FastAPI) -> list[OutputZone]:
    async with app.state.sessionmaker() as session:
        return list(await session.scalars(select(OutputZone).order_by(OutputZone.name)))


async def _until(app: FastAPI, condition, seconds: float = 5.0) -> list[OutputZone]:
    """Zones once ``condition(zones)`` holds (within ``seconds``, the spec's bound)."""
    deadline = asyncio.get_running_loop().time() + seconds
    while True:
        zones = await _zones(app)
        if condition(zones):
            return zones
        if asyncio.get_running_loop().time() > deadline:
            raise AssertionError(f"not within {seconds} s: {[zone.name for zone in zones]}")
        await asyncio.sleep(0.02)


async def _rooms(app: FastAPI) -> dict[str, OutputRoom]:
    async with app.state.sessionmaker() as session:
        return {room.name: room for room in await session.scalars(select(OutputRoom))}


async def _library(app: FastAPI, tmp_path: Path, titles: list[str], suffix: str = ".flac"):
    """An album whose originals exist (generated bytes; the fake reads their start)."""
    async with app.state.sessionmaker() as session, session.begin():
        release, tracks = await album(session, "Nordlicht", "Polarnacht", titles)
        for number, track in enumerate(tracks):
            original = await library.active_original(session, track.recording_id)
            path = tmp_path / f"{number}{suffix}"
            path.write_bytes(bytes(range(256)) * 64)
            original.path = str(path)
    return release, tracks


async def _queue(app: FastAPI, zone_id: uuid.UUID) -> PlayQueue | None:
    async with app.state.sessionmaker() as session:
        return await session.scalar(select(PlayQueue).where(PlayQueue.output_zone_id == zone_id))


async def _titles(app: FastAPI, account: Account) -> tuple[dict, list[str]]:
    """The state row and the queue titles this account's device shows."""
    async with ws_connect(app) as ws:
        await ws.hello(account.access_token)
        await ws.subscribe("s", "playback.state")
        state = (await ws.rows("s", 1))[0]
        meta = await ws.subscribe("q", "playback.queue", generation=state["generation"])
        rows = await ws.rows("q", meta["data"]["total"])
    return state, [row["track"]["title"] for row in rows]


async def _play(client: AsyncClient, account: Account, tracks) -> None:
    ids = [str(track.id) for track in tracks]
    response = await client.post(
        "/api/v1/playback/queue", headers=account.headers, json={"ids": ids}
    )
    assert response.status_code == 200, response.text


async def _choose(client: AsyncClient, account: Account, zone_id) -> httpx.Response:
    body = {"zone_id": str(zone_id) if zone_id is not None else None}
    return await client.put("/api/v1/playback/output", headers=account.headers, json=body)


def _user(account: Account) -> uuid.UUID:
    return uuid.UUID(account.user["id"])


def _query(uri: str) -> dict[str, str]:
    return {key: values[0] for key, values in parse_qs(urlsplit(uri).query).items()}


# --- the interface ------------------------------------------------------------------------


class StubAdapter(OutputAdapter):
    """A system the core knows nothing about."""

    name = "stub"

    async def start(self, listener: Listener) -> None:
        self.listener = listener

    async def stop(self) -> None: ...

    async def watch(self, address: str) -> None:
        await self.refresh(address)

    async def unwatch(self, address: str) -> None: ...

    async def refresh(self, address: str) -> SystemSnapshot:
        snapshot = SystemSnapshot(
            reachable=True,
            name="Stub",
            zones=(ZoneInfo("z1", "Hall", (RoomInfo("r1", "Hall"),), formats=frozenset()),),
            rooms=(RoomInfo("r2", "Attic"),),
        )
        await self.listener.snapshot(address, snapshot)
        return snapshot

    async def play(self, zone, uri, metadata, start_ms=0) -> None: ...
    async def pause(self, zone) -> None: ...
    async def resume(self, zone) -> None: ...
    async def stop_zone(self, zone) -> None: ...
    async def seek(self, zone, position_ms) -> None: ...

    async def state(self, zone) -> TransportState:
        return TransportState(Transport.STOPPED, 0, None)

    async def set_volume(self, zone, volume, muted) -> None: ...
    async def set_room_volume(self, room, volume, muted) -> None: ...
    async def group(self, room, zone) -> None: ...
    async def ungroup(self, room) -> None: ...


async def test_a_new_adapter_needs_no_core_changes(
    app: FastAPI, client: AsyncClient, settings: Settings
) -> None:
    admin = await setup_admin(client)
    outputs = Outputs(
        app.state.sessionmaker, settings, {"stub": StubAdapter()}, _media(app, settings)
    )
    app.state.outputs = outputs
    await outputs.start(run_players=False)
    added = await client.post(
        "/api/v1/playback/systems", headers=admin.headers, json={"adapter": "stub", "address": "x"}
    )
    async with ws_connect(app) as ws:
        await ws.hello(admin.access_token)
        meta = await ws.subscribe("o", "playback.outputs")
        rows = await ws.rows("o", meta["data"]["total"])
    await outputs.stop()

    assert added.status_code == 201
    assert meta["data"]["counters"] == {"output_system": 1, "output_zone": 1, "output_room": 2}
    assert [(row["kind"], row["name"]) for row in rows] == [
        ("system", "Stub"),
        ("zone", "Hall"),
        ("room", "Attic"),
        ("room", "Hall"),
    ]
    zone = rows[1]
    assert zone["online"] is True and rows[3]["zone_id"] == zone["id"]
    for row in rows:
        PlaybackOutputRow.model_validate(row)
    assert rows[2]["zone_id"] is None


def test_ssdp_answers_and_protocol_info() -> None:
    assert ssdp.host_address(SSDP_ANSWER) == "192.168.1.20:47365"
    assert ssdp.host_address(OTHER_ANSWER) is None
    assert b"ST: urn:schemas-raumfeld-com:device:ConfigDevice:1" in ssdp.m_search()
    assert formats(SINK) == {AudioFormat.FLAC, AudioFormat.MP3, AudioFormat.AAC, AudioFormat.WAV}


# --- systems, zones and rooms -------------------------------------------------------------


async def test_zones_follow_the_host(app: FastAPI, rig: Rig) -> None:
    [zone] = await _zones(app)
    rooms = await _rooms(app)

    # A room joins the zone in the Raumfeld app: the long poll brings it within five seconds.
    await rig.host.get(
        "/connectRoomToZone", params={"roomUDN": "uuid:kitchen", "zoneUDN": "uuid:zone-living"}
    )
    [grown] = await _until(app, lambda zones: zones and "Kitchen" in zones[0].name)
    kitchen = (await _rooms(app))["Kitchen"]

    assert zone.name == "Living room" and zone.online
    assert set(zone.formats) >= {"flac", "mp3", "aac", "wav"}
    assert zone.control.endswith("/zones/uuid:zone-living/description.xml")
    assert zone.volume == 30
    assert rooms["Bath"].zone_id is None and rooms["Living room"].zone_id == zone.id
    assert grown.id == zone.id and grown.name == "Living room + Kitchen"
    assert kitchen.zone_id == zone.id


async def test_unreachable_host_shows_its_zones_offline(
    app: FastAPI, client: AsyncClient, rig: Rig
) -> None:
    admin = await setup_admin(client)
    [zone] = await _zones(app)

    await rig.host.post("/test/offline", json={"offline": True})
    await _until(app, lambda zones: not zones[0].online)
    async with app.state.sessionmaker() as session:
        system = await session.scalar(select(OutputSystem))
    chosen = await _choose(client, admin, zone.id)
    async with ws_connect(app) as ws:
        await ws.hello(admin.access_token)
        meta = await ws.subscribe("o", "playback.outputs")
        rows = await ws.rows("o", meta["data"]["total"])

    assert system.state == SystemState.UNREACHABLE and system.reason == "HTTP 503"
    assert chosen.status_code == 409 and chosen.json()["detail"] == "output_offline"
    assert rows[0]["state"] == "unreachable" and rows[0]["reason"] == "HTTP 503"
    assert {row["online"] for row in rows[1:]} == {False}


async def test_addresses_are_for_admins(app: FastAPI, client: AsyncClient, rig: Rig) -> None:
    admin = await setup_admin(client)
    await create_user(client, admin, "lena")
    lena = await login(client, "lena")
    path = "/api/v1/playback/systems"

    refused = await client.post(path, headers=lena.headers, json={"address": "192.168.1.30"})
    invalid = await client.post(path, headers=admin.headers, json={"address": "http://"})
    added = await client.post(path, headers=admin.headers, json={"address": "192.168.1.30"})
    async with app.state.sessionmaker() as session:
        addresses = set(await session.scalars(select(OutputSystem.address)))
    removed = await client.delete(f"{path}/{added.json()['id']}", headers=admin.headers)

    assert refused.status_code == 403
    assert invalid.status_code == 422
    assert added.status_code == 201
    assert addresses == {HOST, "192.168.1.30:47365"}
    assert removed.status_code == 204


# --- playing on a zone --------------------------------------------------------------------


async def test_handover_shared_zone_pause_and_take_back(
    app: FastAPI, client: AsyncClient, rig: Rig, tmp_path: Path
) -> None:
    admin = await setup_admin(client)
    await create_user(client, admin, "lena")
    lena = await login(client, "lena")
    titles = ["Eisfeld", "Treibeis", "Driftlinie", "Polarlicht", "Schneesturm", "Tauwetter"]
    release, tracks = await _library(app, tmp_path, titles)
    [zone] = await _zones(app)
    rule = {"list": "release_tracks", "release_id": str(release.id)}
    await client.post(
        "/api/v1/playback/queue",
        headers=admin.headers,
        json={"rule": rule, "start": str(tracks[4].id)},
    )
    async with app.state.sessionmaker() as session:
        own = await service.find_queue(session, _user(admin), uuid.UUID(admin.device_id))
    await client.put(
        "/api/v1/playback/state",
        headers=admin.headers,
        json={
            "current_entry_id": str(own.current_entry_id),
            "position_ms": 80_000,
            "playing": True,
        },
    )

    # The fifth track at 1:20 goes to the living room.
    chosen = await _choose(client, admin, zone.id)
    await rig.tick()
    playing = (await rig.fake())["zones"]["uuid:zone-living"]
    remote_state, remote_titles = await _titles(app, admin)
    async with app.state.sessionmaker() as session:
        own = await service.find_queue(session, _user(admin), uuid.UUID(admin.device_id))

    assert chosen.status_code == 204
    assert playing["state"] == "playing" and playing["position_ms"] >= 80_000
    assert "<dc:title>Schneesturm</dc:title>" in playing["metadata"]
    assert "<upnp:album>Polarnacht</upnp:album>" in playing["metadata"]
    original = _query(playing["uri"])
    assert playing["uri"].startswith(f"{MEDIA}/api/v1/media/originals/")
    assert original["d"] == str(zone.id) and original["u"] == admin.user["id"]
    assert (await rig.fake())["fetches"] == [{"uri": playing["uri"], "status": 206}]
    assert remote_state["output_zone_id"] == str(zone.id) and remote_state["playing"] is True
    assert remote_titles == titles
    assert own.playing is False

    # A second user selects the zone that plays: the same queue, and pause acts on the zone.
    await _play(client, lena, tracks[:1])
    await _choose(client, lena, zone.id)
    lena_state, lena_titles = await _titles(app, lena)
    await client.put(
        "/api/v1/playback/state",
        headers=lena.headers,
        json={
            "current_entry_id": lena_state["current_entry_id"],
            "position_ms": lena_state["position_ms"],
            "playing": False,
        },
    )
    await rig.tick()
    paused = (await rig.fake())["zones"]["uuid:zone-living"]
    admin_state, _ = await _titles(app, admin)

    assert lena_titles == titles and lena_state["id"] != admin_state["id"]
    assert paused["state"] == "paused"
    assert admin_state["playing"] is False

    # Back to this device: the zone stops, the queue returns paused at the zone's position.
    await rig.advance(10)
    back = await _choose(client, admin, None)
    stopped = (await rig.fake())["zones"]["uuid:zone-living"]
    device_state, device_titles = await _titles(app, admin)

    assert back.status_code == 204
    assert stopped["state"] == "stopped"
    assert device_state["output_zone_id"] is None and device_state["playing"] is False
    assert device_titles == titles
    assert device_state["current"]["title"] == "Schneesturm"
    assert device_state["position_ms"] == admin_state["position_ms"]


async def test_the_zone_plays_the_queue_to_the_end_without_a_client(
    app: FastAPI, client: AsyncClient, rig: Rig, tmp_path: Path
) -> None:
    admin = await setup_admin(client)
    _release, tracks = await _library(app, tmp_path, ["Eisfeld", "Treibeis"])
    [zone] = await _zones(app)
    await _play(client, admin, tracks)
    await _choose(client, admin, zone.id)

    await rig.tick()
    first = (await rig.fake())["zones"]["uuid:zone-living"]["uri"]
    await rig.advance(6)
    await rig.tick()
    position = (await _queue(app, zone.id)).position_ms
    await rig.advance(180)  # the first track (3:00) ends
    await rig.tick()
    second = (await rig.fake())["zones"]["uuid:zone-living"]
    await rig.advance(182)  # the second track ends, unobserved while it played
    await rig.tick()
    queue = await _queue(app, zone.id)

    assert position >= 6_000
    assert second["uri"] != first and second["state"] == "playing"
    assert "<dc:title>Treibeis</dc:title>" in second["metadata"]
    assert queue.playing is False
    assert len((await rig.fake())["fetches"]) == 2


async def test_the_raumfeld_app_takes_over(
    app: FastAPI, client: AsyncClient, rig: Rig, tmp_path: Path
) -> None:
    admin = await setup_admin(client)
    _release, tracks = await _library(app, tmp_path, ["Eisfeld"])
    [zone] = await _zones(app)
    await _play(client, admin, tracks[:1])
    await _choose(client, admin, zone.id)
    await rig.tick()
    await rig.advance(30)
    await rig.tick()

    await rig.host.post("/test/foreign", json={"zone": "uuid:zone-living"})
    await rig.tick()
    queue = await _queue(app, zone.id)
    fake = (await rig.fake())["zones"]["uuid:zone-living"]

    assert queue.playing is False and queue.position_ms >= 30_000
    assert fake["uri"] == "http://radio.invalid/stream.mp3" and fake["state"] == "playing"


async def test_undeliverable_entries_are_skipped_and_aiff_is_transcoded(
    app: FastAPI, client: AsyncClient, rig: Rig, tmp_path: Path
) -> None:
    require_ffmpeg()
    admin = await setup_admin(client)
    # AIFF originals (the bytes are WAV: FFmpeg reads either, the server image writes no AIFF).
    _release, tracks = await _library(app, tmp_path, ["Kaputt", "Eisfeld"], suffix=".aiff")
    transcoder = app.state.transcoder
    async with app.state.sessionmaker() as session, session.begin():
        for track, frequency in zip(tracks, (330, 440), strict=True):
            original = await library.active_original(session, track.recording_id)
            original.format = AudioFormat.AIFF
            if frequency == 330:
                await asyncio.to_thread(Path(original.path).write_bytes, b"not audio")
            else:
                wav = tone_wav(tmp_path / "tone.wav", [frequency], 3)
                original.path = str(wav)
        broken = await library.active_original(session, tracks[0].recording_id)
    # The first track's transcode failed a moment ago.
    entry = await transcoder.ensure(broken.id, transcoder_variant())
    await transcoder.wait(entry.id)
    [zone] = await _zones(app)
    await _play(client, admin, tracks)
    await _choose(client, admin, zone.id)

    await rig.tick()
    playing = (await rig.fake())["zones"]["uuid:zone-living"]
    queue = await _queue(app, zone.id)
    async with app.state.sessionmaker() as session:
        failed = await session.get(TranscodeCacheEntry, entry.id)

    assert failed.status == CacheStatus.FAILED
    assert "<dc:title>Eisfeld</dc:title>" in playing["metadata"]
    assert "/api/v1/media/transcodes/" in playing["uri"]
    assert 'protocolInfo="http-get:*:audio/mp4:*"' in playing["metadata"]
    assert queue.playing is True


def transcoder_variant():
    from anthology.transcoding.delivery import STEPS, Variant

    return Variant(AudioFormat.AAC, STEPS[-1])


async def test_a_paused_track_gets_a_new_url_after_its_url_expired(
    app: FastAPI, client: AsyncClient, rig: Rig, tmp_path: Path
) -> None:
    admin = await setup_admin(client)
    _release, tracks = await _library(app, tmp_path, ["Eisfeld"])
    [zone] = await _zones(app)
    await _play(client, admin, tracks[:1])
    await _choose(client, admin, zone.id)
    await rig.tick()
    first = (await rig.fake())["zones"]["uuid:zone-living"]["uri"]
    await rig.advance(20)
    await rig.tick()

    async def command(playing: bool) -> None:
        state, _ = await _titles(app, admin)
        await client.put(
            "/api/v1/playback/state",
            headers=admin.headers,
            json={
                "current_entry_id": state["current_entry_id"],
                "position_ms": state["position_ms"],
                "playing": playing,
            },
        )
        await rig.tick()

    await command(False)
    await rig.advance(2 * 3600)  # the URL (3:00 plus an hour) expired while paused
    await command(True)
    fake = await rig.fake()
    renewed = fake["zones"]["uuid:zone-living"]
    expires = int(_query(first)["exp"]), int(_query(renewed["uri"])["exp"])

    assert renewed["state"] == "playing"
    assert renewed["position_ms"] >= 20_000
    assert [r["action"] for r in fake["requests"] if r.get("action") == "SetAVTransportURI"] == [
        "SetAVTransportURI",
        "SetAVTransportURI",
    ]
    # Valid for the track (3:00) plus an hour, issued by the real clock.
    assert 3 * 60 + 3600 - 5 <= expires[0] - int(utcnow().timestamp()) <= 3 * 60 + 3600


async def test_zone_urls_end_with_the_zone_or_the_user(
    app: FastAPI, client: AsyncClient, rig: Rig, tmp_path: Path
) -> None:
    admin = await setup_admin(client)
    _release, tracks = await _library(app, tmp_path, ["Eisfeld"])
    [zone] = await _zones(app)
    await _play(client, admin, tracks[:1])
    await _choose(client, admin, zone.id)
    await rig.tick()
    uri = (await rig.fake())["zones"]["uuid:zone-living"]["uri"]
    path = uri.removeprefix(MEDIA)

    valid = await client.get(path, headers={"Range": "bytes=0-9"})
    async with app.state.sessionmaker() as session:
        system = await session.scalar(select(OutputSystem))
    await rig.outputs.remove_system(system.id)
    rig.outputs._grants.clear()
    gone = await client.get(path, headers={"Range": "bytes=0-9"})

    assert valid.status_code == 206
    assert gone.status_code == 403


async def test_one_process_plays_a_zone(
    app: FastAPI, client: AsyncClient, rig: Rig, settings: Settings, tmp_path: Path
) -> None:
    admin = await setup_admin(client)
    _release, tracks = await _library(app, tmp_path, ["Eisfeld"])
    [zone] = await _zones(app)
    other = Outputs(app.state.sessionmaker, settings, rig.outputs.adapters, _media(app, settings))
    await _play(client, admin, tracks[:1])
    await _choose(client, admin, zone.id)

    await rig.tick()
    await other.run_once()
    held_elsewhere = dict(other.players)
    # The first process died: its lease ends and the other one takes over.
    async with app.state.sessionmaker() as session, session.begin():
        await session.execute(
            update(OutputZone).values(player_lease_until=utcnow() - timedelta(seconds=1))
        )
    await other.run_once()

    assert list(rig.outputs.players) == [zone.id]
    assert held_elsewhere == {}
    assert list(other.players) == [zone.id]


# --- zone management ----------------------------------------------------------------------


async def test_rooms_join_leave_and_have_their_own_volume(
    app: FastAPI, client: AsyncClient, rig: Rig
) -> None:
    admin = await setup_admin(client)
    await create_user(client, admin, "lena")
    lena = await login(client, "lena")
    [living] = await _zones(app)
    rooms = await _rooms(app)
    base = "/api/v1/playback"

    joined = await client.put(
        f"{base}/rooms/{rooms['Kitchen'].id}/zone",
        headers=lena.headers,
        json={"zone_id": str(living.id)},
    )
    after_join = await _rooms(app)
    quieter = await client.put(
        f"{base}/rooms/{rooms['Kitchen'].id}/volume", headers=lena.headers, json={"volume": 12}
    )
    muted = await client.put(
        f"{base}/zones/{living.id}/volume", headers=lena.headers, json={"muted": True}
    )
    fake = await rig.fake()
    alone = await client.put(
        f"{base}/rooms/{rooms['Bath'].id}/zone", headers=lena.headers, json={"zone_id": None}
    )
    zones_with_bath = await _zones(app)
    left = await client.delete(f"{base}/rooms/{rooms['Kitchen'].id}/zone", headers=lena.headers)
    after_leave = await _rooms(app)
    unknown = await client.put(
        f"{base}/zones/{uuid.uuid4()}/volume", headers=lena.headers, json={"volume": 5}
    )

    assert (joined.status_code, quieter.status_code, muted.status_code) == (204, 204, 204)
    assert after_join["Kitchen"].zone_id == living.id
    assert after_join["Kitchen"].volume == 12 or fake["rooms"]["uuid:kitchen"]["volume"] == 12
    assert fake["rooms"]["uuid:kitchen"]["volume"] == 12
    assert fake["rooms"]["uuid:living"]["volume"] == 30
    assert fake["zones"]["uuid:zone-living"]["muted"] is True
    assert alone.status_code == 204
    assert sorted(zone.name for zone in zones_with_bath) == ["Bath", "Living room + Kitchen"]
    assert left.status_code == 204 and after_leave["Kitchen"].zone_id is None
    assert unknown.status_code == 404


async def test_an_open_state_stream_follows_the_output(
    app: FastAPI, client: AsyncClient, rig: Rig, tmp_path: Path
) -> None:
    admin = await setup_admin(client)
    _release, tracks = await _library(app, tmp_path, ["Eisfeld"])
    [zone] = await _zones(app)
    await _play(client, admin, tracks)

    def output(zone_id, playing: bool):
        # On PostgreSQL the first delta may repeat the snapshot: wait for the expected one.
        return lambda data: (
            bool(data["row"])
            and (
                data["row"]["output_zone_id"],
                data["row"]["playing"],
            )
            == (zone_id, playing)
        )

    async with ws_connect(app) as ws:
        await ws.hello(admin.access_token)
        await ws.subscribe("s", "playback.state")
        [before] = await ws.rows("s", 1)
        await _choose(client, admin, zone.id)
        remote = await _delta(ws, "s", output(str(zone.id), True))
        await _choose(client, admin, None)
        local = await _delta(ws, "s", output(None, False))

    assert remote["id"] == local["id"] == before["id"]
