# Spec Delta

## ADDED Requirements

### Requirement: Job control rights
Only the user who created a job and admins SHALL be able to pause, resume or cancel it; all users SHALL be able to see it.

#### Scenario: Another user tries to cancel
- **WHEN** an editor tries to cancel a job created by another user
- **THEN** the request is rejected and the job keeps running

#### Scenario: Admin cancels any job
- **WHEN** an admin cancels a job created by another user
- **THEN** the job is cancelled

### Requirement: Parallel execution
The system SHALL run several jobs in parallel up to the number of slots of the configured throttle level (gentle 1, normal 2, fast 4 background jobs per server process, plus separate slots for interactive jobs) and SHALL run items of one job in parallel only if its job type allows it.

#### Scenario: Throttle level gentle
- **WHEN** three background jobs are queued and the throttle level is gentle
- **THEN** one job runs per server process and the others wait

#### Scenario: Interactive job while background jobs run
- **WHEN** all background slots are busy and an interactive job is created
- **THEN** the interactive job starts without waiting for a background job

### Requirement: Takeover after a process failure
A job SHALL run in at most one server process at a time; if that process stops without finishing the job, another process SHALL continue the job at its first unfinished item.

#### Scenario: Process crash during a job
- **WHEN** the server process running a job dies after 5 of 12 items
- **THEN** another server process continues the job with item 6

### Requirement: Job counters
The system SHALL maintain the number of jobs per status and SHALL show them with the job list before the rows.

#### Scenario: Counters in the streaming view
- **WHEN** a client opens the job list
- **THEN** the numbers of running, queued, paused, finished and failed jobs are shown before the jobs
