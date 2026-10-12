# Proposal

## Why

The job system (`jobs-core`) needs its view: the Streaming page of the mockups shows the jobs with counters, progress and status, and users must be able to pause, resume and cancel their jobs. Second part of step 5.

## What Changes

- Streaming page: counter tiles (total, done, running, queued, failed) from the `jobs` stream counters; job list with `VirtualList` (title, creator, items done/total, progress bar, status with icon and text).
- Expanding a job shows its items (`job.items` stream) with status and message.
- Pause, resume and cancel buttons for the creator and admins.
- Developer button to start a demo job (dev builds with `ANTHOLOGY_DEV_DEMO=true`).
- E2E test: start a demo job, watch progress, pause and resume.

## Capabilities

### New Capabilities

_None._

### Modified Capabilities

_None._ Client side of `jobs`. `skip_specs: true`.

## Impact

- **Client:** `src/features/jobs/`; texts de/en.
- **Non-functional requirements:** progress updates within one second (spec: jobs, live progress), verified end to end.
