# Design

## Context

- **What exists:**
  - one play queue per user and device on the server (`playback`);
  - signed media URLs with a revocation check (`core.media_urls`, `api.deps.media_grant`);
  - the delivery decision as a pure function (`transcoding.delivery.decide`);
  - service monitors for optional services (`core.services`).
- **Raumfeld (Teufel) is UPnP with additions:**
  - a host device (`urn:schemas-raumfeld-com:device:ConfigDevice:1`) runs a configuration web service on port 47365;
  - `getZones` lists zones, their rooms and the unassigned rooms, and answers long polls with an `updateID` header;
  - `connectRoomToZone` and `dropRoomJob` change zones;
  - every zone is a virtual UPnP MediaRenderer with AVTransport, RenderingControl (with room-level `SetRoomVolume` and `SetRoomMute`) and ConnectionManager (`GetProtocolInfo`).
- **Rootless Podman:** without host networking, the pod cannot receive multicast (ADR 0005).

Decided with the maintainer:
- discovery by SSDP plus a manual address;
- every zone has its own queue, which takes over the device's queue;
- full zone management;
- two pull requests.

## Goals / Non-Goals

**Goals:**
- Play the library on Raumfeld zones, track by track, controlled by the server, and keep playing with every client closed.
- Manage zones, rooms and volumes from Anthology.
- Keep the core free of Raumfeld specifics (adapter interface), so Sonos or Chromecast can follow.

**Non-Goals:**
- Gapless playback between tracks on Raumfeld (`SetNextAVTransportURI`): later, as an optimization.
- Raumfeld's own sources (radio, line-in): the zone stops following Anthology's queue when they play.
- Audio-only playback of videos: comes with video (milestone 4).
- Covers in DIDL-Lite: come with change `covers`.

## Decisions

### Adapter interface

`playback/outputs/base.py` defines `OutputAdapter`, registered under the entry point group `anthology.outputs`. An adapter:
- starts and stops;
- reports systems, zones and rooms as plain data (`OutputSnapshot`);
- offers per-zone commands: `play(uri, metadata, start_ms)`, `pause`, `resume`, `stop`, `seek`, `state()` → transport state, position and the URI playing;
- offers volume and mute per zone and per room, and `group(room, zone | None)` / `ungroup(room)`;
- reports `supported_formats(zone)`.

The registry (`playback/outputs/registry.py`) loads the adapters, persists their snapshots and runs the zone players. Core code calls the interface only. The Raumfeld adapter lives in `playback/outputs/raumfeld/` and is registered in `server/pyproject.toml` like an external one would be.

Alternative considered: a separate service per output system, like source services. Rejected for Raumfeld: no license reason (own code, MIT), and control needs low latency and LAN access, which the server has anyway.

### Discovery and addresses

- **Discovery:**
  - an SSDP M-SEARCH for the ConfigDevice runs at start and every 60 seconds (`ANTHOLOGY_OUTPUT_DISCOVERY`, default on);
  - without multicast it finds nothing, which is harmless;
  - discovered hosts are `OutputSystem` rows with origin `discovered`.
- **Manual addresses:** admins add host addresses (`POST /api/v1/playback/systems`, origin `manual`), and `ANTHOLOGY_RAUMFELD_HOSTS` seeds them for containers.
- **Health:** each system's state (online, unreachable with reason) is shown like a service's health.
- **Zone configuration:** for every reachable host the adapter long-polls `getZones` and maps it to `OutputZone` and `OutputRoom` rows. Renderer locations come from the host's device list (`listDevices`).

`deploy/` documents both ways: `Network=host` in the pod for discovery, or the address in the settings.

### Zone queues and handover

`PlayQueue` belongs either to a user's device (`user_id`, `device_id`) or to a zone (`output_zone_id`, unique); a check constraint enforces exactly one.

A device's selected output is `UserDevice.output_zone_id`:
- the queue REST endpoints and the queue streams resolve "my queue" to the zone queue while it is set. The client is then a remote control with the same commands;
- choosing a zone copies the device queue into the zone queue (replacing it, entries in order, current entry, position, playing) and starts the zone player; a zone that plays already keeps its queue, and the device joins it (Shared zone);
- choosing "this device" copies the zone queue back to the device, paused at the zone's position, and stops the zone.

Several users may select the same zone: they all control the one queue (a household speaker). Every signed-in user may play on zones, change volumes and group rooms. Adding or removing system addresses is for admins only.

Alternative considered: the queue stays with the user's device and the zone is only its target. Rejected by the maintainer: a zone shared by a family needs one queue.

### Zone player

One task per playing zone (`playback/outputs/player.py`):
- it hands the current entry to the renderer (`SetAVTransportURI` with DIDL-Lite of the track's context, then `Play`, and `Seek` when it resumes at a position);
- it polls transport state and position once per second while playing;
- it writes the position to the queue at most every 5 seconds and on every state change;
- it starts the next entry when the track ends: the zone reports `STOPPED` after it was seen playing, or 10 seconds after the handover (before that, it may still be loading).
- Entries that cannot be delivered (no original, failed transcode) are skipped and marked, like on a device.
- If the renderer plays a URI that is not Anthology's (the Raumfeld app started something else), the zone queue pauses and keeps its position.

With several server processes, one process runs a zone's player. It holds a lease on the zone row (`player_owner`, `player_lease_until`, renewed every 10 seconds, taken over with a compare-and-swap after expiry), like job leases.

### Delivery and URLs

- **Format:**
  - the zone's formats come from `GetProtocolInfo` (sink list, mapped to `AudioFormat`) and are stored on the zone;
  - `decide(original, BitrateSetting.ORIGINAL, zone_formats)` chooses the original or a compatibility transcode, which the player prepares one entry ahead.
- **Signed URL:**
  - bound to user and target, where the target is the zone. The user is the one who handed the queue over, or who last changed it;
  - issued when the player hands the track over;
  - valid for the track's duration plus one hour, capped at 24 hours;
  - a track resumed after its URL expired is handed over again with a new URL at the paused position.
- **Revocation:** `media_grant` accepts a zone target when the zone exists and the user is active.
- **URL base:** the speakers fetch from `ANTHOLOGY_OUTPUT_MEDIA_URL`; without it, from this host's address on the route to the system and `ANTHOLOGY_PORT` (8400). Behind port forwarding (a rootless pod) the URL has to be set.

This replaces "valid for the handed-over queue, refreshed before expiry" in `signed-media-urls`. Because the server hands over each track itself, no URL has to outlive its track. The change's requirement and task 3.2 are reworded accordingly.

### Fake Raumfeld

`tools/fake-raumfeld/` (MIT, FastAPI, like `fake-source-service`):
- the host configuration service: `getZones` with `updateID` long polling, `connectRoomToZone`, `dropRoomJob`, `listDevices`;
- device descriptions and SOAP control for one virtual renderer per zone;
- a simulated clock: `Play` fetches the first bytes of the URI with a range request, as speakers do, and advances the position; the track ends at its DIDL-Lite duration;
- test endpoints to set rooms, speed up time and read the requests it made.

Server tests use it in process (ASGI transport). The end-to-end server starts it on a port and configures it with `ANTHOLOGY_RAUMFELD_HOSTS`. SSDP is tested with recorded datagrams.

### Progressive loading

Outputs are few: `playback.outputs` sends all systems, zones and rooms as one list with deltas. The zone queue reuses the queue streams, which page already.

## Risks / Trade-offs

- **No real hardware in CI.** The fake follows the documented protocol, and the protocol notes in `docs/architecture/raumfeld.md` name their sources. The maintainer checks against real speakers before the archive.
- **Polling once per second per playing zone.** A handful of zones is cheap. GENA events can replace polling later without changing behavior.
- **Track changes have a short gap.** Accepted for now; see Non-Goals.

## Migration Plan

Migration `0022`:
- adds the output tables;
- makes `play_queues.user_id` and `device_id` nullable and adds `output_zone_id` with a check constraint;
- adds `user_devices.output_zone_id`.

Existing queues stay device queues.
