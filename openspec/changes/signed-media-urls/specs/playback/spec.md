# Spec Delta

## ADDED Requirements

### Requirement: Media URLs for network outputs
When the server hands a track to a network output, it SHALL pass a signed media URL bound to that output zone, valid for the track's duration plus one hour but at most 24 hours, so that the output can fetch the stream without further authentication. The server SHALL hand over each track when it is due, so that no URL needs to outlive its track.

#### Scenario: Raumfeld plays a long queue
- **WHEN** a user hands a queue of three hours to a Raumfeld zone and closes the client
- **THEN** the speakers fetch every track of the queue with the URL the server handed over for it

#### Scenario: Track paused for a long time
- **WHEN** a track handed to a zone stays paused until its URL has expired and is then resumed
- **THEN** the server hands the track over again with a new URL at the paused position
