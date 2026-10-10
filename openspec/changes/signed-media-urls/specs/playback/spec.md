# Spec Delta

## ADDED Requirements

### Requirement: Media URLs for network outputs
When playback is handed to a network output, the server SHALL pass signed media URLs bound to that output, valid long enough for the handed-over queue but at most 24 hours, so that the output can fetch the streams without further authentication.

#### Scenario: Raumfeld plays a long queue
- **WHEN** a user hands a queue of three hours to a Raumfeld zone and closes the client
- **THEN** the speakers fetch every track of the queue with the URLs they received

#### Scenario: Queue longer than 24 hours
- **WHEN** a queue handed to an output extends beyond 24 hours
- **THEN** the server refreshes the URLs of not yet played items on the output before they expire
