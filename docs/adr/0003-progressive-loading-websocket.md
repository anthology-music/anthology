# ADR 0003: Progressive loading over one WebSocket per client

- Status: Accepted
- Date: 2026-10-09

## Context

The current view must be interactive within 2 seconds with libraries of 500,000 tracks, on desktop and mobile. Loading full lists is impossible within this budget.

## Decision

Progressive loading is designed into every layer:

- Database: keyset pagination, maintained counters, change sequence numbers.
- Server: async generators yielding chunks, visible window first, backpressure.
- Protocol: one WebSocket per client with subscriptions – `snapshot_meta` (counts) first, then chunks, then deltas; resume via change sequence.
- Client: local cache first, virtual scrolling, skeleton rows, rule-based selections.

Audio and video use HTTP range requests, not the WebSocket.

### Jumps without OFFSET (amended 2026-10-11)

Clients request windows by position. Each subscription keeps **anchors** – the sort key at every 1,000th position, built from index-only key scans on demand – so any position is reached from the nearest anchor with keyset pagination and at most one further key scan.

### Several server processes (amended 2026-10-11)

An installation may run several server processes; this requires PostgreSQL (SQLite installations run one process).

- **Outbox with sequencer:** writers insert change log rows without a number; a single sequencer (the process holding a PostgreSQL advisory lock, with automatic takeover) numbers committed rows afterwards. Numbers therefore appear in commit order, and a client that has seen a number never misses a smaller one.
- **Change feed per process:** every process reads newly numbered rows and dispatches them to its own consumers – WebSocket connections and the session cache, so revocation reaches all processes within a second.
- `NOTIFY` wakes sequencer and feeds on PostgreSQL; otherwise they poll (50 ms / 100 ms).

## Consequences

- Every list feature needs a stream implementation and protocol tests.
- The protocol is the foundation and is built in phase 1.
- The protocol is versioned (`hello`/`welcome`, close code 4426 for unsupported versions) and uses one global change sequence for shared, personal, job and device data; the change log is kept for a configurable retention (default 7 days), older clients are resynchronised per visible window.
- See `openspec/specs/sync-protocol/spec.md` and `docs/architecture/sync-protocol.md`.
