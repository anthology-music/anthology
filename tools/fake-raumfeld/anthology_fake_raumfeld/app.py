"""The fake Raumfeld host: the host's configuration service and one virtual UPnP media renderer
per zone, as described in docs/architecture/raumfeld.md, with a simulated clock.

``Play`` fetches the first bytes of the track's URI with a range request, as speakers do, and
the position advances with the clock; a track ends at the duration of its DIDL-Lite. Test
endpoints (``/test/...``) set up rooms and zones, advance the clock, make the host unreachable,
let "the Raumfeld app" play a foreign source and list the requests the fake received.
"""

import argparse
import asyncio
import itertools
import os
import re
import time
import uuid
from dataclasses import dataclass, field
from typing import Any
from xml.etree import ElementTree
from xml.sax.saxutils import escape, quoteattr

import httpx
from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse

PORT = 47365
# The host answers a long poll after this many seconds without a change.
LONG_POLL_SECONDS = 25.0
DEFAULT_SINK = (
    "http-get:*:audio/flac:*",
    "http-get:*:audio/x-flac:*",
    "http-get:*:audio/mpeg:*",
    "http-get:*:audio/mp4:*",
    "http-get:*:audio/x-m4a:*",
    "http-get:*:audio/wav:*",
    "http-get:*:audio/ogg:*",
)
SOAP_ENV = "http://schemas.xmlsoap.org/soap/envelope/"
SERVICES = {
    "AVTransport": "urn:schemas-upnp-org:service:AVTransport:1",
    "RenderingControl": "urn:schemas-upnp-org:service:RenderingControl:1",
    "ConnectionManager": "urn:schemas-upnp-org:service:ConnectionManager:1",
}
DURATION = re.compile(r'duration="(\d+):(\d+):(\d+)(?:\.(\d+))?"')
STATES = {
    "playing": "PLAYING",
    "paused": "PAUSED_PLAYBACK",
    "stopped": "STOPPED",
    "none": "NO_MEDIA_PRESENT",
}


class Clock:
    """Real time plus what the tests added."""

    def __init__(self) -> None:
        self.offset = 0.0

    def now(self) -> float:
        return time.monotonic() + self.offset


@dataclass
class Renderer:
    uri: str | None = None
    metadata: str = ""
    duration_ms: int = 0
    state: str = "none"
    # Position at ``since`` (clock seconds); it advances while playing.
    position_ms: int = 0
    since: float = 0.0
    volume: int = 30
    muted: bool = False

    def position(self, now: float) -> int:
        if self.state != "playing":
            return self.position_ms
        position = self.position_ms + int((now - self.since) * 1000)
        return min(position, self.duration_ms) if self.duration_ms else position

    def settle(self, now: float) -> None:
        """A track that played to its end stops."""
        if self.state == "playing" and self.duration_ms and self.position(now) >= self.duration_ms:
            self.position_ms, self.state, self.since = self.duration_ms, "stopped", now


@dataclass
class Room:
    udn: str
    name: str
    volume: int = 30
    muted: bool = False


@dataclass
class Zone:
    udn: str
    rooms: list[str]
    renderer: Renderer = field(default_factory=Renderer)


@dataclass
class State:
    rooms: dict[str, Room] = field(default_factory=dict)
    zones: dict[str, Zone] = field(default_factory=dict)
    update_id: int = 1
    changed: asyncio.Event = field(default_factory=asyncio.Event)
    offline: bool = False
    sink: tuple[str, ...] = DEFAULT_SINK
    requests: list[dict[str, Any]] = field(default_factory=list)
    fetches: list[dict[str, Any]] = field(default_factory=list)
    counter: itertools.count = field(default_factory=lambda: itertools.count(1))

    def bump(self) -> None:
        self.update_id += 1
        self.changed.set()
        self.changed = asyncio.Event()

    def zone_of(self, room_udn: str) -> Zone | None:
        return next((zone for zone in self.zones.values() if room_udn in zone.rooms), None)

    def take_out(self, room_udn: str) -> None:
        zone = self.zone_of(room_udn)
        if zone is not None:
            zone.rooms.remove(room_udn)
            if not zone.rooms:
                del self.zones[zone.udn]


def _zone_config(state: State) -> str:
    def room(udn: str) -> str:
        item = state.rooms[udn]
        return (
            f"<room udn={quoteattr(udn)} name={quoteattr(item.name)}>"
            f"<renderer udn={quoteattr(udn + '-speaker')} name={quoteattr(item.name)}/></room>"
        )

    zones = "".join(
        f"<zone udn={quoteattr(zone.udn)}>{''.join(room(udn) for udn in zone.rooms)}</zone>"
        for zone in state.zones.values()
    )
    assigned = {udn for zone in state.zones.values() for udn in zone.rooms}
    free = "".join(room(udn) for udn in state.rooms if udn not in assigned)
    return (
        '<?xml version="1.0" encoding="utf-8"?>'
        f'<zoneConfig numRooms="{len(state.rooms)}"><zones>{zones}</zones>'
        f"<unassignedRooms>{free}</unassignedRooms></zoneConfig>"
    )


def _description(base: str, zone: Zone, state: State) -> str:
    name = " + ".join(state.rooms[udn].name for udn in zone.rooms)
    services = "".join(
        f"<service><serviceType>{kind}</serviceType>"
        f"<serviceId>urn:upnp-org:serviceId:{short}</serviceId>"
        f"<controlURL>/zones/{zone.udn}/{short}/control</controlURL>"
        f"<eventSubURL>/zones/{zone.udn}/{short}/event</eventSubURL>"
        f"<SCPDURL>/zones/{zone.udn}/{short}.xml</SCPDURL></service>"
        for short, kind in SERVICES.items()
    )
    return (
        '<?xml version="1.0" encoding="utf-8"?>'
        '<root xmlns="urn:schemas-upnp-org:device-1-0">'
        f"<URLBase>{escape(base)}</URLBase><device>"
        "<deviceType>urn:schemas-upnp-org:device:MediaRenderer:1</deviceType>"
        f"<friendlyName>{escape(name)}</friendlyName>"
        "<manufacturer>Raumfeld</manufacturer><modelName>Virtual Media Player</modelName>"
        f"<UDN>{escape(zone.udn)}</UDN><serviceList>{services}</serviceList>"
        "</device></root>"
    )


def _soap(service: str, action: str, values: dict[str, Any]) -> Response:
    body = "".join(f"<{key}>{escape(str(value))}</{key}>" for key, value in values.items())
    envelope = (
        '<?xml version="1.0" encoding="utf-8"?>'
        f'<s:Envelope xmlns:s="{SOAP_ENV}" s:encodingStyle='
        '"http://schemas.xmlsoap.org/soap/encoding/"><s:Body>'
        f'<u:{action}Response xmlns:u="{SERVICES[service]}">{body}</u:{action}Response>'
        "</s:Body></s:Envelope>"
    )
    return Response(envelope, media_type='text/xml; charset="utf-8"')


def _fault(code: int, text: str) -> Response:
    envelope = (
        f'<?xml version="1.0"?><s:Envelope xmlns:s="{SOAP_ENV}"><s:Body><s:Fault>'
        "<faultcode>s:Client</faultcode><faultstring>UPnPError</faultstring><detail>"
        '<UPnPError xmlns="urn:schemas-upnp-org:control-1-0">'
        f"<errorCode>{code}</errorCode><errorDescription>{escape(text)}</errorDescription>"
        "</UPnPError></detail></s:Fault></s:Body></s:Envelope>"
    )
    return Response(envelope, status_code=500, media_type='text/xml; charset="utf-8"')


def _arguments(body: bytes) -> dict[str, str]:
    # The fake parses only what its tests and the server send (trusted, local).
    root = ElementTree.fromstring(body)  # noqa: S314
    action = next(iter(root.find(f"{{{SOAP_ENV}}}Body")))
    return {child.tag.split("}")[-1]: child.text or "" for child in action}


def _clock_time(milliseconds: int) -> str:
    seconds = milliseconds // 1000
    return f"{seconds // 3600}:{seconds // 60 % 60:02d}:{seconds % 60:02d}"


def _parse_time(value: str) -> int:
    hours, minutes, seconds = (float(part) for part in value.split(":"))
    return int((hours * 3600 + minutes * 60 + seconds) * 1000)


def create_app(
    media_transport: httpx.AsyncBaseTransport | None = None, clock: Clock | None = None
) -> FastAPI:
    """``media_transport``: how the speakers reach media URLs (tests: the server in process)."""
    app = FastAPI(title="Fake Raumfeld host")
    state = State()
    clock = clock or Clock()
    app.state.fake = state
    app.state.clock = clock

    @app.middleware("http")
    async def record(request: Request, call_next):
        if not request.url.path.startswith("/test/"):
            if state.offline:
                return Response(status_code=503)
            entry: dict[str, Any] = {"method": request.method, "path": request.url.path}
            if request.url.query:
                entry["query"] = request.url.query
            action = request.headers.get("soapaction")
            if action:
                entry["action"] = action.strip('"').split("#")[-1]
            state.requests.append(entry)
        return await call_next(request)

    # --- host configuration service ------------------------------------------------------

    @app.get("/getZones")
    async def get_zones(request: Request) -> Response:
        known = request.headers.get("updateID")
        if known is not None and known == str(state.update_id):
            changed = state.changed
            try:
                await asyncio.wait_for(changed.wait(), LONG_POLL_SECONDS)
            except TimeoutError:
                pass
        return Response(
            _zone_config(state),
            media_type="text/xml",
            headers={"updateID": str(state.update_id)},
        )

    @app.get("/listDevices")
    async def list_devices(request: Request) -> Response:
        base = str(request.base_url).rstrip("/")
        devices = "".join(
            f"<device location={quoteattr(f'{base}/zones/{zone.udn}/description.xml')}"
            f" udn={quoteattr(zone.udn)}"
            ' type="urn:schemas-upnp-org:device:MediaRenderer:1">'
            f"{escape(' + '.join(state.rooms[udn].name for udn in zone.rooms))}</device>"
            for zone in state.zones.values()
        )
        return Response(f'<?xml version="1.0"?><devices>{devices}</devices>', media_type="text/xml")

    @app.get("/connectRoomToZone")
    async def connect(roomUDN: str, zoneUDN: str = "") -> Response:
        if roomUDN not in state.rooms or (zoneUDN and zoneUDN not in state.zones):
            return Response(status_code=404)
        if zoneUDN and roomUDN in state.zones[zoneUDN].rooms:
            return Response(status_code=200)
        state.take_out(roomUDN)
        if zoneUDN and zoneUDN in state.zones:
            state.zones[zoneUDN].rooms.append(roomUDN)
        else:
            udn = f"uuid:zone-{next(state.counter)}-{uuid.uuid4().hex[:8]}"
            state.zones[udn] = Zone(udn=udn, rooms=[roomUDN])
        state.bump()
        return Response(status_code=200)

    @app.get("/dropRoomJob")
    async def drop(roomUDN: str) -> Response:
        if roomUDN not in state.rooms:
            return Response(status_code=404)
        state.take_out(roomUDN)
        state.bump()
        return Response(status_code=200)

    # --- zone renderers ------------------------------------------------------------------

    @app.get("/zones/{udn}/description.xml")
    async def description(request: Request, udn: str) -> Response:
        zone = state.zones.get(udn)
        if zone is None:
            return Response(status_code=404)
        base = str(request.base_url).rstrip("/")
        return Response(_description(base, zone, state), media_type="text/xml")

    @app.post("/zones/{udn}/{service}/control")
    async def control(request: Request, udn: str, service: str) -> Response:
        zone = state.zones.get(udn)
        if zone is None or service not in SERVICES:
            return Response(status_code=404)
        action = request.headers.get("soapaction", "").strip('"').split("#")[-1]
        args = _arguments(await request.body())
        renderer = zone.renderer
        now = clock.now()
        renderer.settle(now)
        handler = _HANDLERS.get((service, action))
        if handler is None:
            return _fault(401, "Invalid Action")
        return await handler(state, zone, renderer, args, now, media_transport)

    # --- test endpoints ------------------------------------------------------------------

    @app.post("/test/setup")
    async def setup(request: Request) -> dict:
        """``{"rooms": [{"udn", "name"}], "zones": [{"udn", "rooms": [udn]}], "sink": [...]}``"""
        body = await request.json()
        state.rooms = {room["udn"]: Room(room["udn"], room["name"]) for room in body["rooms"]}
        state.zones = {
            zone["udn"]: Zone(udn=zone["udn"], rooms=list(zone["rooms"]))
            for zone in body.get("zones", [])
        }
        if "sink" in body:
            state.sink = tuple(body["sink"])
        state.requests.clear()
        state.fetches.clear()
        state.bump()
        return {"update_id": state.update_id}

    @app.post("/test/advance")
    async def advance(request: Request) -> dict:
        clock.offset += float((await request.json())["seconds"])
        return {"ok": True}

    @app.post("/test/offline")
    async def offline(request: Request) -> dict:
        state.offline = bool((await request.json())["offline"])
        state.bump()
        return {"ok": True}

    @app.post("/test/foreign")
    async def foreign(request: Request) -> dict:
        """The Raumfeld app plays a radio station on the zone."""
        zone = state.zones[(await request.json())["zone"]]
        zone.renderer = Renderer(
            uri="http://radio.invalid/stream.mp3",
            state="playing",
            since=clock.now(),
            volume=zone.renderer.volume,
            muted=zone.renderer.muted,
        )
        return {"ok": True}

    @app.get("/test/state")
    async def read_state() -> JSONResponse:
        now = clock.now()
        zones = {}
        for zone in state.zones.values():
            zone.renderer.settle(now)
            renderer = zone.renderer
            zones[zone.udn] = {
                "rooms": zone.rooms,
                "uri": renderer.uri,
                "metadata": renderer.metadata,
                "state": renderer.state,
                "position_ms": renderer.position(now),
                "volume": renderer.volume,
                "muted": renderer.muted,
            }
        rooms = {
            room.udn: {"name": room.name, "volume": room.volume, "muted": room.muted}
            for room in state.rooms.values()
        }
        return JSONResponse(
            {
                "zones": zones,
                "rooms": rooms,
                "requests": state.requests,
                "fetches": state.fetches,
                "update_id": state.update_id,
            }
        )

    return app


# --- SOAP actions --------------------------------------------------------------------------


async def _fetch(uri: str, state: State, transport: httpx.AsyncBaseTransport | None) -> None:
    """What a speaker does first: read the start of the stream."""
    try:
        async with httpx.AsyncClient(transport=transport, timeout=10.0) as client:
            response = await client.get(uri, headers={"Range": "bytes=0-1023"})
        state.fetches.append({"uri": uri, "status": response.status_code})
    except httpx.HTTPError as error:
        state.fetches.append({"uri": uri, "status": None, "error": str(error)})


async def _set_uri(state, zone, renderer, args, now, transport):
    metadata = args.get("CurrentURIMetaData", "")
    match = DURATION.search(metadata)
    duration = 0
    if match:
        hours, minutes, seconds = (int(part) for part in match.groups()[:3])
        duration = (hours * 3600 + minutes * 60 + seconds) * 1000
    zone.renderer = Renderer(
        uri=args["CurrentURI"],
        metadata=metadata,
        duration_ms=duration,
        state="stopped",
        since=now,
        volume=renderer.volume,
        muted=renderer.muted,
    )
    return _soap("AVTransport", "SetAVTransportURI", {})


async def _play(state, zone, renderer, args, now, transport):
    if renderer.uri is None:
        return _fault(701, "Transition not available")
    if renderer.state != "paused":
        await _fetch(renderer.uri, state, transport)
    if renderer.state == "stopped" and renderer.position_ms >= renderer.duration_ms > 0:
        renderer.position_ms = 0
    renderer.state, renderer.since = "playing", now
    return _soap("AVTransport", "Play", {})


async def _pause(state, zone, renderer, args, now, transport):
    if renderer.state == "playing":
        renderer.position_ms, renderer.state, renderer.since = renderer.position(now), "paused", now
    return _soap("AVTransport", "Pause", {})


async def _stop(state, zone, renderer, args, now, transport):
    if renderer.uri is not None:
        renderer.position_ms, renderer.state, renderer.since = 0, "stopped", now
    return _soap("AVTransport", "Stop", {})


async def _seek(state, zone, renderer, args, now, transport):
    if args.get("Unit") != "REL_TIME":
        return _fault(710, "Seek mode not supported")
    renderer.position_ms, renderer.since = _parse_time(args["Target"]), now
    return _soap("AVTransport", "Seek", {})


async def _transport_info(state, zone, renderer, args, now, transport):
    return _soap(
        "AVTransport",
        "GetTransportInfo",
        {
            "CurrentTransportState": STATES[renderer.state],
            "CurrentTransportStatus": "OK",
            "CurrentSpeed": "1",
        },
    )


async def _position_info(state, zone, renderer, args, now, transport):
    return _soap(
        "AVTransport",
        "GetPositionInfo",
        {
            "Track": "1" if renderer.uri else "0",
            "TrackDuration": _clock_time(renderer.duration_ms),
            "TrackMetaData": renderer.metadata,
            "TrackURI": renderer.uri or "",
            "RelTime": _clock_time(renderer.position(now)),
            "AbsTime": _clock_time(renderer.position(now)),
            "RelCount": "2147483647",
            "AbsCount": "2147483647",
        },
    )


async def _media_info(state, zone, renderer, args, now, transport):
    return _soap(
        "AVTransport",
        "GetMediaInfo",
        {
            "NrTracks": "1" if renderer.uri else "0",
            "MediaDuration": _clock_time(renderer.duration_ms),
            "CurrentURI": renderer.uri or "",
            "CurrentURIMetaData": renderer.metadata,
        },
    )


async def _get_volume(state, zone, renderer, args, now, transport):
    return _soap("RenderingControl", "GetVolume", {"CurrentVolume": renderer.volume})


async def _set_volume(state, zone, renderer, args, now, transport):
    renderer.volume = int(args["DesiredVolume"])
    for udn in zone.rooms:
        state.rooms[udn].volume = renderer.volume
    return _soap("RenderingControl", "SetVolume", {})


async def _get_mute(state, zone, renderer, args, now, transport):
    return _soap("RenderingControl", "GetMute", {"CurrentMute": int(renderer.muted)})


async def _set_mute(state, zone, renderer, args, now, transport):
    renderer.muted = args["DesiredMute"] in ("1", "true")
    return _soap("RenderingControl", "SetMute", {})


def _room(state: State, zone: Zone, args: dict[str, str]) -> Room | None:
    udn = args.get("Room", "")
    return state.rooms.get(udn) if udn in zone.rooms else None


async def _get_room_volume(state, zone, renderer, args, now, transport):
    room = _room(state, zone, args)
    if room is None:
        return _fault(402, "Invalid Args")
    return _soap("RenderingControl", "GetRoomVolume", {"CurrentVolume": room.volume})


async def _set_room_volume(state, zone, renderer, args, now, transport):
    room = _room(state, zone, args)
    if room is None:
        return _fault(402, "Invalid Args")
    room.volume = int(args["DesiredVolume"])
    return _soap("RenderingControl", "SetRoomVolume", {})


async def _get_room_mute(state, zone, renderer, args, now, transport):
    room = _room(state, zone, args)
    if room is None:
        return _fault(402, "Invalid Args")
    return _soap("RenderingControl", "GetRoomMute", {"CurrentMute": int(room.muted)})


async def _set_room_mute(state, zone, renderer, args, now, transport):
    room = _room(state, zone, args)
    if room is None:
        return _fault(402, "Invalid Args")
    room.muted = args["DesiredMute"] in ("1", "true")
    return _soap("RenderingControl", "SetRoomMute", {})


async def _protocol_info(state, zone, renderer, args, now, transport):
    return _soap(
        "ConnectionManager", "GetProtocolInfo", {"Source": "", "Sink": ",".join(state.sink)}
    )


_HANDLERS = {
    ("AVTransport", "SetAVTransportURI"): _set_uri,
    ("AVTransport", "Play"): _play,
    ("AVTransport", "Pause"): _pause,
    ("AVTransport", "Stop"): _stop,
    ("AVTransport", "Seek"): _seek,
    ("AVTransport", "GetTransportInfo"): _transport_info,
    ("AVTransport", "GetPositionInfo"): _position_info,
    ("AVTransport", "GetMediaInfo"): _media_info,
    ("RenderingControl", "GetVolume"): _get_volume,
    ("RenderingControl", "SetVolume"): _set_volume,
    ("RenderingControl", "GetMute"): _get_mute,
    ("RenderingControl", "SetMute"): _set_mute,
    ("RenderingControl", "GetRoomVolume"): _get_room_volume,
    ("RenderingControl", "SetRoomVolume"): _set_room_volume,
    ("RenderingControl", "GetRoomMute"): _get_room_mute,
    ("RenderingControl", "SetRoomMute"): _set_room_mute,
    ("ConnectionManager", "GetProtocolInfo"): _protocol_info,
}


def main() -> None:
    import json

    import uvicorn

    parser = argparse.ArgumentParser(description="Fake Raumfeld host (tests only)")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=PORT)
    parser.add_argument(
        "--setup",
        default=os.environ.get("ANTHOLOGY_FAKE_RAUMFELD_SETUP", ""),
        help="JSON file with rooms and zones (as for POST /test/setup)",
    )
    options = parser.parse_args()
    app = create_app()
    if options.setup:
        with open(options.setup, encoding="utf-8") as file:
            body = json.load(file)
        state: State = app.state.fake
        state.rooms = {room["udn"]: Room(room["udn"], room["name"]) for room in body["rooms"]}
        state.zones = {
            zone["udn"]: Zone(udn=zone["udn"], rooms=list(zone["rooms"]))
            for zone in body.get("zones", [])
        }
    uvicorn.run(app, host=options.host, port=options.port)
