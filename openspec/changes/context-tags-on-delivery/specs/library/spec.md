# Spec Delta

## ADDED Requirements

### Requirement: Unchanged originals for playback
When the original is delivered for playback (own clients, network outputs), the system SHALL deliver the bytes of the active original unchanged and SHALL support range requests on them. Context metadata SHALL be delivered separately (API, DIDL-Lite).

#### Scenario: Seeking in a FLAC original
- **WHEN** a client plays a FLAC original and requests a byte range
- **THEN** the server returns exactly that byte range of the original file

#### Scenario: Playback via a compilation
- **WHEN** a client plays a recording via a compilation without transcoding
- **THEN** the audio bytes are those of the original file
- **AND** the compilation's metadata is delivered through the API

### Requirement: Context-tagged downloads
When a user downloads or exports an original, the system SHALL deliver a copy tagged with the complete context tags (including cover, ISRC and recording ID) of the context it was requested from, and SHALL support range requests on that copy.

#### Scenario: Download from a compilation
- **WHEN** a user downloads a track from a compilation
- **THEN** the file contains the compilation's album title, track number and album artist
- **AND** the original file is not modified

#### Scenario: Resumed download
- **WHEN** a download of a tagged copy is interrupted and resumed with a range request
- **THEN** the server continues with the requested bytes of the same tagged copy

### Requirement: Tagged copy cache
Tagged copies SHALL be cached per original and context, shared between users and devices, counted against the same size limit as transcodes, and invalidated when the context's tags or the original change. A tagged copy MUST NOT be treated as an original.

#### Scenario: Tag change invalidates the copy
- **WHEN** an editor changes the album title of a context with a cached tagged copy
- **THEN** the cached copy is discarded and recreated on the next download

#### Scenario: Copy is not an original
- **WHEN** duplicate detection or quality ranking runs
- **THEN** tagged copies are ignored
