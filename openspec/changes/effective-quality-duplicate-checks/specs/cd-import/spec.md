# Spec Delta

## MODIFIED Requirements

### Requirement: Duplicate check before ripping
Before ripping, every track SHALL be checked against the library by effective quality and marked as new, already present (skip) when the existing original is at least genuine CD quality (lossless, 16 bit/44.1 kHz), or present in lower quality (replace) otherwise.

#### Scenario: Two tracks already present
- **WHEN** two tracks of the CD already exist as FLAC with genuine CD quality
- **THEN** they are skipped and not ripped

#### Scenario: Upscaled FLAC present
- **WHEN** a track of the CD exists as FLAC whose effective quality is "lossy origin, about 128 kbit/s"
- **THEN** the track is marked "replace", ripped, and the rip becomes the original
