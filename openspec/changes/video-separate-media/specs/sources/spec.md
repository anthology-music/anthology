# Spec Delta

## ADDED Requirements

### Requirement: Separate duplicate checks for audio and video
Duplicate checks for audio orders SHALL consider only audio originals, and duplicate checks for video orders SHALL consider only videos (see video).

#### Scenario: Video exists, audio ordered
- **WHEN** a recording exists only as a linked video and the user orders it as audio only
- **THEN** the audio is downloaded and becomes the audio original

#### Scenario: Audio exists, video ordered
- **WHEN** a recording exists as FLAC and the user orders its music video
- **THEN** the video is downloaded and linked to the recording
