## ADDED Requirements

### Requirement: Quality badge
Library track rows SHALL show a badge with the effective quality (hi-res lossless, CD quality, lossy) once the file's effective quality is known, and SHALL mark files whose analysis was not conclusive as to be checked. The format label SHALL stay unchanged.

#### Scenario: Upscaled FLAC
- **WHEN** a track's FLAC file was analysed as lossy origin with high confidence
- **THEN** its row shows `FLAC 16/44.1` and the badge "lossy"

#### Scenario: Suspicious file
- **WHEN** a track's file was analysed with medium confidence
- **THEN** its row shows the format label and a "check" marker, but no quality badge
