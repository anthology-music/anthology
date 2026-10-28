# Spec Delta

## MODIFIED Requirements

### Requirement: Never upscale
The system MUST NOT transcode to a bitrate above the effective quality of the original; in that case it SHALL deliver the original if the target can play its format. Compatibility transcodes are the only exception (see "Compatibility transcodes"). The delivered quality MUST NOT be presented as better than the original's effective quality.

#### Scenario: Low-quality original
- **WHEN** the device is set to 320 kbit/s, the original is Opus 160 and the device can play Opus
- **THEN** the original is delivered unchanged

#### Scenario: Quality shown for a compatibility transcode
- **WHEN** an Opus 160 original is delivered as AAC 192 for compatibility
- **THEN** the client shows the effective quality of the original, not 192 kbit/s

### Requirement: Target format
Transcoded files SHALL use AAC in an M4A container, or ALAC in an M4A container for lossless compatibility transcodes.

#### Scenario: Transcode output
- **WHEN** a lossy transcode is created
- **THEN** the result is an AAC M4A file

#### Scenario: Lossless compatibility output
- **WHEN** a lossless compatibility transcode is created
- **THEN** the result is an ALAC M4A file

## ADDED Requirements

### Requirement: Format-aware delivery
Each client device SHALL report the audio formats it can play, and the system SHALL deliver an original unchanged only if the target can play its format and its effective quality does not exceed the configured bitrate; otherwise it SHALL deliver a transcode.

#### Scenario: FLAC on a device without FLAC support
- **WHEN** a device set to "Original" cannot play FLAC and plays a FLAC original
- **THEN** the device receives a transcode instead of the FLAC file

#### Scenario: Playable original
- **WHEN** a device set to "Original" can play FLAC and plays a FLAC original
- **THEN** the original is delivered unchanged

### Requirement: Compatibility transcodes
If the target cannot play the original's format, the system SHALL transcode a lossless original with setting "Original" to ALAC when the target supports ALAC, otherwise to AAC 320; and a lossy original to AAC at the lowest bitrate step at or above its effective quality, capped by the configured bitrate.

#### Scenario: Opus on an Apple device
- **WHEN** a device set to 320 kbit/s that cannot play Opus plays an Opus 160 original
- **THEN** it receives AAC at 192 kbit/s

#### Scenario: Cap by device setting
- **WHEN** a device set to 128 kbit/s that cannot play Opus plays an Opus 160 original
- **THEN** it receives AAC at 128 kbit/s

#### Scenario: AIFF with setting Original
- **WHEN** a device set to "Original" that supports ALAC but not AIFF plays an AIFF original
- **THEN** it receives a lossless ALAC M4A transcode

#### Scenario: No ALAC support
- **WHEN** a device set to "Original" supports neither FLAC nor ALAC and plays a FLAC original
- **THEN** it receives AAC at 320 kbit/s
