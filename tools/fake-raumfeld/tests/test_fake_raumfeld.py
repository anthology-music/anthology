"""The fake Raumfeld host: configuration service, zone renderers and the simulated clock."""

import asyncio

import httpx
from fastapi import FastAPI, Request, Response

from anthology_fake_raumfeld.app import create_app

SETUP = {
    "rooms": [
        {"udn": "uuid:living", "name": "Living room"},
        {"udn": "uuid:kitchen", "name": "Kitchen"},
        {"udn": "uuid:bath", "name": "Bath"},
    ],
    "zones": [{"udn": "uuid:zone-a", "rooms": ["uuid:living"]}],
}
DIDL = (
    '<DIDL-Lite xmlns="urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/"><item>'
    '<res duration="0:00:10.000">x</res></item></DIDL-Lite>'
)


def media() -> tuple[FastAPI, list[str]]:
    seen: list[str] = []
    app = FastAPI()

    @app.get("/track")
    async def track(request: Request) -> Response:
        seen.append(request.headers.get("range", ""))
        return Response(b"x" * 1024, status_code=206)

    return app, seen


def client(app: FastAPI) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://raumfeld")


def soap(action: str, service: str = "AVTransport", **args) -> tuple[dict, str]:
    kind = f"urn:schemas-upnp-org:service:{service}:1"
    body = "".join(f"<{key}>{value}</{key}>" for key, value in args.items())
    envelope = (
        '<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/"><s:Body>'
        f'<u:{action} xmlns:u="{kind}"><InstanceID>0</InstanceID>{body}</u:{action}>'
        "</s:Body></s:Envelope>"
    )
    return {"SOAPACTION": f'"{kind}#{action}"', "Content-Type": "text/xml"}, envelope


async def call(host: httpx.AsyncClient, zone: str, action: str, service="AVTransport", **args):
    headers, body = soap(action, service, **args)
    return await host.post(f"/zones/{zone}/{service}/control", headers=headers, content=body)


async def test_zones_long_poll_and_grouping() -> None:
    async with client(create_app()) as host:
        await host.post("/test/setup", json=SETUP)
        first = await host.get("/getZones")
        update_id = first.headers["updateID"]
        waiting = asyncio.create_task(host.get("/getZones", headers={"updateID": update_id}))
        await asyncio.sleep(0.05)
        assert not waiting.done()
        await host.get(
            "/connectRoomToZone", params={"roomUDN": "uuid:kitchen", "zoneUDN": "uuid:zone-a"}
        )
        changed = await waiting
        await host.get("/connectRoomToZone", params={"roomUDN": "uuid:bath"})
        await host.get("/dropRoomJob", params={"roomUDN": "uuid:kitchen"})
        state = (await host.get("/test/state")).json()
        devices = await host.get("/listDevices")

    assert "<unassignedRooms>" in first.text and 'name="Kitchen"' in first.text
    assert int(changed.headers["updateID"]) > int(update_id)
    assert 'udn="uuid:kitchen"' in changed.text.split("</zones>")[0]
    assert state["zones"]["uuid:zone-a"]["rooms"] == ["uuid:living"]
    assert [zone["rooms"] for zone in state["zones"].values()][1] == ["uuid:bath"]
    assert devices.text.count("<device ") == 2


async def test_playing_fetches_the_stream_and_ends_with_the_track() -> None:
    server, seen = media()
    app = create_app(media_transport=httpx.ASGITransport(app=server))
    async with client(app) as host:
        await host.post("/test/setup", json=SETUP)
        description = await host.get("/zones/uuid:zone-a/description.xml")
        await call(
            host,
            "uuid:zone-a",
            "SetAVTransportURI",
            CurrentURI="http://anthology/track",
            CurrentURIMetaData=DIDL.replace("<", "&lt;").replace(">", "&gt;"),
        )
        await call(host, "uuid:zone-a", "Play", Speed="1")
        await host.post("/test/advance", json={"seconds": 4})
        position = await call(host, "uuid:zone-a", "GetPositionInfo")
        await call(host, "uuid:zone-a", "Pause")
        paused = await call(host, "uuid:zone-a", "GetTransportInfo")
        await call(host, "uuid:zone-a", "Seek", Unit="REL_TIME", Target="0:00:08")
        await call(host, "uuid:zone-a", "Play", Speed="1")
        await host.post("/test/advance", json={"seconds": 3})
        ended = await call(host, "uuid:zone-a", "GetTransportInfo")
        sink = await call(host, "uuid:zone-a", "GetProtocolInfo", "ConnectionManager")

    assert "/zones/uuid:zone-a/AVTransport/control" in description.text
    assert seen == ["bytes=0-1023"]
    assert "<RelTime>0:00:04</RelTime>" in position.text
    assert "PAUSED_PLAYBACK" in paused.text
    assert "STOPPED" in ended.text
    assert "audio/flac" in sink.text


async def test_room_volume_foreign_source_and_offline() -> None:
    async with client(create_app()) as host:
        await host.post("/test/setup", json=SETUP)
        await host.get(
            "/connectRoomToZone", params={"roomUDN": "uuid:kitchen", "zoneUDN": "uuid:zone-a"}
        )
        await call(
            host,
            "uuid:zone-a",
            "SetRoomVolume",
            "RenderingControl",
            Room="uuid:kitchen",
            DesiredVolume="12",
        )
        await host.post("/test/foreign", json={"zone": "uuid:zone-a"})
        media_info = await call(host, "uuid:zone-a", "GetMediaInfo")
        await host.post("/test/offline", json={"offline": True})
        offline = await host.get("/getZones")
        state = (await host.get("/test/state")).json()

    assert state["rooms"]["uuid:kitchen"]["volume"] == 12
    assert state["rooms"]["uuid:living"]["volume"] == 30
    assert "radio.invalid" in media_info.text
    assert offline.status_code == 503
    assert {
        "method": "POST",
        "path": "/zones/uuid:zone-a/RenderingControl/control",
        "action": "SetRoomVolume",
    } in state["requests"]
