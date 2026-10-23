# Design

## Context

- **Jobs:** the job system runs resumable items with leases across server processes. It has no schedules yet; the change log retention runs as a process-local background task (`ChangeBackground`).
- **Managed storage:** managed originals live in `<library>/_originals/<xx>/…`; transfers leave `.<name>.part` while writing, and link probes leave `.probe-<id>`.
- **Guard and ADRs:** `check_file_operation` guards file operations. ADR 0021 deletes replaced managed originals after the database commit, so a crash can leave an orphan.

Use case UC-001 and story US-001 in `docs/requirements/`.

## Goals / Non-Goals

**Goals:**
- Find and remove orphaned files and leftovers reliably and safely.
- Report missing originals.
- Make the schedule configurable by admins.

**Non-Goals:**
- Repairing missing originals.
- Cleaning caches.
- Database maintenance.
- Checking referenced files for deletion.

## Decisions

### Schedules (jobs)

Table `job_schedules`, one row per schedulable job type. Its fields:
- `type` (primary key), `enabled`, `frequency` (`daily`, `weekly`), `time_of_day`, `weekday`;
- `options` (JSON, validated by the job type);
- `next_run_at`, `last_job_id`.

The runner loop of every process checks due schedules each minute. A process claims a schedule with a compare-and-swap `UPDATE … SET next_run_at = <next> WHERE type = … AND next_run_at = <seen>`, the same pattern as the lookup schedule, so exactly one process creates the job. A schedule whose job is still unfinished skips the occurrence (A1).

Times are computed in `ANTHOLOGY_TIME_ZONE` (zoneinfo, default UTC) and stored in UTC. Daylight saving changes take the next valid local time.

Job types register a `ScheduleSpec` (default schedule and options schema) with the registry. The first is `library_maintenance`.

### Maintenance options

Options of `library_maintenance`, validated with pydantic:
- `action`: `delete` (default) or `report`;
- `grace_hours`: 1–168, default 24;
- `safety_share_percent`: 0.1–100 or null (off), default 1. The limit of a run is `max(10, ceil(share × managed files / 100))`. Managed files are the managed audio file entries counted at the start of the run (a maintained counter is not needed: one indexed count per run). Counting the database side is deliberate: after a restore from an older backup it is small while the orphans are many.

### Maintenance run (library)

Job `library_maintenance`:
- Item 1 walks `_originals` (scandir in a thread, no symlinks followed). It writes candidates (path, size, mtime) of files older than the grace period into `maintenance_findings` for this run, 1,000 per transaction, idempotent by (run, path).
- Classification: a file whose path is an `audio_files.path` is fine. Unique index lookup in batches of 1,000 paths. Otherwise it is a leftover if its name starts with `.` and ends with `.part` or starts with `.probe-`; else an orphan.
- Item 2 reads managed audio files by path (keyset) and checks `os.path.exists` in a thread, in batches of 1,000; missing ones become findings of class `missing`.
- Item 3 acts:
  - if the action is `delete` and the number of deletable findings is within the safety limit, each file is deleted after a final check: still no audio file entry with that path, still older than the grace period, still inside `_originals` (resolved path). Each finding records `deleted` or the reason it was kept.
  - Otherwise the run ends as `held` (safety limit) or `reported`.
- An admin's confirmation of a held run creates a job that performs item 3 for that run without the limit.

Deletion uses a new library function `delete_orphan(path)`. It refuses paths outside `_originals` and paths of any audio file entry. That is the guard for files without an entry: `check_file_operation` needs an entry. ADR 0021's deletion order (database first, then file) stays; this job is its sweep.

### Result and stream

- `maintenance_runs`: id, job, started, finished, status (`running`, `done`, `held`, `reported`, `failed`), action, counts and bytes per class and outcome.
- Stream `library.maintenance` (admins): the runs, newest first, with counts.
- Stream `library.maintenance.findings` (admins, param `run_id`): findings by path, keyset.

### API

All endpoints are for admins.

| Endpoint | Purpose |
|---|---|
| `GET/PUT /api/v1/maintenance/schedule` | schedule and options, with `next_run_at` |
| `POST /api/v1/maintenance/runs` | run now; 409 while running |
| `POST /api/v1/maintenance/runs/{id}/confirm` | delete a held run's findings |

### Client

Settings › Systempflege:
- form for schedule (off, daily, weekly with weekday, time), action, grace period and safety limit (percentage or off);
- next run, "Jetzt ausführen";
- last result with counts and the findings list (VirtualList);
- for a held run, "Löschen bestätigen" with a dialog.

Texts de/en.

## Risks / Trade-offs

- **Deleting a file an import is just writing:** the grace period plus the final check before deletion. Transfers write `.part` names that are renamed when complete, and imports register the audio file entry before the next run usually comes.
- **Large storage walks:** in a thread, in batches, at background priority; resumable by item.
- **Wrong library directory configured (e.g. empty mount):**
  - Every file would look orphaned. The safety limit holds the run, unless it was switched off.
  - Missing originals would also explode, which is visible in the result.
  - A run with the storage directory missing fails (A2).

## Migration Plan

One Alembic migration:
- `job_schedules` with the default row for `library_maintenance` (daily 03:00, enabled);
- `maintenance_runs` and `maintenance_findings`.

Rollback drops them.

## Open Questions

- Whether later checks (cache size, database vacuum) share the same settings section. Likely yes, as further schedules of the same table.
