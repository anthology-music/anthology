# Spec Delta

## MODIFIED Requirements

### Requirement: Output adapters
The system SHALL implement every playback target as an output adapter with a common interface (discover, play, pause, resume, stop, seek, volume, state, group/ungroup where supported). Each adapter SHALL declare per device the audio formats it can play, and audio for that device SHALL be delivered according to the transcoding spec's format-aware delivery.

#### Scenario: New output type
- **WHEN** an output adapter for a new system is installed
- **THEN** its devices appear in the output picker without changes to core code

#### Scenario: Output cannot play the original's format
- **WHEN** a recording whose original is Opus is played on an output that does not declare Opus
- **THEN** the output receives a compatibility transcode
