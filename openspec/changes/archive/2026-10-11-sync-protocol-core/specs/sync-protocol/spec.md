# Spec Delta

## ADDED Requirements

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
