# Spec Delta

## ADDED Requirements

### Requirement: Signed media URLs
Every media request (original, transcode, tagged copy, HLS playlist and segment) SHALL be authorised by a signed URL issued by the server and bound to one media variant, the user, the device or output, and an expiry; requests with a missing, invalid or expired signature SHALL be rejected. Range requests SHALL work with signed URLs.

#### Scenario: Playing a track in the browser
- **WHEN** a client starts playing a track
- **THEN** it obtains a signed URL for the track's variant and the audio element requests it without auth headers

#### Scenario: Expired URL
- **WHEN** a request uses a signed URL whose expiry has passed
- **THEN** the server rejects it and no media data is sent

#### Scenario: URL for a different variant
- **WHEN** a signed URL for a 128 kbit/s transcode is altered to point to the original
- **THEN** the server rejects the request

### Requirement: Short-lived client media URLs
Signed media URLs for client devices SHALL expire after at most one hour, and clients SHALL request new URLs for queued items before they expire.

#### Scenario: Long queue
- **WHEN** a client has queued tracks that will play in two hours
- **THEN** it requests fresh signed URLs for them shortly before they play

### Requirement: Token renewal on an open connection
A client SHALL renew its access token on an open WebSocket by sending an `auth` message with the new token; when the token of a connection expires without renewal, the server SHALL close the connection with a dedicated close code, and the client SHALL reconnect and resume from its last change sequence.

#### Scenario: Renewal before expiry
- **WHEN** a client sends `auth` with a new valid access token before the old one expires
- **THEN** the connection and all subscriptions continue unchanged

#### Scenario: Expired token
- **WHEN** a connection's access token expires without renewal
- **THEN** the server closes the connection with the token-expired close code
- **AND** the client obtains a new token, reconnects and receives only the missed deltas
