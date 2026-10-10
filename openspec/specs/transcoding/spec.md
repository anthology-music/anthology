# transcoding Specification

## Purpose
Deliver music to each device in the bitrate configured for that user and device, while the original on the server stays unchanged.

## Requirements

### Requirement: Bitrate per user and device
The system SHALL deliver audio in the bitrate set for the current user and device: Original, 320, 256, 192 or 128 kbit/s. 128 kbit/s SHALL be the minimum.

#### Scenario: Phone with 128 kbit/s
- **WHEN** a user whose phone is set to 128 kbit/s plays a FLAC original
- **THEN** the phone receives AAC at 128 kbit/s

### Requirement: Never upscale
The system MUST NOT transcode to a bitrate above the effective quality of the original; in that case it SHALL deliver the original.

#### Scenario: Low-quality original
- **WHEN** the device is set to 320 kbit/s and the original is Opus 160
- **THEN** the original is delivered unchanged

### Requirement: Target format
Transcoded files SHALL use AAC in an M4A container.

#### Scenario: Transcode output
- **WHEN** a transcode is created
- **THEN** the result is an AAC M4A file

### Requirement: Automatic tagging of transcodes
After every transcode the system SHALL automatically write the complete context tags from the database, including cover, ISRC and recording ID, into the result.

#### Scenario: Tags after FLAC to AAC
- **WHEN** a FLAC original is transcoded to AAC
- **THEN** the result contains all context tags and the cover without any manual step

### Requirement: Shared transcode cache
The system SHALL cache transcodes keyed by recording, bitrate, format and context, share them between users and devices, and invalidate them when tags or the original change.

#### Scenario: Tag change
- **WHEN** an editor changes the album title of a context
- **THEN** cached transcodes for that context are discarded and recreated on next request

### Requirement: Originals untouched
The system MUST NOT modify an original file during transcoding.

#### Scenario: Original checksum
- **WHEN** a transcode is created
- **THEN** the original's audio hash is unchanged
