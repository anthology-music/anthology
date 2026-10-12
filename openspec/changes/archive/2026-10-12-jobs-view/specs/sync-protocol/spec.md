## MODIFIED Requirements

### Requirement: Counts first
For every subscription the server SHALL send `snapshot_meta` with the total count and a `counters` object before any rows. The keys of `counters` SHALL be defined per subscription type by the owning domain, and all values SHALL come from maintained counters, not from counting rows on request. Every `delta` of a subscription with counters SHALL carry the current `counters` together with the current total.

#### Scenario: Opening the library
- **WHEN** a client subscribes to the track list
- **THEN** the total number of tracks is displayed before the first rows arrive

#### Scenario: Job list counters
- **WHEN** a client subscribes to the job list
- **THEN** `snapshot_meta` contains the total and the counters defined by the jobs domain (e.g. running, failed)

#### Scenario: Counters stay live
- **WHEN** a job of a subscribed job list finishes
- **THEN** the delta for that job carries the updated counters (e.g. one fewer running, one more done)
