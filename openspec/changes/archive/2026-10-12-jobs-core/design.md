# Design

## Context

Spec `jobs` (background execution, live progress, control, attribution, priority and throttling). Several server processes are supported on PostgreSQL (ADR 0003); the change feed delivers deltas to all processes; streams provide `KeyQuery` + `rows` + `changes`. See proposal.md for the motivation.

## Goals / Non-Goals

**Goals:**
- A job runs in exactly one process; jobs survive process crashes and restarts.
- Domains add job types by registering a handler, nothing else.
- Live progress without flooding the database.

**Non-Goals:**
- Real job types (downloads, imports, tagging) – they come with their domains; the tagger write queue (step 6) is the first.
- Admin UI for the throttle level (environment setting for now).
- Job retention / cleanup of old jobs (later).

## Decisions

### Model

- `jobs(id, type, title, params_json, status, priority_class, parallel_items, created_by → users, created_at, started_at, finished_at, total_items, done_items, failed_items, progress, error, lease_owner, lease_expires_at)`
- `job_items(id, job_id → jobs, position, title, status, progress, outcome, message, result_json, started_at, finished_at)`, unique `(job_id, position)`
- `job_counters(status PK, count)` maintained in the same transaction as every status change (no `COUNT(*)`).

Statuses: `queued → running → done | failed | cancelled`; `running ↔ paused` (pause sets `paused`, resume sets `queued`). An item that fails marks only the item `failed`; the job continues and ends `done` with `failed_items > 0`. A job is `failed` only if its handler raises outside an item or the job type is unknown.

### Handlers

```python
class JobHandler(Protocol):
    type: str
    parallel_items: int            # max items in parallel (1 = sequential)
    async def run_item(self, ctx: ItemContext) -> ItemResult: ...
```

`ItemContext` carries job params, the item, `report(progress, message)` (throttled to one write per second) and `cancelled()` (checks the job status). Jobs are created by domain services with `create_job(type, title, params, items, created_by, priority_class)`; the creating transaction notifies `anthology_jobs`.

### Runner per process and leases

Each process runs a `JobRunner` with an owner ID (random per process start). It fills free slots by claiming the oldest claimable job of the slot's class:

```sql
SELECT id FROM jobs
WHERE priority_class = :class AND status IN ('queued', 'running')
  AND (lease_expires_at IS NULL OR lease_expires_at < :now)
ORDER BY created_at LIMIT 1 FOR UPDATE SKIP LOCKED
```

and sets `status = running`, `lease_owner`, `lease_expires_at = now + 30 s`. A heartbeat extends the lease every 10 s while the owner still holds it; if it lost it (e.g. the database was unreachable), it stops the job without writing. A process that dies stops its heartbeat; after at most 30 s another process claims the job and continues with the first item not in `done | failed | cancelled` (items left in `running` are restarted). On SQLite (one process) `FOR UPDATE SKIP LOCKED` is a no-op.

Wake-ups: `NOTIFY anthology_jobs` on PostgreSQL, otherwise polling every second.

### Slots and throttling

`ANTHOLOGY_JOBS_THROTTLE` = `gentle | normal | fast` → background slots 1 / 2 / 4 per process; interactive slots `ANTHOLOGY_JOBS_INTERACTIVE_SLOTS` (default 2). Items run with `min(handler.parallel_items, slots of the level)` concurrency; `gentle` also waits 0.5 s between items. Subprocesses started by handlers later run with `nice`/`ionice` (helper added when the first one exists).

### Pause, resume, cancel

Control endpoints change the job status in the database (creator or admin, spec "Job control rights"). The runner checks the status before each item and after each finished item; on `paused` it releases the lease and stops, on `cancelled` it marks remaining items `cancelled`. Resume sets `queued`, so any process may pick it up.

### Live progress

Every status change and finished item writes a `job` change log entry (scope `SHARED`), item changes a `job_item` entry; progress within an item at most once per second. The streams turn these into deltas.

### Descending sort keys

`KeyQuery` gets `descending: bool`; `scan_keys` and `scan_anchors` use `<` and descending order, and `Anchors.invalidate_from` compares in list order. `jobs` sorts by `(created_at, id)` descending (newest first); `job.items` by `(position, id)` ascending with param `job_id`.

### REST

`GET /api/v1/jobs/{id}`, `POST /api/v1/jobs/{id}/pause|resume|cancel` (403 for others, 409 for invalid transitions). Developer demo (`ANTHOLOGY_DEV_DEMO=true`): `POST /api/v1/dev/jobs/demo {items, seconds_per_item, parallel_items}` creates a `demo` job whose items sleep and report progress.

## Risks / Trade-offs

- [30 s takeover delay after a crash] → acceptable for background work; lease duration is configurable.
- [Clock differences between processes] → leases use the database clock (`now()` on PostgreSQL).
- [Many progress writes with many parallel items] → throttled per item to one write per second.
