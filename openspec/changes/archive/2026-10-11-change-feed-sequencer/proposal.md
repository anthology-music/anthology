# Proposal

## Why

Deltas and resume (sync protocol) need change sequence numbers that appear in commit order, and the maintainer requires that an installation can run several server processes. The identity sequence from step 2 is assigned at insert time, so a later-committing transaction can hold a smaller number than one a client has already seen; and session revocation is only propagated inside one process. This is the first of three steps of the sync protocol (followed by `sync-protocol-core` and `sync-demo-stream`).

## What Changes

- `change_log` gets an internal `id` (identity) and a nullable unique `change_seq`; writers insert without a number.
- A **sequencer** numbers committed change log rows in batches after commit; exactly one sequencer runs per installation (PostgreSQL advisory lock with automatic takeover); `NOTIFY` wakes it on PostgreSQL.
- A **change feed** in every process reads newly numbered entries and dispatches them to in-process consumers.
- The session cache invalidates entries from the feed, so sign-out and deactivation take effect in all processes within one second.
- Change log retention (default 7 days) as a periodic task on the sequencer leader.
- Several server processes require PostgreSQL; SQLite runs one process.

## Capabilities

### New Capabilities

_None._

### Modified Capabilities

- `sync-protocol`: new requirements "Changes in commit order" and "Revocation across server processes".

## Impact

- **Data model:** `ChangeLog.id`, nullable unique `ChangeLog.changeSeq`; migration `0003`.
- **Code:** `anthology/sync/sequencer.py`, `feed.py`, `retention.py`; `core/changes.py` (`record_change()` no longer returns a number); app lifespan starts the background tasks.
- **Changes completed in part:** `sync-protocol-details` task 3.1 (global change sequence) and 3.3 (retention part).
- **Docs:** ADR 0003 (several processes, outbox with sequencer), `docs/architecture/sync-protocol.md`.
- **Non-functional requirements (2 s, 500,000 tracks):** adds 50–100 ms latency to deltas; well within the budget.
