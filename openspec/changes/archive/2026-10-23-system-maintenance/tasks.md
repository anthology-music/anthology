# Tasks

## 1. Foundations

- [x] 1.1 Migration and models `job_schedules` (default row for `library_maintenance`), `maintenance_runs`, `maintenance_findings`; setting `ANTHOLOGY_TIME_ZONE`; update `docs/architecture/data-model.puml`; verify with the migration round-trip and model comparison tests on SQLite and PostgreSQL

## 2. Schedules

- [x] 2.1 Schedule computation (daily, weekly, time zone, daylight saving) and claiming due schedules with compare-and-swap in the runner loop; skip while the job is unfinished; verify with unit tests with a fake clock and a test with two runners creating exactly one job on PostgreSQL and SQLite
- [x] 2.2 REST `GET/PUT /api/v1/maintenance/schedule` with validated options and `next_run_at`; verify with API tests (defaults, validation, roles)

## 3. Maintenance run

- [x] 3.1 Job `library_maintenance`: walk of `_originals` with grace period, classification (fine, leftover, orphan) in batches, missing managed originals; verify with tests on a temporary storage (orphan, leftover, young file, referenced file outside, missing original, interrupted item)
- [x] 3.2 Action: `delete_orphan` with the final checks, report only, safety limit and confirmation of a held run (`POST …/runs`, `POST …/runs/{id}/confirm`); verify with tests for each action, the limit (share, minimum of 10, off), a file referenced meanwhile and roles
- [x] 3.3 Streams `library.maintenance` and `library.maintenance.findings`; verify with protocol tests (snapshot, paging, delta when a run finishes)

## 4. Client

- [x] 4.1 Settings › Systempflege: schedule form, action, grace period, safety limit, next run, run now, last result with findings list, confirmation of a held run; texts de/en; verify with client tests for the acceptance criteria of US-001

## 5. Documentation

- [x] 5.1 Update `server/AGENTS.md`, `docs/agent-notes.md`, `docs/install.md` (time zone, maintenance), the sync protocol stream table and the links in `docs/requirements/`; verify the files and `openspec validate --all --strict`
