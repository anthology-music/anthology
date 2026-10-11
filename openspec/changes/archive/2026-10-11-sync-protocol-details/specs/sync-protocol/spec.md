# Spec Delta

## MODIFIED Requirements

### Requirement: WebSocket connection
Each client SHALL keep one authenticated WebSocket connection to the server and SHALL multiplex all list and status subscriptions over it. `hello` and `welcome` SHALL carry the protocol version; if the server does not support the client's version it SHALL close the connection with close code 4426, and the client SHALL ask the user to update.

#### Scenario: Connect
- **WHEN** a client connects and sends `hello` with its token and last known change sequence
- **THEN** the server answers with `welcome` including the current change sequence

#### Scenario: Outdated client
- **WHEN** a client sends `hello` with a protocol version the server no longer supports
- **THEN** the server closes the connection with close code 4426
- **AND** the client shows a hint to update the app

### Requirement: Counts first
For every subscription the server SHALL send `snapshot_meta` with the total count and a `counters` object before any rows. The keys of `counters` SHALL be defined per subscription type by the owning domain, and all values SHALL come from maintained counters, not from counting rows on request.

#### Scenario: Opening the library
- **WHEN** a client subscribes to the track list
- **THEN** the total number of tracks is displayed before the first rows arrive

#### Scenario: Job list counters
- **WHEN** a client subscribes to the job list
- **THEN** `snapshot_meta` contains the total and the counters defined by the jobs domain (e.g. running, failed)

### Requirement: Resume after disconnect
On reconnect the server SHALL send only the deltas missed since the client's last change sequence if that sequence is within the change log retention; otherwise it SHALL send `resync` for each subscription followed by a new snapshot of the visible window.

#### Scenario: Short network loss
- **WHEN** a client reconnects after a 30-second loss
- **THEN** it receives the missed deltas and no full reload happens

#### Scenario: Client offline for two weeks
- **WHEN** a client reconnects with a change sequence older than the change log retention
- **THEN** each subscription receives `resync`, counts first and then the rows of the visible window

## ADDED Requirements

### Requirement: Message schema
All protocol messages SHALL use one envelope with type, subscription ID where applicable, change sequence where applicable, and payload, and SHALL conform to a schema published with the server; client types SHALL be generated from it.

#### Scenario: Unknown message
- **WHEN** the server receives a message that does not conform to the schema
- **THEN** it answers with an error message naming the problem and keeps the connection open

### Requirement: Global change sequence
The system SHALL use one monotonically increasing change sequence for all changes to shared data, personal data, jobs and devices.

#### Scenario: Favorite and tag edit
- **WHEN** a user marks a favorite and another user edits a tag shortly after
- **THEN** both changes have distinct, increasing change sequence numbers from the same sequence

### Requirement: Delta visibility
The server SHALL send a delta only to connections that subscribed to the affected data and are allowed to see it; personal changes SHALL only be sent to the owning user's connections, device changes only to that device.

#### Scenario: Private favorite
- **WHEN** a user marks a track as favorite
- **THEN** that user's other devices receive the delta
- **AND** no other user's connection receives it

### Requirement: Change log retention
The system SHALL keep the change log for a configurable retention period with a default of 7 days and MAY delete older entries.

#### Scenario: Retention elapsed
- **WHEN** change log entries are older than the configured retention
- **THEN** they are removed and clients older than the oldest remaining entry are resynchronised
