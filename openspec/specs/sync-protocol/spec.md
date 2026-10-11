# sync-protocol Specification

## Purpose
Keep clients usable immediately by loading only the needed subset first and streaming the rest, through all layers: database, server, WebSocket protocol and client.

## Requirements

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

### Requirement: Windowed chunks
The server SHALL deliver rows in chunks for the window requested by the client, prioritising the visible window over background filling, and SHALL use keyset pagination in the database.

#### Scenario: Scrolling
- **WHEN** the client scrolls and sends a new `window`
- **THEN** the server sends the missing rows of that window first
- **AND** the database query does not use OFFSET

### Requirement: Deltas
After the snapshot the server SHALL send only changes (`delta`) for subscribed data, each with a change sequence number.

#### Scenario: Change by another user
- **WHEN** another user edits a track that is visible on this client
- **THEN** the client receives a delta and updates the row without reloading the list

### Requirement: Resume after disconnect
On reconnect the server SHALL send only the deltas missed since the client's last change sequence if that sequence is within the change log retention; otherwise it SHALL send `resync` for each subscription followed by a new snapshot of the visible window.

#### Scenario: Short network loss
- **WHEN** a client reconnects after a 30-second loss
- **THEN** it receives the missed deltas and no full reload happens

#### Scenario: Client offline for two weeks
- **WHEN** a client reconnects with a change sequence older than the change log retention
- **THEN** each subscription receives `resync`, counts first and then the rows of the visible window

### Requirement: Backpressure
The server MUST NOT send more chunks than the client has acknowledged or can buffer.

#### Scenario: Slow mobile client
- **WHEN** a slow client has not acknowledged previous chunks
- **THEN** the server pauses sending further chunks for that subscription

### Requirement: Media over HTTP
Audio and video SHALL be delivered over HTTP with range requests, not over the WebSocket.

#### Scenario: Seeking
- **WHEN** the user seeks within a track
- **THEN** the client requests the needed byte range over HTTP

### Requirement: Interaction budget
The current view SHALL be interactive within 2 seconds (95th percentile) and SHALL show first data from the local cache within 300 milliseconds.

#### Scenario: Cold start without cache in the LAN
- **WHEN** a client starts without local cache on the local network
- **THEN** the current view is interactive within 2 seconds

### Requirement: Rule-based selection
Bulk actions SHALL accept a selection rule (e.g. folder plus filter) instead of an explicit list of IDs.

#### Scenario: Select whole folder
- **WHEN** the user selects a folder with 5,000 files and applies a tag change
- **THEN** the client sends one rule and receives live progress

### Requirement: Changes in commit order
Change sequence numbers SHALL be assigned in the order in which the changes became committed, so that a client that has received a number never misses a change with a smaller number.

#### Scenario: Overlapping transactions
- **WHEN** a long transaction starts before a short one but commits after it
- **THEN** the change of the short transaction receives the smaller change sequence number
- **AND** a client resuming after the short transaction's change still receives the long transaction's change

### Requirement: Revocation across server processes
When an installation runs several server processes, signing out a device or deactivating an account through one process SHALL take effect in all processes within one second.

#### Scenario: Sign-out on another process
- **WHEN** a device is signed out through server process A
- **THEN** server process B rejects that device's next request within one second

### Requirement: Authentication timeout
The server SHALL close a WebSocket connection that does not send a valid `hello` within 10 seconds, and SHALL NOT accept the access token in the connection URL.

#### Scenario: Silent connection
- **WHEN** a client opens the WebSocket and sends nothing for 10 seconds
- **THEN** the server closes the connection

### Requirement: Jump to a position
A client SHALL be able to request any window of a subscribed list by position, and the server SHALL deliver it without `OFFSET` queries within the interaction budget.

#### Scenario: Dragging the scroll bar
- **WHEN** a client of a list with 500,000 rows requests the window starting at row 250,000
- **THEN** the server delivers the rows of that window within 2 seconds
- **AND** no database query uses OFFSET

### Requirement: Deltas across server processes
Deltas and resume SHALL work the same when an installation runs several server processes, with clients connected to different processes.

#### Scenario: Edit on another process
- **WHEN** a change is made through server process A while a client is subscribed through process B
- **THEN** the client receives the delta through process B

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
