# Proposal

## Why

The job system (`jobs-core`) needs its view: the Streaming page of the mockups shows the jobs with counters, progress and status, and users must be able to pause, resume and cancel their jobs. Second part of step 5.

## What Changes

- Streaming page: counter tiles (total, done, running, queued, failed) from the `jobs` stream counters; job list with `VirtualList` (title, creator, items done/total, progress bar, status with icon and text).
- Expanding a job shows its items (`job.items` stream) with status and message.
- Pause, resume and cancel buttons for the creator and admins.
- Developer button to start a demo job (dev builds with `ANTHOLOGY_DEV_DEMO=true`).
- E2E test: start a demo job, watch progress, pause and resume.
- Protocol gap found by the E2E test: deltas carried the new `total` but not the counters, so the counter tiles stayed at the snapshot values. Deltas of subscriptions with counters now carry the current `counters` (optional field, omitted for streams without counters).

## Capabilities

### New Capabilities

_None._

### Modified Capabilities

- `sync-protocol`: deltas carry the current counters (requirement "Counts first"). Otherwise the client side of `jobs`.

## Impact

- **Client:** `src/features/jobs/`; texts de/en; `Subscription` applies counters from deltas.
- **Server:** `sync/connection.py` and `sync/messages.py` (optional `counters` in `delta`); `packages/api-types` regenerated; `docs/architecture/sync-protocol.md`.
- **Non-functional requirements:** progress updates within one second (spec: jobs, live progress), verified end to end.
