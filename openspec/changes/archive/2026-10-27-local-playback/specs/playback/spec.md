# Spec Delta

## ADDED Requirements

### Requirement: Playback on this device
The client SHALL play tracks on the device it runs on, fetching the audio over HTTP with range requests from signed URLs (see sync-protocol, Signed media URLs). Until transcoding exists, the device SHALL receive the original.

#### Scenario: Playing an album in the browser
- **WHEN** a user presses "Play" on an album in the browser
- **THEN** the first track starts playing in the browser
- **AND** the audio is requested with a signed URL, without auth headers

#### Scenario: Seeking
- **WHEN** the user drags the seek bar to the middle of a track
- **THEN** playback continues there after a range request for that part of the file

### Requirement: Play queue
The system SHALL keep one play queue per user and device on the server with its entries in order, the current entry, the position within it and whether it plays; the queue SHALL be available as a subscription that follows every change, and SHALL hold at most 10,000 entries.

#### Scenario: Queue follows changes
- **WHEN** the user adds a track to the queue
- **THEN** the queue subscription receives the new entry at its place

#### Scenario: Long list
- **WHEN** a user starts playback of a list with 50,000 tracks
- **THEN** the queue holds the 10,000 tracks from the chosen one on
- **AND** the user is told that the queue was shortened

#### Scenario: Removed track
- **WHEN** a track in the queue is removed from the library
- **THEN** its entry leaves the queue

### Requirement: Starting playback
The client SHALL offer to play an album, to play a list from a chosen track, to play a track next and to add tracks to the end of the queue; playing an album or a list SHALL replace the queue, "play next" and "add to queue" SHALL keep it.

#### Scenario: Play from a track
- **WHEN** a user starts the third track of an album
- **THEN** the queue holds the album's tracks in order and playback starts with the third

#### Scenario: Play next
- **WHEN** a user chooses "play next" on a track while another track plays
- **THEN** the track is inserted after the current entry and the current track keeps playing

### Requirement: Resume
The client SHALL report the current entry, the position and whether it plays to the server while playing and on every pause, skip and seek; after a reload the client SHALL show the queue's current entry at the reported position, paused.

#### Scenario: Reload during playback
- **WHEN** the user reloads the page two minutes into a track
- **THEN** the player shows that track at about two minutes, paused, and continues there on "play"

### Requirement: Player controls
The client SHALL show the current track with title, artist and album, previous, play/pause and next, a seek bar with elapsed and total time, a volume control and the queue, and SHALL answer the operating system's media keys.

#### Scenario: Media key
- **WHEN** the user presses the "next" media key while a track plays
- **THEN** the next entry of the queue starts

#### Scenario: Previous
- **WHEN** the user presses "previous" more than three seconds into a track
- **THEN** the track starts again from the beginning

### Requirement: Formats the device cannot play
The client SHALL detect which original formats the device can play, SHALL mark the others as not playable on this device and SHALL skip them during playback; such entries SHALL stay in the queue.

#### Scenario: AIFF in the browser
- **WHEN** the queue reaches an AIFF original in a browser that cannot play AIFF
- **THEN** the entry is marked "not playable on this device" and the next entry starts
