# Proposal

## Why

Milestone 3 promises playback on the multi-room system: a user picks a room or zone, the phone becomes a remote control, and the music keeps playing when the phone is closed. The `playback` spec states this (output adapters, output picker, server-side control, Raumfeld support), but only "this device" exists. Two open tasks wait for it: `playable-delivery-format` 3.3 (formats of an output) and `signed-media-urls` 3.2 (URLs bound to an output).

## What Changes

- **Output adapter interface** in the core, discovered through the `anthology.outputs` entry point group (ADR 0011): systems, zones and rooms, playback commands, volume, grouping, supported formats.
- **Raumfeld adapter**, built into the server (MIT, no new dependency):
  - finds the Raumfeld host by SSDP when the pod can reach multicast (host networking), or by an address the admin enters;
  - follows the host's zone configuration;
  - controls zones through their UPnP media renderers (AVTransport, RenderingControl, ConnectionManager) with DIDL-Lite metadata of the track's context.
- **Zone play queues:**
  - every zone has one shared queue on the server;
  - choosing a zone in the output picker hands the device's queue to the zone (entries, current entry, position);
  - the server plays it track by track and keeps going when every client is closed;
  - while a device has a zone selected, its queue commands act on the zone's queue (remote control);
  - choosing "this device" again takes playback back: the zone stops and its queue and position return to the device.
- **Zone management:**
  - rooms join and leave zones, and a room alone forms a new zone;
  - volume and mute per zone and per room.
- **Delivery to outputs:**
  - the original when the zone reports its format as playable, otherwise a compatibility transcode;
  - signed URLs bound to the zone, issued when the server hands a track over.
- **Fake Raumfeld service** in `tools/fake-raumfeld/` (host configuration service and zone renderers with a simulated clock that fetches the media URLs) for tests and end-to-end runs.
- **Client:**
  - output picker in the player bar;
  - remote-control mode showing the zone's state;
  - zone and room management with volumes;
  - admin setting for Raumfeld host addresses.
- **Deployment:** `deploy/` documents host networking for discovery and the address alternative. This answers the roadmap question about rootless discovery.

## Capabilities

### New Capabilities

_None._

### Modified Capabilities

- `playback`: requirements for discovery and addresses, zone queues and handover, remote control, zone management, delivery to outputs; "Raumfeld support" made concrete.

## Impact

- **Domains:**
  - playback (server module `playback`, new package `playback/outputs/`);
  - transcoding (delivery decision reused with the zone's formats);
  - users (media grants for outputs).
- **Data model:**
  - new `OutputSystem`, `OutputZone` and `OutputRoom` rows, replacing the sketched `OutputDevice`;
  - `PlayQueue` belongs to either a user's device or a zone;
  - `UserDevice` gets the selected output.
- **API:**
  - `PUT /api/v1/playback/output` selects the output;
  - zone and room commands under `/api/v1/playback/zones/…`;
  - admin `…/playback/systems`;
  - stream `playback.outputs`;
  - the queue streams resolve to the zone queue while a zone is selected.
- **Other changes:**
  - `playable-delivery-format` 3.3 is done here;
  - `signed-media-urls` 3.2 is done here, and its output requirement changes from queue-length URLs to per-track URLs (see design).
- **Docs:** `docs/architecture/data-model.puml`, `docs/architecture/sync-protocol.md`, `docs/architecture/raumfeld.md` (new: protocol notes), `deploy/` README and Quadlet comments, `docs/roadmap.md` (open question answered), `server/AGENTS.md`.
- **Non-functional requirements:**
  - Outputs are few (a household has a handful of rooms), so their lists do not need paging.
  - Zone players poll their renderer once per second while playing; this never blocks a request.
- **License:** own SSDP and SOAP code on `asyncio` and `httpx`; no new dependency. The fake service is MIT and uses generated data only.
