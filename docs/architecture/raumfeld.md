# Raumfeld protocol notes

How Anthology's Raumfeld output adapter (`server/anthology/playback/outputs/raumfeld/`) talks to
Teufel Raumfeld speakers. Behavior: `openspec/specs/playback/spec.md` (Raumfeld support,
Output discovery and addresses, Zone play queue, Delivery to outputs). The fake host in
`tools/fake-raumfeld/` implements exactly what is listed here; tests never reach real speakers.

## Sources

Raumfeld has no published API documentation. These notes follow:

- the UPnP Device Architecture 1.0 and the UPnP AV specifications (MediaRenderer 1.0,
  AVTransport 1.0, RenderingControl 1.0, ConnectionManager 1.0, ContentDirectory 1.0 for
  DIDL-Lite), which the zone renderers implement;
- the host's configuration service as used by community projects that control Raumfeld
  systems, such as `node-raumkernel` and `pyfeld`.

Every request below must be checked against real speakers before the change `raumfeld-output`
is archived (its workflow follow-up). Correct this file and the fake together when they differ.

## Discovery

- An SSDP `M-SEARCH` (multicast `239.255.255.250:1900`) with
  `ST: urn:schemas-raumfeld-com:device:ConfigDevice:1`, at start and every 60 seconds
  (`ANTHOLOGY_OUTPUT_DISCOVERY`, default on).
- The answer's `LOCATION` names the host. The adapter keeps `host:47365`, the port of the
  configuration service.
- Without multicast (a container without host networking) no answer arrives. Admins then enter
  the host's address (`POST /api/v1/playback/systems`), or the installation sets
  `ANTHOLOGY_RAUMFELD_HOSTS`.

## Host configuration service (port 47365)

| Request | Use |
|---|---|
| `GET /getZones` | Zones with their rooms, and the unassigned rooms (XML below). The answer carries an `updateID` header. |
| `GET /getZones` with request header `updateID: <last>` | Long poll: the host answers when the configuration changed (or after a timeout). The adapter keeps one open per host, so zone changes from the Raumfeld app arrive at once. |
| `GET /listDevices` | Devices with `udn`, `type` and `location`; a zone's virtual media renderer has the zone's UDN, and its `location` is the renderer's description. |
| `GET /connectRoomToZone?roomUDN=…&zoneUDN=…` | Moves a room into a zone; without `zoneUDN`, the room forms a new zone of its own. |
| `GET /dropRoomJob?roomUDN=…` | Takes a room out of its zone (it becomes unassigned). |

```xml
<zoneConfig>
  <zones>
    <zone udn="uuid:…">
      <room udn="uuid:…" name="Living room"><renderer udn="uuid:…" name="…"/></room>
    </zone>
  </zones>
  <unassignedRooms>
    <room udn="uuid:…" name="Bath">…</room>
  </unassignedRooms>
</zoneConfig>
```

A zone has no name of its own: Anthology names it after its rooms (`Living room + Kitchen`).
A non-200 answer or no answer makes the system unreachable, with the reason
(`HTTP 503`, `no answer`, `unreachable (ConnectError)`). Its zones and rooms are then shown
offline, and playback on them is refused.

## Zone renderers (UPnP MediaRenderer)

Control URLs come from the renderer's description (`serviceList`, resolved against `URLBase`
or the description's URL). SOAP actions as sent, all with `InstanceID` 0:

| Service | Action | Arguments | Use |
|---|---|---|---|
| ConnectionManager | `GetProtocolInfo` | – | `Sink`: the formats the zone plays (`http-get:*:<mime>:*`), read once per zone |
| AVTransport | `SetAVTransportURI` | `CurrentURI`, `CurrentURIMetaData` (DIDL-Lite) | hand a track to the zone |
| AVTransport | `Play` | `Speed` = 1 | start, or resume after a pause |
| AVTransport | `Pause`, `Stop` | – | pause; stop when playback is taken back to a device |
| AVTransport | `Seek` | `Unit` = `REL_TIME`, `Target` = `H:MM:SS` | the handover's position, and seeks |
| AVTransport | `GetTransportInfo` | – | `CurrentTransportState` (`PLAYING`, `PAUSED_PLAYBACK`, `STOPPED`, `TRANSITIONING`, `NO_MEDIA_PRESENT`) |
| AVTransport | `GetMediaInfo` | – | `CurrentURI`: Anthology's URL, or something else when the Raumfeld app plays another source |
| AVTransport | `GetPositionInfo` | – | `RelTime`: the position |
| RenderingControl | `GetVolume`, `SetVolume` | `Channel` = `Master`, `DesiredVolume` | zone volume (0–100) |
| RenderingControl | `GetMute`, `SetMute` | `Channel` = `Master`, `DesiredMute` | zone mute |
| RenderingControl | `GetRoomVolume`, `SetRoomVolume` | `Room` (room UDN), `DesiredVolume` | one room's volume (Raumfeld extension) |
| RenderingControl | `GetRoomMute`, `SetRoomMute` | `Room`, `DesiredMute` | one room's mute (Raumfeld extension) |

MIME types of the sink list map to formats: `audio/flac`, `audio/x-flac` → FLAC;
`audio/mpeg` → MP3; `audio/mp4`, `audio/x-m4a`, `audio/aac` → AAC; `audio/wav`, `audio/x-wav`,
`audio/wave` → WAV; `audio/aiff`, `audio/x-aiff` → AIFF; `audio/ogg` → Vorbis; `audio/opus`
→ Opus. A format the zone does not report gets a compatibility transcode.

## Metadata (DIDL-Lite)

One `item` of class `object.item.audioItem.musicTrack` with the tags of the track's context:
`dc:title`, `dc:creator` and `upnp:artist`, `upnp:album`, `upnp:artist role="AlbumArtist"`,
`upnp:originalTrackNumber`, and a `res` with `protocolInfo` (`http-get:*:<mime>:*`), the
`duration` (`H:MM:SS.mmm`) and the URL. A track played from a compilation shows the
compilation. Covers come with change `covers`.

## How Anthology plays a zone

- **Server-driven:** the zone player in the server (one process per zone, lease on the zone
  row) hands over one track at a time.
- **Following the zone:** while the zone plays, the player reads `GetTransportInfo`,
  `GetMediaInfo` and `GetPositionInfo` once per second.
- **Track ends:** a `STOPPED` zone after it played, or 10 seconds after the handover, finished
  the track. The next entry follows, with a short gap; gapless playback through
  `SetNextAVTransportURI` is not used yet.
- **Foreign source:** a `CurrentURI` that is not the handed-over URL is another source, so the
  zone queue pauses.
- **Media URLs:** each URL is bound to the zone and valid for the track's duration plus one
  hour (at most 24 hours). A track resumed after its URL expired is handed over again with a
  new URL at its position.
- **URL base:** speakers fetch from `ANTHOLOGY_OUTPUT_MEDIA_URL` (e.g.
  `http://192.168.1.10:8400`), or from this host's address on the route to the speakers with
  `ANTHOLOGY_PORT` (default 8400).
- **Volume changes from the Raumfeld app** appear with the next zone configuration change.
  Following them live (GENA events) can come later.
