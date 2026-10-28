# Spec Delta

## ADDED Requirements

### Requirement: Tagged audio formats
The tagger SHALL read and write tags in every audio format the library accepts: FLAC, MP3, MP4 (AAC and ALAC), Ogg Vorbis, Opus, WAV and AIFF; WAV and AIFF carry their tags in an ID3 chunk.

#### Scenario: WAV original
- **WHEN** the core requests a tagged copy of a WAV original
- **THEN** the copy carries the requested tags in its ID3 chunk and the original's checksum is unchanged
