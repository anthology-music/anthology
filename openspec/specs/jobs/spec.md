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
