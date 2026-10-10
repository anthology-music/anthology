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

| Type | Direction | Purpose |
|---|---|---|
| `hello` | client → server | protocol version, access token, device ID, last known change sequence |
| `welcome` | server → client | protocol version, current change sequence |
| `auth` | client → server | renewed access token for the open connection |
| `subscribe` | client → server | subscription type, filter, sort, initial window |
| `unsubscribe` | client → server | end a subscription |
| `window` | client → server | new visible window (+ buffer) of a subscription |
| `snapshot_meta` | server → client | `total` and `counters` of a subscription, before any rows |
| `chunk` | server → client | rows for a window range |
| `ack` | client → server | chunk received (backpressure) |
| `delta` | server → client | change of subscribed data, with `seq` |
| `resync` | server → client | client is too far behind; snapshot of the visible window follows |
| `error` | server → client | malformed or rejected message; connection stays open |

## Close codes

| Code | Meaning | Client reaction |
|---|---|---|
| `4401` | access token expired | refresh token, reconnect, resume |
| `4426` | protocol version not supported | ask the user to update |

## Counters

`snapshot_meta.data` = `{ "total": n, "counters": { … } }`. The counter keys of each subscription type are defined by the owning domain's spec (e.g. jobs: `running`, `failed`; review: count per type and status). All values come from maintained counters, never from counting rows on request.

## Change sequence and visibility

- One global, monotonically increasing change sequence covers shared data, personal data, jobs and devices.
- Each change log entry has a scope: `SHARED` (all users), `USER` (owner only), `DEVICE` (one device only).
- The server sends a delta only to connections that subscribed to the affected data and may see it.

## Resume and retention

- `hello` carries the client's last change sequence. If it is within the change log retention (default 7 days), the server sends the missed deltas.
- Otherwise each subscription receives `resync`, then `snapshot_meta` and the rows of the visible window.
