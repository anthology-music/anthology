# Proposal

## Why

The WebSocket protocol is the foundation of progressive loading (ADR 0003); every list in Anthology depends on it. The specs (`sync-protocol`, changes `sync-protocol-details` and `signed-media-urls`) define the behavior, but nothing is implemented. This is the second of three steps: it builds on the commit-ordered change feed of `change-feed-sequencer` and is followed by `sync-demo-stream`.

## What Changes

- WebSocket endpoint `/api/v1/ws` with `hello`/`welcome` (protocol version, close code 4426), authentication in `hello` (10-second timeout, never in the URL), `auth` for token renewal, close code 4401 on expiry, `error` replies.
- Message envelope and models with exported JSON Schema (client types are generated in step 4).
- Subscription framework: domains register **streams**; the protocol handles `snapshot_meta` (counts first), windowed chunks with the visible window first, **position anchors** for jumps without `OFFSET`, backpressure with `ack`, deltas from the change feed with scope visibility, resume with `since` and `resync`.
- First streams: `me.devices` and the admin user list `users`.

## Capabilities

### New Capabilities

_None._

### Modified Capabilities

- `sync-protocol`: new requirements "Authentication timeout", "Jump to a position" and "Deltas across server processes".

## Impact

- **Domains:** sync-protocol (server module `sync`); users provides the first streams.
- **Changes completed in part:** `sync-protocol-details` tasks 2.1 (server part), 2.2, 3.2, 3.3 (resync part); `signed-media-urls` task 4.1.
- **Docs:** ADR 0003 (anchors), `docs/architecture/sync-protocol.md` (message fields, `since`).
- **Non-functional requirements (2 s, 500,000 tracks):** directly addressed; the 500,000-row performance test follows in `sync-demo-stream`.
