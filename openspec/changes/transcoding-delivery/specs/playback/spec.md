# Spec Delta

## MODIFIED Requirements

### Requirement: Playback on this device
The client SHALL play tracks on the device it runs on, fetching the audio over HTTP with range requests from signed URLs (see sync-protocol, Signed media URLs). The device SHALL receive the original or a transcode as the transcoding spec decides for its bitrate setting and its playable formats.

#### Scenario: Playing an album in the browser
- **WHEN** a user presses "Play" on an album in the browser
- **THEN** the first track starts playing in the browser
- **AND** the audio is requested with a signed URL, without auth headers

#### Scenario: Seeking
- **WHEN** the user drags the seek bar to the middle of a track
- **THEN** playback continues there after a range request for that part of the file

#### Scenario: Bitrate setting
- **WHEN** a browser set to 128 kbit/s plays a FLAC original
- **THEN** it receives AAC at 128 kbit/s

### Requirement: Formats the device cannot play
The client SHALL detect which formats the device can play and report them to the server; when no delivery is possible for an entry (e.g. its transcode failed), the client SHALL mark it as not playable on this device and SHALL skip it during playback; such entries SHALL stay in the queue.

#### Scenario: AIFF in the browser
- **WHEN** the queue reaches an AIFF original in a browser that cannot play AIFF
- **THEN** the browser receives a transcode and plays it

#### Scenario: Failed transcode
- **WHEN** the transcode of an entry fails
- **THEN** the entry is marked "not playable on this device" and the next entry starts
