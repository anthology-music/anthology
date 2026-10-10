# Design

## Context

ADR 0003 and the sync-protocol spec define one WebSocket per client with `hello`/`welcome`, `snapshot_meta`, windowed chunks, deltas and resume via change sequence. The data model has `ChangeLog` (changeSeq, entityType, entityId, operation, changedAt) without scope. `packages/api-types` is generated from the server's OpenAPI. See proposal.md for the motivation.

## Goals / Non-Goals

**Goals:**
- A versioned, typed protocol shared by server and client.
- Resume works the same for all data kinds.
- Bounded change log.

**Non-Goals:**
- Binary encoding (MessagePack etc.); JSON first, can be negotiated later via the version.
- Defining the counter keys of each subscription – each domain does that in its own spec.

## Decisions

### Envelope and schema

```json
{ "type": "delta", "sub": "s12", "seq": 184467, "data": { … } }
```

`type` is required; `sub` for subscription-bound messages; `seq` for messages carrying a change. Message models are pydantic discriminated unions; the server exports their JSON Schema and `packages/api-types` generates TypeScript types from it alongside OpenAPI. Message types: `hello`, `welcome`, `auth`, `subscribe`, `unsubscribe`, `window`, `snapshot_meta`, `chunk`, `ack`, `delta`, `resync`, `error`.

### Versioning

Integer protocol version. The server supports a range (current and previous); additive changes (new optional fields, new message types the client may ignore) do not bump the version. Close code `4426` mirrors HTTP 426 Upgrade Required.

### Global sequence

A single database sequence (`change_seq`) is drawn in the same transaction as the change and written to `ChangeLog` with `scope` (`SHARED`, `USER`, `DEVICE`), `ownerUserId` and `deviceId`. One sequence keeps resume simple (one number per client) and gives a total order. On SQLite (dev) an autoincrement table provides the same.

Alternative considered: one sequence per scope or user. Rejected: clients would track several numbers and ordering across scopes would be lost.

### Fan-out and filtering

After commit, a change notifier (PostgreSQL `LISTEN/NOTIFY`, in-process for SQLite) publishes `(seq, scope, owner, device, entityType, entityId)`. Each connection's subscription matcher checks scope visibility first (owner/device), then whether the entity falls into a subscribed query (by entity type and, for filtered lists, by the subscription's filter). Only matching connections fetch the row and send `delta`.

### Retention and resync

A daily job deletes `ChangeLog` rows older than the retention (default 7 days, setting `sync.changelog_retention_days`). On `hello`, if the client's sequence is below the oldest retained one, every subscription gets `resync`, then `snapshot_meta` and the visible window as on a fresh subscription.

### Progressive loading

Strengthened: counters maintained per subscription type; resync limited to the visible window; deltas filtered server-side.

## Risks / Trade-offs

- [Single sequence is a write hotspot] → sequences in PostgreSQL are non-transactional and cheap; batch writes draw ranges.
- [Matching deltas against filtered subscriptions is costly with many connections] → match by entity type first, evaluate filters only for candidate subscriptions; household-scale connection counts.
- [Clients ignoring unknown message types] → required by the protocol doc; tested with a fake newer server.
