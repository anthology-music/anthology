# jobs Specification

## Purpose
Run all long-running work (downloads, imports, tagging, recognition, analysis) as server-side background jobs so that clients only place orders and can disconnect at any time.

## Requirements

### Requirement: Background execution
The system SHALL execute long-running work as jobs on the server, independent of any client connection.

#### Scenario: Client closes during download
- **WHEN** a user starts a download and closes the client
- **THEN** the job continues on the server
- **AND** the user sees the current state when reopening any client

### Requirement: Live progress
The system SHALL report job and job-item progress, counts and results to subscribed clients as live updates (see sync-protocol).

#### Scenario: Progress in the Streaming view
- **WHEN** a job item finishes
- **THEN** the job's done count and progress update on all connected clients within one second

### Requirement: Job control
The system SHALL allow pausing, resuming and cancelling jobs and SHALL make jobs resumable after a server restart.

#### Scenario: Server restart
- **WHEN** the server restarts while a job is running
- **THEN** the job resumes from its last completed item

### Requirement: Attribution
The system SHALL record which user created each job and SHALL show it to all users.

#### Scenario: Shared job list
- **WHEN** a user views the job list
- **THEN** each job shows the name of the user who started it

### Requirement: Priority and throttling
The system SHALL give interactive requests priority over background jobs and SHALL support throttle levels (gentle, normal, fast) with low CPU and I/O priority for background work.

#### Scenario: Import running while browsing
- **WHEN** a large import runs with throttle level "gentle"
- **THEN** browsing the library still meets the 2-second interaction budget

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

### Requirement: Scheduled maintenance
The system SHALL run the maintenance as a background job on its schedule and on request of an admin. Across all server processes at most one maintenance job SHALL be active; a scheduled time reached while a run is active SHALL be skipped.

#### Scenario: Nightly run
- **WHEN** the schedule is "daily at 03:00" and it is 03:00 in the installation's time zone
- **THEN** exactly one maintenance job starts, even with several server processes

#### Scenario: Run now while running
- **WHEN** an admin starts a run while one is active
- **THEN** the request is refused and the active run continues

### Requirement: Maintenance configuration
Admins SHALL be able to configure the maintenance installation-wide: the schedule (off, daily at a time, weekly on a weekday at a time), the action for orphaned files and leftovers (delete or report only), the grace period (1 to 168 hours) and a safety limit as a share of the managed files (or off). The defaults SHALL be daily at 03:00, delete, 24 hours and a safety limit of 1 %. Changes SHALL apply from the next run on; other roles SHALL NOT see or change the configuration.

#### Scenario: Change the schedule
- **WHEN** an admin sets the schedule to weekly on Sunday at 04:00
- **THEN** the next run time shown is the coming Sunday at 04:00

#### Scenario: Editor
- **WHEN** an editor requests the maintenance configuration
- **THEN** the request is refused
