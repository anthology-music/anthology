# Spec Delta

## MODIFIED Requirements

### Requirement: Media over HTTP
Audio SHALL be delivered over HTTP with range requests, and video SHALL be delivered adaptively over HLS (see video); neither SHALL be delivered over the WebSocket.

#### Scenario: Seeking
- **WHEN** the user seeks within a track
- **THEN** the client requests the needed byte range over HTTP

#### Scenario: Seeking in a video
- **WHEN** the user seeks within a video
- **THEN** the client loads the HLS segments for the new position over HTTP
- **AND** no media data is sent over the WebSocket
