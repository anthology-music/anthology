# Proposal

## Why

The tagger service exists (`tagger-service`), but the core cannot use it yet: it needs a client for interface v1, must know whether the tagger is reachable and compatible, and must keep working while it is not. Clients will hide tag-writing features while the tagger is unavailable, so its status has to reach them live – the same will apply to source services and recognition later. Step 6b of milestone 1.

## What Changes

- **Tagger client** in the core (`anthology/tagging/tagger_client.py`): typed models of interface v1, `read`, `write`, `copy`, `health`; lists are split into batches (default 200); transport errors and 5xx answers raise "tagger unavailable".
- **Availability monitor** per server process: checks the tagger's health at startup, every 30 s while available and every 5 s while not, and immediately after a failed call; states `available`, `unavailable`, `incompatible` (interface major version other than 1). Calls are refused while incompatible. The core keeps running in every state.
- **Service status in the database** (`service_status`, one row per service) with change-log entries, so all server processes and clients see the same status; `/api/v1/ready` lists it without becoming not-ready.
- **Live stream `services`** for all signed-in users: name, status, versions; deltas on every status change.
- **Client:** `useServices()` / `useServiceAvailable(name)` on the stream; an admin section "Services" in the settings shows the status with icon and text.
- **Contract tests** of the core client against the real tagger (HTTP only), run in CI.

## Capabilities

### New Capabilities

_None._

### Modified Capabilities

- `tagging`: tagger availability (startup without tagger, recovery, incompatible versions).
- `sync-protocol`: service availability stream.

## Impact

- **Domains:** `tagging`, `sync-protocol`; referenced: `sources` (source services will report through the same stream later).
- **Server:** `anthology/tagging/` (client, schemas), `anthology/core/services.py` (status model, monitor), `anthology/sync/services_stream.py`, wiring in `api/app.py`, `/ready`; new settings for the tagger; `httpx` (BSD-3-Clause) becomes a runtime dependency.
- **Data model:** new entity `ServiceStatus`; migration `0005`; `docs/architecture/data-model.puml` updated.
- **Client:** `src/sync/services.ts`, settings section, de/en texts; `packages/api-types` regenerated.
- **CI:** server workflow starts the tagger and runs the contract tests.
- **Docs:** `server/AGENTS.md` (client location), `docs/architecture/sync-protocol.md` (stream list).
- **Non-functional requirements:** none; one health request per 30 s per process.
