# Design

## Context

Interface v1 is documented in `docs/architecture/tagger-api.md` and specified in `openspec/specs/tagging/spec.md`. `Settings.tagger_url` exists (default `http://localhost:8410`). Several server processes may run (PostgreSQL); shared state must go through the database and the change feed (server/AGENTS.md). See proposal.md for the motivation.

## Goals / Non-Goals

**Goals:**
- One client for the core with batching and clear error types.
- A consistent, live service status for all processes and clients.

**Non-Goals:**
- The persistent write queue and its resume logic (change `tag-editing`).
- Status of source services and recognition (they report through the same model once their adapters exist).

## Decisions

### Client

`TaggerClient` wraps an `httpx.AsyncClient` (timeout 30 s, configurable). `read(paths, …)`, `write(mode, files)` and `copy(files)` accept any number of entries and send them in batches of `tagger_batch_size` (default 200, the tagger's limit), concatenating the results in order. Models mirror the interface; `tags` are serialized with `exclude_unset`, so "omitted = keep, null = remove" survives. Errors: `TaggerUnavailable` (connection error, timeout, 5xx), `TaggerIncompatible` (monitor reports another major version), `TaggerError` (4xx, e.g. `forbidden_path` of a whole request). Per-file errors stay in the results.

Location: `anthology/tagging/` – the tagger is the tagging domain's file backend (spec `tagging`); `server/AGENTS.md` is corrected (it named `library/`).

### Availability monitor

`ServiceMonitor` in `anthology/core/services.py` is generic: a name, an async check returning status, version, interface version and message, and two intervals (30 s while available, 5 s otherwise). The tagger check calls `/v1/health`; interface `1.x` → `available`, other major → `incompatible`, transport error → `unavailable`. A failed call (`TaggerUnavailable`) triggers an immediate re-check. The monitor runs with the other background tasks (`background_tasks` setting), so tests control it explicitly.

### Status in the database

Table `service_status` (`name` primary key, `id` = UUID5 of the name for change-log entries, `status`, `version`, `interface`, `message`, `changed_at`). A process writes only when its observation differs from the stored row, in one transaction with a `service_status` change-log entry (scope shared). No audit-log entry: this is system state, not user data. With several processes the status follows the latest observation; all processes share one pod network, so they normally agree.

### Stream `services`

`ServicesStream` (`anthology/sync/services_stream.py`), visible to all signed-in users, ordered by name. The table has one row per known service (bounded by configuration, not by data), so `snapshot_meta` derives the counters `available`, `unavailable`, `incompatible` from these few rows; no counter table is needed. Deltas come from the change feed like any other stream.

### Readiness

`/api/v1/ready` gains `services: {tagger: "available" | …}` from the database. Readiness is not affected: the core runs without the tagger.

### Client (web)

`useServices()` subscribes to `services` and returns a reactive map; `useServiceAvailable('tagger')` is what features will use to hide actions. The settings page gets an admin section "Services" listing each service with icon and text (and versions).

### Contract tests

Server tests marked `tagger_contract` run against a real tagger when `ANTHOLOGY_TEST_TAGGER_URL` and `ANTHOLOGY_TEST_TAGGER_ROOT` are set (otherwise skipped). They generate a FLAC file with FFmpeg below the root, read, write, copy and check the health. CI installs FFmpeg, starts the tagger from `services/tagger` with `uv` and runs these tests. The core only talks HTTP to the GPL service.

## Risks / Trade-offs

- [Status flapping between processes with different views] → only written on change; same pod network; acceptable for a status display.
- [A slow tagger blocks a request for the timeout] → callers are jobs (background); timeout configurable.

## Migration Plan

Migration `0005_service_status` creates the table; rows are created by the monitor on first check.

## Open Questions

None.
