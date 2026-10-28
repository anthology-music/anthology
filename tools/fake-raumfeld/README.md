# Fake Raumfeld host

A Raumfeld host as Anthology's Raumfeld adapter sees it (`docs/architecture/raumfeld.md`): the
host's configuration service (`getZones` with `updateID` long polling, `connectRoomToZone`,
`dropRoomJob`, `listDevices`) and one virtual UPnP media renderer per zone (AVTransport,
RenderingControl with room volumes, ConnectionManager). No real speakers are involved: the
position advances with a simulated clock, and `Play` reads the first bytes of the track's URL
with a range request, as speakers do.

For tests and development only; it is never part of an image. The server tests mount it in
process; the end-to-end tests start it on a port and point `ANTHOLOGY_RAUMFELD_HOSTS` at it.

```
uv run anthology-fake-raumfeld --port 47365 --setup rooms.json
```

`rooms.json` (or `ANTHOLOGY_FAKE_RAUMFELD_SETUP`) has the shape of `POST /test/setup`.

| Test endpoint | Meaning |
|---|---|
| `POST /test/setup` | `{"rooms": [{"udn", "name"}], "zones": [{"udn", "rooms": [...]}], "sink": [...]}` |
| `POST /test/advance` | `{"seconds": n}` moves the clock forward |
| `POST /test/offline` | `{"offline": true}` makes the host answer 503 |
| `POST /test/foreign` | `{"zone": udn}` lets "the Raumfeld app" play a radio station |
| `GET /test/state` | zones, renderers, room volumes, received requests and media fetches |
