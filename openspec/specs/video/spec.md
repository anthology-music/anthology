# video Specification

## Purpose
Allow acquiring and playing videos (music videos, concert recordings) in addition to audio, without storing audio twice.

## Requirements

### Requirement: Audio-only or video per order
For sources that support video the system SHALL let the user choose per order between "audio only" (default) and "video" with a maximum resolution, and SHALL show the estimated size before starting.

#### Scenario: Concert video
- **WHEN** a user orders a YouTube link as video with maximum 1080p
- **THEN** the video is stored with picture and sound up to 1080p

### Requirement: No duplicate audio
When a video is stored, the system MUST NOT store its audio track as a separate file; audio-only playback SHALL read the audio from the video or the transcode cache.

#### Scenario: Audio from video
- **WHEN** a user plays a stored video as audio only
- **THEN** no additional permanent audio file is created

### Requirement: Link to recordings and works
The system SHALL link videos to recordings and works where identifiable and SHALL support chapters that are linked to works.

#### Scenario: Medley in a concert video
- **WHEN** a chapter of a concert video is linked to a medley work
- **THEN** the work view offers to play that chapter

### Requirement: Adaptive playback
The system SHALL stream videos adaptively (HLS) and SHALL respect the maximum video resolution set for the user and device.

#### Scenario: Phone on mobile network
- **WHEN** a phone limited to 720p plays a 4K video
- **THEN** it receives at most 720p

### Requirement: Separate video storage
Videos SHALL be stored in a separate storage area with its own limit and usage display.

#### Scenario: Video storage full
- **WHEN** the video storage limit is reached
- **THEN** new video orders are rejected with a message while audio orders continue
