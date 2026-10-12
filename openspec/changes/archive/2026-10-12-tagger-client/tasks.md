# Tasks

## 1. Documentation

- [x] 1.1 Update `server/AGENTS.md` (tagger client location, monitor), `docs/architecture/sync-protocol.md` (stream `services`) and `docs/architecture/data-model.puml` (`ServiceStatus`); verify the diagram renders on the PlantUML server

## 2. Server

- [x] 2.1 Tagger client with models, batching and error types (`anthology/tagging/`); `httpx` as runtime dependency; verify with tests against a fake tagger (batching order, omitted vs null, unavailable, 4xx)
- [x] 2.2 `ServiceStatus` model, migration 0005, generic `ServiceMonitor` with intervals and immediate re-check after failures; verify with tests for start without tagger, recovery, incompatible version and write-on-change only (SQLite and PostgreSQL)
- [x] 2.3 Stream `services` and `/ready` services section; wire monitor and client in `api/app.py`; verify with protocol tests (snapshot, delta on change) and a readiness test
- [x] 2.4 Contract tests against the real tagger (`tagger_contract`, skipped without `ANTHOLOGY_TEST_TAGGER_URL`); verify locally with a running tagger

## 3. Client

- [x] 3.1 `useServices()` / `useServiceAvailable()` and the admin settings section "Services" (status with icon and text, versions); regenerate api-types; verify with component tests

## 4. CI and verification

- [x] 4.1 Server workflow: FFmpeg, start the tagger, run the contract tests; verify it passes
- [x] 4.2 Run all tests and linters; archive this change before pushing
