"""The Raumfeld output adapter (spec: playback, Raumfeld support; protocol notes in
docs/architecture/raumfeld.md).

A Raumfeld host runs a configuration service on port 47365: ``getZones`` lists zones, their
rooms and the unassigned rooms and answers a request carrying the last ``updateID`` only when
the configuration changed (long polling); ``listDevices`` names the zones' virtual media
renderers; ``connectRoomToZone`` and ``dropRoomJob`` regroup rooms. Each zone is a UPnP media
renderer: AVTransport for playback, RenderingControl for the zone's and each room's volume,
ConnectionManager for the formats it plays.
"""

import asyncio
import contextlib
import logging
import re
from dataclasses import replace
from urllib.parse import urlsplit

import httpx

from anthology.core.config import Settings
from anthology.library.models import AudioFormat
from anthology.playback.outputs.base import (
    Listener,
    OutputAdapter,
    OutputError,
    RoomInfo,
    RoomRef,
    SystemSnapshot,
    TrackMetadata,
    Transport,
    TransportState,
    ZoneInfo,
    ZoneRef,
)
from anthology.playback.outputs.raumfeld import ssdp, upnp
from anthology.playback.outputs.raumfeld.didl import didl, duration

logger = logging.getLogger(__name__)

# Seconds between two searches for hosts.
DISCOVERY_SECONDS = 60
# The host holds a long poll for a while; give it more than that before giving up.
LONG_POLL_SECONDS = 60.0
REQUEST_SECONDS = 10.0
RETRY_SECONDS = 5.0
STATES = {
    "PLAYING": Transport.PLAYING,
    "PAUSED_PLAYBACK": Transport.PAUSED,
    "STOPPED": Transport.STOPPED,
    "NO_MEDIA_PRESENT": Transport.STOPPED,
    "TRANSITIONING": Transport.TRANSITIONING,
}
# A host name or IPv4 address, or an IPv6 address in brackets, with an optional port.
ADDRESS = re.compile(
    r"(?:[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?|\[[0-9A-Fa-f:.]+\])(?::\d{1,5})?"
)
# MIME types of the renderers' sink protocol info.
MIME_FORMATS = {
    "audio/flac": AudioFormat.FLAC,
    "audio/x-flac": AudioFormat.FLAC,
    "audio/mpeg": AudioFormat.MP3,
    "audio/mp3": AudioFormat.MP3,
    "audio/mp4": AudioFormat.AAC,
    "audio/x-m4a": AudioFormat.AAC,
    "audio/aac": AudioFormat.AAC,
    "audio/wav": AudioFormat.WAV,
    "audio/x-wav": AudioFormat.WAV,
    "audio/wave": AudioFormat.WAV,
    "audio/aiff": AudioFormat.AIFF,
    "audio/x-aiff": AudioFormat.AIFF,
    "audio/ogg": AudioFormat.VORBIS,
    "audio/x-ogg": AudioFormat.VORBIS,
    "audio/opus": AudioFormat.OPUS,
}


def formats(sink: str) -> frozenset[AudioFormat]:
    """Formats of a ``GetProtocolInfo`` sink list (``http-get:*:audio/flac:*,...``)."""
    found = set()
    for entry in sink.split(","):
        parts = entry.strip().split(":")
        if len(parts) >= 3 and parts[0] == "http-get":
            mime = parts[2].split(";")[0].strip().lower()
            if mime in MIME_FORMATS:
                found.add(MIME_FORMATS[mime])
    return frozenset(found)


def milliseconds(value: str) -> int:
    """``H:MM:SS`` (optionally with fractions) as milliseconds; 0 for ``NOT_IMPLEMENTED``."""
    try:
        hours, minutes, seconds = value.split(":")
        return int((int(hours) * 3600 + int(minutes) * 60 + float(seconds)) * 1000)
    except ValueError:
        return 0


def normalize(address: str) -> str:
    """``host`` or ``host:port`` → ``host:port`` (the configuration service's port)."""
    address = address.strip()
    if not ADDRESS.fullmatch(address):
        raise ValueError(f"not a host address: {address!r}")
    parts = urlsplit(f"//{address}")
    host = f"[{parts.hostname}]" if ":" in (parts.hostname or "") else parts.hostname
    return f"{host}:{parts.port or ssdp.CONFIG_PORT}"


class RaumfeldAdapter(OutputAdapter):
    name = "raumfeld"

    def __init__(
        self,
        settings: Settings,
        transport: httpx.AsyncBaseTransport | None = None,
        *,
        discovery: bool | None = None,
    ) -> None:
        self._transport = transport
        self._discovery = settings.output_discovery if discovery is None else discovery
        self.configured = tuple(
            normalize(address) for address in settings.raumfeld_hosts.split(",") if address.strip()
        )
        self._listener: Listener | None = None
        self._client: httpx.AsyncClient | None = None
        self._tasks: dict[str, asyncio.Task] = {}
        self._discovery_task: asyncio.Task | None = None
        # Description URL → device (control URLs).
        self._devices: dict[str, upnp.Device] = {}
        # Zone UDN → formats (they do not change while the zone exists).
        self._formats: dict[str, frozenset[AudioFormat]] = {}

    def normalize(self, address: str) -> str:
        return normalize(address)

    # --- lifecycle ------------------------------------------------------------------------

    @property
    def client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                transport=self._transport, timeout=REQUEST_SECONDS, follow_redirects=False
            )
        return self._client

    async def start(self, listener: Listener) -> None:
        self._listener = listener
        if self._discovery:
            self._discovery_task = asyncio.create_task(
                self._discover(), name="anthology-raumfeld-discovery"
            )

    async def stop(self) -> None:
        tasks = [*self._tasks.values()]
        if self._discovery_task is not None:
            tasks.append(self._discovery_task)
        for task in tasks:
            task.cancel()
        for task in tasks:
            with contextlib.suppress(asyncio.CancelledError):
                await task
        self._tasks.clear()
        self._discovery_task = None
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def _discover(self) -> None:
        while True:
            try:
                for address in await ssdp.search():
                    if self._listener is not None:
                        await self._listener.discovered(address, f"Raumfeld ({address})")
            except Exception:
                logger.warning("Raumfeld discovery failed", exc_info=True)
            await asyncio.sleep(DISCOVERY_SECONDS)

    async def watch(self, address: str) -> None:
        if address not in self._tasks:
            self._tasks[address] = asyncio.create_task(
                self._follow(address), name=f"anthology-raumfeld-{address}"
            )

    async def unwatch(self, address: str) -> None:
        task = self._tasks.pop(address, None)
        if task is not None:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task

    async def _follow(self, address: str) -> None:
        """Long-poll the host's zone configuration and report every change."""
        update_id: str | None = None
        while True:
            try:
                update_id, snapshot = await self._read(address, update_id)
            except OutputError as error:
                update_id = None
                await self._report(address, SystemSnapshot(reachable=False, reason=str(error)))
                await asyncio.sleep(RETRY_SECONDS)
                continue
            except Exception:
                logger.exception("following Raumfeld host %s failed", address)
                update_id = None
                await asyncio.sleep(RETRY_SECONDS)
                continue
            await self._report(address, snapshot)

    async def _report(self, address: str, snapshot: SystemSnapshot) -> None:
        if self._listener is not None:
            await self._listener.snapshot(address, snapshot)

    async def refresh(self, address: str) -> SystemSnapshot:
        try:
            _update_id, snapshot = await self._read(address, None)
        except OutputError as error:
            snapshot = SystemSnapshot(reachable=False, reason=str(error))
        await self._report(address, snapshot)
        return snapshot

    # --- the host's configuration ---------------------------------------------------------

    async def _host(self, address: str, path: str, **kwargs) -> httpx.Response:
        try:
            response = await self.client.get(f"http://{address}{path}", **kwargs)
        except httpx.TimeoutException as error:
            raise OutputError("no answer") from error
        except httpx.HTTPError as error:
            raise OutputError(f"unreachable ({error.__class__.__name__})") from error
        if response.status_code != 200:
            raise OutputError(f"HTTP {response.status_code}")
        return response

    async def _read(self, address: str, update_id: str | None) -> tuple[str | None, SystemSnapshot]:
        """The zone configuration (waiting for a change after ``update_id``) as a snapshot."""
        headers = {"updateID": update_id} if update_id is not None else {}
        timeout = LONG_POLL_SECONDS if update_id is not None else REQUEST_SECONDS
        response = await self._host(address, "/getZones", headers=headers, timeout=timeout)
        config = upnp.parse(response.content)
        devices = upnp.parse((await self._host(address, "/listDevices")).content)
        locations = {
            node.get("udn", ""): node.get("location", "") for node in devices.iter("device")
        }
        zones = []
        for node in config.iterfind("zones/zone"):
            udn = node.get("udn", "")
            rooms = tuple(_room(room) for room in node.iterfind("room"))
            location = locations.get(udn) or None
            zone = ZoneInfo(
                external_id=udn,
                name=" + ".join(room.name for room in rooms) or udn,
                rooms=rooms,
                control=location,
            )
            if location:
                zone = await self._details(zone, location)
            zones.append(zone)
        free = tuple(_room(room) for room in config.iterfind("unassignedRooms/room"))
        snapshot = SystemSnapshot(
            reachable=True, name=f"Raumfeld ({address})", zones=tuple(zones), rooms=free
        )
        return response.headers.get("updateID"), snapshot

    async def _details(self, zone: ZoneInfo, location: str) -> ZoneInfo:
        """Formats and volumes of a zone and its rooms; a renderer that does not answer
        leaves them unknown."""
        try:
            device = await self._device(location)
            if zone.external_id not in self._formats:
                info = await self._call(device, upnp.CONNECTION_MANAGER, "GetProtocolInfo", {})
                self._formats[zone.external_id] = formats(info.get("Sink", ""))
            volume = await self._call(
                device, upnp.RENDERING_CONTROL, "GetVolume", {"InstanceID": 0, "Channel": "Master"}
            )
            mute = await self._call(
                device, upnp.RENDERING_CONTROL, "GetMute", {"InstanceID": 0, "Channel": "Master"}
            )
            rooms = []
            for room in zone.rooms:
                arguments = {"InstanceID": 0, "Room": room.external_id}
                room_volume = await self._call(
                    device, upnp.RENDERING_CONTROL, "GetRoomVolume", arguments
                )
                room_mute = await self._call(
                    device, upnp.RENDERING_CONTROL, "GetRoomMute", arguments
                )
                rooms.append(
                    replace(
                        room,
                        volume=_number(room_volume.get("CurrentVolume")),
                        muted=room_mute.get("CurrentMute") in ("1", "true"),
                    )
                )
        except OutputError:
            logger.info("zone %s does not answer", zone.external_id, exc_info=True)
            return zone
        return replace(
            zone,
            rooms=tuple(rooms),
            formats=self._formats[zone.external_id],
            volume=_number(volume.get("CurrentVolume")),
            muted=mute.get("CurrentMute") in ("1", "true"),
        )

    # --- zone renderers -------------------------------------------------------------------

    async def _device(self, location: str) -> upnp.Device:
        device = self._devices.get(location)
        if device is None:
            try:
                response = await self.client.get(location)
            except httpx.HTTPError as error:
                raise OutputError(f"description: {error.__class__.__name__}") from error
            if response.status_code != 200:
                raise OutputError(f"description: HTTP {response.status_code}")
            device = upnp.device(location, response.content)
            self._devices[location] = device
        return device

    async def _call(self, device: upnp.Device, service: str, action: str, arguments) -> dict:
        control = device.controls.get(service)
        if control is None:
            raise OutputError(f"{action}: the renderer has no {service}")
        return await upnp.call(self.client, control, service, action, arguments)

    async def _renderer(self, zone: ZoneRef) -> upnp.Device:
        if not zone.control:
            raise OutputError("the zone has no renderer")
        return await self._device(zone.control)

    async def _av(self, zone: ZoneRef, action: str, **arguments) -> dict:
        device = await self._renderer(zone)
        return await self._call(device, upnp.AV_TRANSPORT, action, {"InstanceID": 0, **arguments})

    async def play(
        self, zone: ZoneRef, uri: str, metadata: TrackMetadata, start_ms: int = 0
    ) -> None:
        await self._av(
            zone, "SetAVTransportURI", CurrentURI=uri, CurrentURIMetaData=didl(uri, metadata)
        )
        await self._av(zone, "Play", Speed="1")
        if start_ms > 0:
            await self.seek(zone, start_ms)

    async def pause(self, zone: ZoneRef) -> None:
        await self._av(zone, "Pause")

    async def resume(self, zone: ZoneRef) -> None:
        await self._av(zone, "Play", Speed="1")

    async def stop_zone(self, zone: ZoneRef) -> None:
        await self._av(zone, "Stop")

    async def seek(self, zone: ZoneRef, position_ms: int) -> None:
        target = duration(position_ms).split(".")[0]
        await self._av(zone, "Seek", Unit="REL_TIME", Target=target)

    async def state(self, zone: ZoneRef) -> TransportState:
        info = await self._av(zone, "GetTransportInfo")
        media = await self._av(zone, "GetMediaInfo")
        position = await self._av(zone, "GetPositionInfo")
        return TransportState(
            transport=STATES.get(info.get("CurrentTransportState", ""), Transport.STOPPED),
            position_ms=milliseconds(position.get("RelTime", "")),
            uri=media.get("CurrentURI") or None,
        )

    # --- volumes and grouping -------------------------------------------------------------

    async def set_volume(self, zone: ZoneRef, volume: int | None, muted: bool | None) -> None:
        device = await self._renderer(zone)
        base = {"InstanceID": 0, "Channel": "Master"}
        if volume is not None:
            await self._call(
                device, upnp.RENDERING_CONTROL, "SetVolume", {**base, "DesiredVolume": volume}
            )
        if muted is not None:
            await self._call(
                device, upnp.RENDERING_CONTROL, "SetMute", {**base, "DesiredMute": int(muted)}
            )

    async def set_room_volume(self, room: RoomRef, volume: int | None, muted: bool | None) -> None:
        if room.zone is None:
            raise OutputError("the room is in no zone")
        device = await self._renderer(room.zone)
        base = {"InstanceID": 0, "Room": room.external_id}
        if volume is not None:
            await self._call(
                device, upnp.RENDERING_CONTROL, "SetRoomVolume", {**base, "DesiredVolume": volume}
            )
        if muted is not None:
            await self._call(
                device, upnp.RENDERING_CONTROL, "SetRoomMute", {**base, "DesiredMute": int(muted)}
            )

    async def group(self, room: RoomRef, zone: ZoneRef | None) -> None:
        params = {"roomUDN": room.external_id}
        if zone is not None:
            params["zoneUDN"] = zone.external_id
        await self._host(room.address, "/connectRoomToZone", params=params)

    async def ungroup(self, room: RoomRef) -> None:
        await self._host(room.address, "/dropRoomJob", params={"roomUDN": room.external_id})


def _room(node) -> RoomInfo:
    return RoomInfo(external_id=node.get("udn", ""), name=node.get("name", ""))


def _number(value: str | None) -> int | None:
    return int(value) if value is not None and value.isdigit() else None
