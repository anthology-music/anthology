# Proposal

## Why

The specs link videos to recordings but do not say how a video's audio relates to the "one original per recording" model: whether it can replace or be replaced by an audio original, and whether an existing video counts in duplicate checks for audio orders. Music videos often use a different mix and concert videos are different recordings, so treating video audio as an audio variant would produce wrong replacements.

## What Changes

- Videos SHALL be a separate media type: a video's audio track SHALL never be an audio original and SHALL not take part in quality ranking or replacement of audio originals.
- Duplicate checks for audio orders SHALL consider only audio originals; an existing video SHALL not prevent an audio download and vice versa.
- If a recording has no audio original but a linked video, it SHALL be playable as audio only through the video's audio track.
- Duplicate videos SHALL be detected by source and content hash; a video with a higher resolution of the same source item SHALL replace the existing video.

## Capabilities

### New Capabilities

_None._

### Modified Capabilities

- `video`: new requirements "Video is not an audio original", "Audio fallback from video" and "Video duplicates".
- `sources`: new requirement "Separate duplicate checks for audio and video".

## Impact

- **Domains:** video, sources. library unchanged (its originals are audio only, which this change makes explicit from the video side).
- **Data model:** `VideoFile.contentHash : String` and `VideoFile.sourceItemId : String [0..1]`; the `VideoFile`–`QualityAnalysis` relation is removed (audio quality analysis is not used for videos). Migration only once the schema exists.
- **Docs:** ADR 0016 amended.
- **Non-functional requirements (2 s, 500,000 tracks):** none.
