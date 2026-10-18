# Sync protocol

One WebSocket per client carries all list and status subscriptions (ADR 0003, `openspec/specs/sync-protocol/spec.md`). Media never uses the WebSocket: audio is served over HTTP with range requests, video over HLS, both through signed URLs (ADR 0015).

Status: draft – nothing built yet. The normative message schema is generated from the server's pydantic models; client types live in `packages/api-types`.

## Envelope

```json
{ "type": "delta", "sub": "s12", "seq": 184467, "data": { } }
```

| Field | Required | Meaning |
|---|---|---|
| `type` | always | message type (see below) |
| `sub` | subscription-bound messages | subscription ID chosen by the client |
| `seq` | messages carrying a change | global change sequence number |
| `data` | per type | payload |

Clients and servers ignore unknown optional fields and unknown message types they do not need; such additions do not change the protocol version.

## Message types

| Type | Direction | `data` |
|---|---|---|
| `hello` | client → server | `protocol`, `token` (access token), `device_id`?, `last_seq`? |
| `welcome` | server → client | `protocol`, `current_seq`, `oldest_seq` |
| `auth` | client → server | `token` – renewed access token for the open connection |
| `subscribe` | client → server | `stream`, `params`, `since`? (newest `seq` the client has for this list), `start`, `end` (initial window) |
| `unsubscribe` | client → server | – |
| `window` | client → server | `start`, `end` – new visible window (+ buffer) by position |
| `snapshot_meta` | server → client | `total`, `counters`; envelope `seq` = feed position the snapshot is based on |
| `chunk` | server → client | `chunk` (number), `start` (position of the first row), `rows` |
| `ack` | client → server | `chunk` – chunk received (backpressure) |
| `delta` | server → client | `op` (`upsert` or `remove`), `id`, `key` (sort key), `row`?, `total`, `counters`? (subscriptions with counters); envelope `seq` |
| `resync` | server → client | – the client drops its cached rows; `snapshot_meta` and the window follow |
| `error` | server → client | `code`, `message`; connection stays open |

The first message must be `hello` within 10 seconds; the access token is never accepted in the URL.

Deltas are upserts or removals by `id` and must be applied idempotently: a delta may repeat a state that the snapshot already contained (changes committed shortly before the subscription are numbered after it).

## Windows and jumps

Clients request rows by position (`start`, `end`, end exclusive, at most 1,000 rows). The server answers in chunks of 200 rows, the requested window first; a new `window` replaces the previous one. To serve any position without `OFFSET`, the server keeps **anchors** per subscription – the sort key at every 1,000th position, computed in the database on demand (only every 1,000th key is returned) – and reads from the nearest anchor with keyset pagination. At most 4 chunks per subscription are unacknowledged.

## Close codes

| Code | Meaning | Client reaction |
|---|---|---|
| `4401` | access token expired | refresh token, reconnect, resume |
| `4426` | protocol version not supported | ask the user to update |

## Counters

`snapshot_meta.data` = `{ "total": n, "counters": { … } }`. The counter keys of each subscription type are defined by the owning domain's spec (e.g. jobs: `running`, `failed`; review: count per type and status). All values come from maintained counters, never from counting rows on request. Every `delta` of a subscription with counters carries the current `counters` along with `total`, so counter displays stay live without a new snapshot.

## Service availability

The stream `services` (all signed-in users, no parameters) lists the services the installation uses – currently the tagger – with `status` (`available`, `unavailable`, `incompatible`), `version`, `interface` and `message`; counters per status. Every server process checks the services and stores status changes with a change-log entry, so all connections receive the same deltas. Clients use it to hide features of unavailable services.

## Library lists

Five streams for all signed-in users serve the library (`openspec/specs/library/spec.md`). Each is one index range scan; the sort keys are normalized (no case, no diacritics) and stored on the listed rows, and they compare bytewise on both engines (collation `"C"` on PostgreSQL). Row types are published with the message schema (`LibraryArtistRow`, `LibraryReleaseRow`, `LibraryTrackRow` in `packages/api-types`).

| Stream | Params | Sort key | Total | Counters |
|---|---|---|---|---|
| `library.artists` | – | sort name, id | artists | all four |
| `library.releases` | – | album artist sort name, title, id | releases | all four |
| `library.artist.releases` | `artist_id` | title, id | the artist's release count | – |
| `library.release.tracks` | `release_id` | disc number, track number, id | the release's track count | – |
| `library.tracks` | – | artist sort name, title, album title, id | tracks | all four |

The four library counters are `artists`, `releases`, `tracks` and `recordings`; all are maintained in the writing transaction. A change that alters what other rows show or sort by (e.g. an artist rename) writes one change entry per affected row, so each of them receives a delta. The filtered lists ignore changes of rows outside their filter; when a row leaves a filtered list, the library writes an extra entry of type `release.moved` or `track.moved`, which the list of the former parent answers with `remove`.

## Change sequence and visibility

- One global, monotonically increasing change sequence covers shared data, personal data, jobs and devices.
- Each change log entry has a scope: `SHARED` (all users), `USER` (owner only), `DEVICE` (one device only).
- The server sends a delta only to connections that subscribed to the affected data and may see it.

## Several server processes

Change sequence numbers are assigned after commit by a single sequencer (outbox pattern, PostgreSQL advisory lock), so they appear in commit order. Every server process reads the numbered change log and delivers deltas to its own connections; clients may be connected to any process. Several processes require PostgreSQL.

## Resume and retention

- `hello` carries the client's last change sequence. If it is within the change log retention (default 7 days), the server sends the missed deltas.
- Otherwise each subscription receives `resync`, then `snapshot_meta` and the rows of the visible window.
