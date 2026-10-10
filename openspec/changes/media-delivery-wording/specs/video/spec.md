# Spec Delta

## MODIFIED Requirements

### Requirement: No duplicate audio
When a video is stored, the system MUST NOT store its audio track as a separate permanent file; audio-only playback SHALL use the audio track extracted into the transcode cache and SHALL deliver it like any audio, with range requests.

#### Scenario: Audio from video
- **WHEN** a user plays a stored video as audio only
- **THEN** no additional permanent audio file is created

#### Scenario: Seeking in audio-only playback
- **WHEN** a user seeks while playing a video as audio only
- **THEN** the client requests a byte range of the extracted audio from the transcode cache
