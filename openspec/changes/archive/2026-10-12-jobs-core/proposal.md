# Proposal

## Why

All long-running work (downloads, imports, tagging, recognition, analysis) runs as jobs (spec: jobs), but nothing exists yet. The jobs system must work with several server processes: a job runs in exactly one process, and a crashed process's jobs continue elsewhere. Who may control jobs and how much runs in parallel is not specified yet.

## What Changes

- Jobs and job items with a handler registry per job type; domains register handlers.
- Runner per process: claims jobs with leases (`FOR UPDATE SKIP LOCKED`, heartbeat); jobs with expired leases are taken over and continue at the first unfinished item.
- Pause, resume and cancel between items; handlers can check for cancellation inside long items.
- **Control rights:** only the creator of a job and admins may pause, resume or cancel it (maintainer decision).
- **Parallelism:** server-wide throttle level gentle / normal / fast → 1 / 2 / 4 background slots per process (plus separate interactive slots); items of a job run in parallel only if the job type allows it, limited by the throttle level.
- Live progress through the change feed: status changes immediately, progress within an item at most once per second; maintained counters per status.
- Streams `jobs` (newest first, visible to all users with the creator's name) and `job.items`; the stream framework learns descending sort keys.
- REST: job details and control endpoints; developer demo job (`ANTHOLOGY_DEV_DEMO=true`) to see jobs before real job types exist.

## Capabilities

### New Capabilities

_None._

### Modified Capabilities

- `jobs`: new requirements "Job control rights", "Parallel execution", "Takeover after a process failure" and "Job counters".

## Impact

- **Domains:** jobs (server module `jobs`); sync (descending keys); users (control rights).
- **Data model:** `Job` gets `title`, `paramsJson`, `priorityClass` (interactive/background), `parallelItems`, `createdBy`, `leaseOwner`, `leaseExpiresAt`, `startedAt`, `error`; download-specific fields (`mediaMode`, `maxVideoResolution`) move into `paramsJson`; `JobItem` gets `position`, `resultJson`, `startedAt`, `finishedAt`; new `JobCounter`; `JobType.DEMO`. Migration `0004`.
- **Docs:** ADR 0003 not affected; `server/AGENTS.md` (how to add a job type).
- **Non-functional requirements (2 s, 500,000 tracks):** interactive slots keep interactive work responsive while background jobs run; throttling keeps browsing within budget.
