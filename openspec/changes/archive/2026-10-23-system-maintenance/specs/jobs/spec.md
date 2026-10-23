## ADDED Requirements

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
