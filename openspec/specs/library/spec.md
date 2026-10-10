# library Specification

## Purpose
Manage the shared music library so that every recording is stored exactly once, while albums, compilations and other contexts reference it and present context-specific metadata.

## Requirements

### Requirement: Single original per recording
The system SHALL store at most one original audio file per recording and SHALL represent every additional album or compilation appearance as a reference (track context), not as a copy.

#### Scenario: Same recording on two albums
- **WHEN** a recording that already exists is added as part of a second album
- **THEN** no second audio file is stored
- **AND** a new track context links the second album to the existing recording

### Requirement: Context-dependent metadata
The system SHALL deliver album, track number, album artist and cover from the track context the recording is accessed through, and SHALL keep only neutral base tags (title, artist, recording ID, ISRC) in the original file.

#### Scenario: Playing from a compilation
- **WHEN** a client plays a recording via a compilation
- **THEN** the client receives the compilation's album title, track number and album artist
- **AND** the original file on disk is not modified

### Requirement: Recording identification
The system SHALL identify recordings in this order: ISRC, acoustic fingerprint (AcoustID), and only as a suggestion a fuzzy match of artist, title and duration (±2 s). Fuzzy matches MUST NOT be merged automatically.

#### Scenario: Fuzzy match only
- **WHEN** a new file matches an existing recording only by artist, title and duration
- **THEN** the match is added to the review list as a suggestion
- **AND** the recordings stay separate until a user confirms

### Requirement: Quality-based replacement
The system SHALL replace an original with a new file of the same recording when the new file has a higher effective quality (see quality-analysis), and SHALL keep all references and track contexts unchanged.

#### Scenario: Better source arrives
- **WHEN** a recording stored as Opus 160 from YouTube is acquired again as FLAC 16/44.1 from Tidal
- **THEN** the FLAC file becomes the original
- **AND** cached transcodes of the old original are invalidated

### Requirement: Supported audio formats
The system SHALL support FLAC, WAV, AIFF, ALAC, MP3, AAC, Opus and Ogg Vorbis as originals. WAV and FLAC with equal sample rate and bit depth SHALL be treated as equal quality.

#### Scenario: WAV import
- **WHEN** a WAV file is added
- **THEN** it is identified, deduplicated and playable like any other format
- **AND** its metadata is taken from the database even if the WAV tags are incomplete

### Requirement: Change tracking
The system SHALL assign a monotonically increasing change sequence number to every change of shared library data.

#### Scenario: Tag edit
- **WHEN** an editor changes the title of a track context
- **THEN** a new change sequence number is recorded for that change
- **AND** connected clients receive the change as a delta (see sync-protocol)

### Requirement: Library scale
The system SHALL support libraries of at least 500,000 tracks while meeting the interaction budget of the sync-protocol spec.

#### Scenario: Large library browsing
- **WHEN** a client opens the track list of a library with 500,000 tracks
- **THEN** the total count and the first visible rows are interactive within 2 seconds
