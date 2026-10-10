# Spec Delta

## Purpose

Let users take selected albums and playlists offline on their devices in a chosen quality, within a storage limit and respecting metered connections, and synchronise offline changes back to the server.

## ADDED Requirements

### Requirement: Explicit offline selection
Users SHALL be able to mark albums and playlists for offline use on a device; only marked content SHALL be stored offline, and a marked playlist SHALL follow later changes to its entries.

#### Scenario: Album offline
- **WHEN** a user marks an album for offline use on the phone
- **THEN** all its tracks are downloaded to the phone and playable without connection

#### Scenario: Playlist changes
- **WHEN** a track is added to a playlist that is marked for offline use
- **THEN** the track is downloaded on the next sync

### Requirement: Platform support
The native desktop and mobile apps SHALL store offline content persistently; the web app (PWA) SHALL offer offline storage on a best-effort basis within the browser's storage and SHALL tell the user that it may be removed by the browser.

#### Scenario: PWA on iOS
- **WHEN** a user marks an album offline in the PWA on iOS
- **THEN** the app explains that the browser may delete offline content and recommends the native app

### Requirement: Offline quality
Offline copies SHALL be stored in the offline bitrate set for the user and device (default: the device's streaming bitrate), using format-aware delivery (see transcoding).

#### Scenario: Different offline quality
- **WHEN** a phone streams at 128 kbit/s and its offline bitrate is 256 kbit/s
- **THEN** offline copies on the phone are stored at 256 kbit/s

### Requirement: Offline limit
The system SHALL enforce the offline limit per user and device; explicitly marked content SHALL NOT be removed automatically, and when the limit would be exceeded the user SHALL be warned and the remaining items SHALL not be downloaded.

#### Scenario: Limit reached
- **WHEN** a user marks a playlist whose size exceeds the remaining offline space
- **THEN** the user is warned with the missing space
- **AND** no previously stored offline content is deleted

### Requirement: Connection rules
With Wi-Fi-only sync enabled, offline downloads SHALL run only on Wi-Fi or unmetered connections; interrupted downloads SHALL resume where they stopped.

#### Scenario: Leaving Wi-Fi
- **WHEN** a device with Wi-Fi-only sync leaves Wi-Fi during an offline download
- **THEN** the download pauses and resumes on the next Wi-Fi connection without restarting finished parts

### Requirement: Warning on metered connections
On a metered connection the client SHALL warn the user before starting any transfer that is not streaming for immediate playback (offline sync, file downloads) and SHALL start it only after confirmation.

#### Scenario: Offline sync on mobile data
- **WHEN** Wi-Fi-only sync is disabled and a user starts an offline sync on mobile data
- **THEN** a warning with the expected data volume appears and the sync starts only after confirmation

#### Scenario: Streaming on mobile data
- **WHEN** a user plays a track on mobile data
- **THEN** it streams without a warning

### Requirement: Shared devices
On shared devices identical recordings SHALL be stored only once, and each user SHALL see and play only their own offline content.

#### Scenario: Same album for two users
- **WHEN** two users of a family tablet both mark the same album offline in the same quality
- **THEN** the files are stored once and the album appears in both users' offline content

### Requirement: Offline changes
Play history, favorites and playlist edits made offline SHALL be stored locally and synchronised on the next connection with their original timestamps; for favorites the most recent change SHALL win, and playlist edits SHALL be merged without losing entries.

#### Scenario: Listening on a plane
- **WHEN** a user plays ten tracks offline and reconnects
- **THEN** the ten plays appear in the history with the times they were played

### Requirement: Keeping offline copies current
When the original of an offline recording is replaced by one of higher effective quality, the offline copy SHALL be renewed on the next sync if the offline bitrate allows a better copy; metadata changes SHALL be applied without re-downloading audio.

#### Scenario: Album title corrected
- **WHEN** an editor corrects the title of an album that is offline on a phone
- **THEN** the phone shows the new title after the next sync without downloading the tracks again
