# Tasks

## 1. Documentation and data model

- [x] 1.1 Update `docs/architecture/data-model.puml` (Job, JobItem, JobCounter, `JobType.DEMO`, `PriorityClass`) and describe adding a job type in `server/AGENTS.md`; verify the diagram renders without errors on the PlantUML server

## 2. Model and creation

- [x] 2.1 Models and migration `0004` (jobs, job_items, job_counters); verify the migration round trip and the model comparison test on both engines
- [x] 2.2 Job creation, status transitions with maintained counters and change log entries; verify with tests that counters always match the jobs per status

## 3. Runner

- [x] 3.1 Handler registry and runner with slots per throttle level and interactive slots, item parallelism and gentle pause; verify with tests using fake handlers (slot limits, parallel items, interactive first)
- [x] 3.2 Leases with heartbeat and takeover; verify on PostgreSQL that two runners never run the same job and that a job of a dead runner continues at its first unfinished item
- [x] 3.3 Pause, resume, cancel and in-item cancellation; verify with tests for each transition and that a paused job continues where it stopped
- [x] 3.4 Throttled in-item progress; verify that progress is written at most once per second

## 4. API and streams

- [x] 4.1 Descending keys in the stream framework; verify with tests for keys, anchors and invalidation in descending order
- [x] 4.2 Streams `jobs` (with creator name and counters) and `job.items`; verify with protocol tests including live deltas while a job runs
- [x] 4.3 Control endpoints with rights (creator, admin) and the developer demo job; verify with API tests for all roles

## 5. Verification

- [x] 5.1 Run the full test suite on SQLite and PostgreSQL and the linters; regenerate API types; archive this change before pushing
