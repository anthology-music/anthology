# Design

## Context

Step 2 introduced `change_log` (identity `change_seq`, scope, owner, device) and an in-process session cache with a 5-second TTL. The maintainer requires support for several server processes. See proposal.md for the motivation.

## Goals / Non-Goals

**Goals:**
- Commit-ordered, gap-free-from-the-client's-view change sequence across processes.
- One change feed per process that later steps (WebSocket deltas, jobs) subscribe to.

**Non-Goals:**
- WebSocket protocol and streams (`sync-protocol-core`).
- Multi-process operation on SQLite.

## Decisions

### Outbox with sequencer

`change_log(id identity PK, change_seq BIGINT NULL UNIQUE, …)`. Writers insert rows without `change_seq`. The sequencer numbers committed rows:

```sql
UPDATE change_log SET change_seq = m.base + p.rn
FROM (SELECT id, row_number() OVER (ORDER BY id) AS rn
      FROM change_log WHERE change_seq IS NULL ORDER BY id LIMIT 1000) AS p,
     (SELECT coalesce(max(change_seq), 0) AS base FROM change_log) AS m
WHERE change_log.id = p.id
```

Uncommitted rows are invisible to the sequencer, so every row committing later gets a larger number than all rows already numbered (spec "Changes in commit order"). `UPDATE … FROM` and window functions work on PostgreSQL and SQLite ≥ 3.33.

Alternative considered: PostgreSQL transaction IDs and snapshot `xmin` as a watermark. Rejected: transaction ID order differs from sequence order, so a client could still skip a change.

### Leadership

On PostgreSQL the sequencer holds a session-level advisory lock (`pg_try_advisory_lock(<constant>)`) on a dedicated connection; every process tries to acquire it every 5 seconds, so another process takes over when the leader dies. On SQLite the single process is always leader.

### Wake-ups

`record_change()` issues `SELECT pg_notify('anthology_changes', '')` inside the writing transaction on PostgreSQL (delivered on commit); the leader listens and runs immediately, otherwise every 50 ms. After numbering it notifies `anthology_feed`.

### Change feed

`ChangeFeed` per process: remembers the last delivered `change_seq` (starting at the current maximum), reads `WHERE change_seq > :last ORDER BY change_seq LIMIT 500` every 100 ms or on `anthology_feed`, and calls registered async consumers with `ChangeEvent(seq, entity_type, entity_id, operation, scope, owner_user_id, device_id)`. Consumers must be fast; slow work is handed off.

### Session cache invalidation

The session cache registers as a feed consumer: `user_device` events invalidate that entry, `user` events invalidate all entries of the user. Together with the poll interval this keeps revocation below one second across processes (spec "Revocation across server processes"); the 5-second TTL remains as a safety net.

### Retention

The leader deletes numbered rows with `changed_at` older than `sync_changelog_retention_days` (default 7) once per hour.

### Background tasks

The app lifespan starts sequencer, feed and retention as asyncio tasks and cancels them on shutdown. Tests can run them step-wise (`run_once()`), so timing does not make tests flaky.

## Risks / Trade-offs

- [Leader loses the lock while numbering] → numbering runs in one transaction; a new leader continues from `max(change_seq)`.
- [Feed lag under heavy write load] → batches of 500 and immediate re-poll while batches are full.
- [Polling cost] → one indexed query per 100 ms per process; negligible.
