# sync-protocol Specification

## Purpose
Keep clients usable immediately by loading only the needed subset first and streaming the rest, through all layers: database, server, WebSocket protocol and client.

## Requirements

### Requirement: WebSocket connection
Each client SHALL keep one authenticated WebSocket connection to the server and SHALL multiplex all list and status subscriptions over it.

#### Scenario: Connect
- **WHEN** a client connects and sends `hello` with its token and last known change sequence
- **THEN** the server answers with `welcome` including the current change sequence

### Requirement: Counts first
For every subscription the server SHALL send `snapshot_meta` with total count and status counters before any rows.

#### Scenario: Opening the library
- **WHEN** a client subscribes to the track list
- **THEN** the total number of tracks is displayed before the first rows arrive

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
On reconnect the server SHALL send only the deltas missed since the client's last change sequence, or request a new snapshot of the visible window if the gap is too large.

#### Scenario: Short network loss
- **WHEN** a client reconnects after a 30-second loss
- **THEN** it receives the missed deltas and no full reload happens

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
