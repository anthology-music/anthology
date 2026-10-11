# Proposal

## Why

The sync-protocol spec defines the flow (hello, snapshot_meta, chunks, deltas, resume) but leaves gaps that every implementation would fill differently: there is no protocol version or message schema, "status counters" are undefined, the change sequence is only defined for shared library data although personal data, jobs and devices also need deltas, and "if the gap is too large" has no definition.

## What Changes

- `hello`/`welcome` SHALL carry a protocol version; incompatible clients are closed with code `4426` and shown an update hint.
- All messages SHALL use one envelope (`type`, `sub`, `seq`, payload) with a schema generated from the server models into `packages/api-types`.
- `snapshot_meta` SHALL carry `total` and a `counters` object whose keys are defined per subscription type by the owning domain; counters are maintained, never computed by counting rows.
- One global, monotonically increasing change sequence SHALL cover all data (shared, personal, jobs, devices); the server filters deltas per subscription and user.
- The change log SHALL be kept for a configurable retention (default 7 days); a client whose last change sequence is older receives `resync` per subscription and a fresh snapshot of the visible window.

## Capabilities

### New Capabilities

_None._

### Modified Capabilities

- `sync-protocol`: "WebSocket connection", "Counts first" and "Resume after disconnect" are made precise; new requirements "Message schema", "Global change sequence", "Delta visibility" and "Change log retention".

## Impact

- **Domains:** sync-protocol. library's "Change tracking" stays valid (its changes are part of the global sequence); jobs, users, review are producers.
- **Data model:** `ChangeLog` gets `scope : ChangeScope` (`SHARED`, `USER`, `DEVICE`), `ownerUserId [0..1]`, `deviceId [0..1]`. Migration only once the schema exists.
- **Docs:** new `docs/architecture/sync-protocol.md`; ADR 0003 amended.
- **Packages:** `packages/api-types` also generates protocol message types.
- **Non-functional requirements (2 s, 500,000 tracks):** supports them – counters are maintained, resync is limited to the visible window, change log retention bounds its size.
