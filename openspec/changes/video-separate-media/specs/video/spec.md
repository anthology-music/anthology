# Spec Delta

## ADDED Requirements

### Requirement: Video is not an audio original
A video's audio track SHALL never become the audio original of a recording and SHALL NOT take part in quality ranking, duplicate resolution or replacement of audio originals.

#### Scenario: Music video with better audio codec
- **WHEN** a music video with high-bitrate audio is linked to a recording whose original is MP3 128
- **THEN** the MP3 remains the audio original
- **AND** the video stays a separate video

### Requirement: Audio fallback from video
If a recording has no audio original but a linked video, the system SHALL offer audio-only playback of the recording through the video's audio track.

#### Scenario: Recording only available as video
- **WHEN** a user plays a recording that exists only as a linked concert video
- **THEN** the audio of the video is played as audio only (see "No duplicate audio")

### Requirement: Video duplicates
The system SHALL detect duplicate videos by source item and content hash, SHALL not store the same video twice, and SHALL replace a video with a higher-resolution version of the same source item.

#### Scenario: Same video ordered twice
- **WHEN** a user orders a YouTube video that is already stored in the same resolution
- **THEN** it is not downloaded again and the order item is marked "already present"

#### Scenario: Higher resolution available
- **WHEN** a video stored in 720p is ordered again in 1080p from the same source item
- **THEN** the 1080p version replaces the 720p video and its links and chapters are kept
