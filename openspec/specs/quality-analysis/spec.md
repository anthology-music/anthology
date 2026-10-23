# quality-analysis Specification

## Purpose
Determine the effective quality of every audio file so that upscaled files (e.g. MP3 stored as FLAC, fake hi-res) are recognised and ranked correctly.

## Requirements

### Requirement: Declared and effective quality
The system SHALL store for every audio file both the declared quality (format, sample rate, bit depth, bitrate) and an estimated effective quality.

#### Scenario: MP3 saved as FLAC
- **WHEN** a FLAC file shows a spectral cutoff at 16 kHz
- **THEN** its effective quality is "lossy origin, about 128 kbit/s"

### Requirement: Detection methods
The analysis SHALL check spectral cutoff, content above 22 kHz for high sample rates, effective bit depth, lossy-encoder patterns and plausibility with the source.

#### Scenario: Fake 24-bit
- **WHEN** the lower 8 bits of a 24-bit file carry no information
- **THEN** its effective bit depth is 16

### Requirement: Confidence instead of verdict
Each result SHALL carry a finding text, a confidence (high, medium, low) and a status (genuine, suspicious, upscaled, confirmed genuine). Only high-confidence results SHALL be classified automatically; others SHALL go to the review list with a spectrogram. Older recordings SHALL be evaluated more tolerantly.

#### Scenario: Old recording with little treble
- **WHEN** a 1960s recording shows a cutoff at 15 kHz
- **THEN** it is marked "suspicious" with low confidence, not "upscaled"

### Requirement: Effective quality drives decisions
Quality ranking, replacement, duplicate resolution and transcoding SHALL use the effective quality.

#### Scenario: Genuine 320 vs fake FLAC
- **WHEN** a genuine AAC 320 and an upscaled FLAC of the same recording exist
- **THEN** the AAC 320 file is kept as the original

### Requirement: Optional lossless reduction
The system MAY reduce upscaled lossless files losslessly to their effective resolution, and SHALL replace the original only after user confirmation and checksum verification.

#### Scenario: Reduce fake hi-res
- **WHEN** a user confirms reduction of a fake 24/96 file
- **THEN** it is stored as 16/44.1 and the reduction is verified before the old file is removed

### Requirement: Efficient execution
The analysis SHALL run as a throttled background step, SHALL analyse excerpts first and the full file only when inconclusive, and SHALL store results per audio hash so that no file is analysed twice.

#### Scenario: Same audio twice
- **WHEN** a file with an already analysed audio hash is added
- **THEN** the stored result is reused

### Requirement: Analysis on acquisition
During imports, uploads, downloads and CD imports the system SHALL analyse only files that are duplicate candidates of an existing recording or of another acquired file, together with the files they are compared with. Other files SHALL be analysed only when a user starts the quality check of the whole library.

#### Scenario: New album without duplicates
- **WHEN** an import adds an album whose recordings are not in the library
- **THEN** its files are not analysed during the import
- **AND** they are analysed when an editor starts the quality check of the library

#### Scenario: Candidate analysed once
- **WHEN** a file was analysed as a duplicate candidate during an import
- **THEN** the later quality check of the library reuses its result
