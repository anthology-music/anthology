# Design

## Context

ADR 0003 and `docs/architecture/sync-protocol.md` define one WebSocket per client with subscriptions (counts first, windowed chunks, deltas, resume, resync, backpressure, versioning, `auth`, close codes 4401/4426). The change `change-feed-sequencer` provides commit-ordered change sequence numbers and a change feed per process (several server processes, PostgreSQL). See proposal.md for the motivation.

## Goals / Non-Goals

**Goals:**
- A generic stream framework so that every later list (library, jobs, review, …) only implements queries.
- Deltas and resume work for clients connected to any server process.
- Jumps to any position of a 500,000-row list within the interaction budget without `OFFSET`.

**Non-Goals:**
- Client implementation (step 4).
- Binary encoding (roadmap).
- Rule-based bulk selection (comes with the first bulk action in milestone 2).
- Sequencer, change feed and retention (`change-feed-sequencer`); demo stream and performance test (`sync-demo-stream`).

## Decisions

### Module layout (`anthology/sync/`)

`messages.py` (pydantic models), `streams.py` (stream interface and registry), `anchors.py`, `connection.py` (per-connection state machine), `hub.py` (connections of this process, registered as change feed consumer), `api.py` (WebSocket route).

### Messages

Envelope `{type, sub?, seq?, data}`; pydantic discriminated union on `type`. Client → server: `hello {protocol, token, device_id, last_seq}`, `auth {token}`, `subscribe {sub, stream, params, since?, window}`, `window {sub, start, end}`, `ack {sub, chunk}`, `unsubscribe {sub}`. Server → client: `welcome {protocol, current_seq, oldest_seq}`, `snapshot_meta {sub, total, counters, seq}`, `chunk {sub, chunk, start, rows}`, `delta {sub, seq, op: upsert|remove, row|id, counters}`, `resync {sub}`, `error {code, message, sub?}`. JSON Schema of both unions is exported by `python -m anthology.sync.messages > schema.json`; TypeScript generation follows in step 4.

### Connection lifecycle

1. Accept; wait up to 10 s for `hello` (spec "Authentication timeout"). Unsupported `protocol` → close 4426. Invalid token or revoked session → close 4401.
2. `welcome` with the newest assigned change sequence and the oldest retained one.
3. A timer closes the connection with 4401 at token expiry unless `auth` delivered a newer valid token for the same user device.
4. Malformed messages → `error`, connection stays open.

### Streams

```python
class Stream(Protocol):
    name: str
    entity_types: frozenset[str]                       # change log entity types that may affect it
    def allowed(self, session: SessionInfo) -> bool
    async def meta(self, db, ctx) -> Meta              # total + counters (maintained, not COUNT(*) on large tables)
    async def keys(self, db, ctx, after, limit) -> list[SortKey]      # index-only scan for anchors
    async def rows(self, db, ctx, after, limit) -> list[Row]          # keyset page
    async def row(self, db, ctx, entity_id) -> Row | None             # current row if it belongs to the list
```

`ctx` holds the session info and validated params. Rows carry `id` and `key` (the sort key, used by the client to place deltas).

### Windows, anchors and jumps

Rows are served in chunks of 200. A `window {start, end}` replaces the previous window of that subscription; pending chunks outside the new window are dropped, chunks of the new window are sent first (visible first). Position → keyset: the subscription keeps **anchors**, the sort key at every 1,000th position, built by `keys()` scans (index-only) on demand up to the requested position and cached. A window at position *p* starts from anchor ⌊p/1000⌋ and skips at most 999 keys with one further `keys()` call before `rows()`. Inserts and removes reported by deltas mark anchors behind the affected key as stale; they are rebuilt lazily. No query uses `OFFSET`.

Alternative considered: sending all sort keys to the client. Rejected: about 8 MB for 500,000 rows before the first row.

### Backpressure

At most 4 unacknowledged chunks per subscription; further chunks wait for `ack` (spec "Backpressure"). Deltas are not subject to the chunk window but are coalesced per entity while a client lags.

### Deltas

The process-local hub registers as consumer of the change feed. For each event it checks every subscription of its connections: scope visibility (`SHARED` for everyone allowed by the stream, `USER` only for the owner, `DEVICE` only for that device) and the stream's `entity_types`; then it calls `row()` and sends `delta` (upsert with the current row, or remove). Clients connected to other processes receive the same events through their own feed (spec "Deltas across server processes").

### Resume and resync

`subscribe` may carry `since` (the newest sequence the client has for that list). If `since` ≥ oldest retained, the server replays matching change log entries after `since` (coalesced per entity: one `delta` with the current row or a removal) before live deltas; otherwise it sends `resync` and a fresh snapshot (counts first, then the requested window).

### First streams

`me.devices` (scope USER, owner only) and `users` (admins only, sorted by username). Both are small; they prove the framework end to end.

## Risks / Trade-offs

- [Anchor building scans many keys after large changes] → index-only, in batches, cancelled if the subscription changes; at most one rebuild per jump.
- [Multi-process tests] → protocol tests run two app instances against the same PostgreSQL database in one test process.
