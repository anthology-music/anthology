# Spec Delta

## MODIFIED Requirements

### Requirement: Duplicate check before download
The system SHALL check every requested track against the library before downloading and SHALL download it only if the source's declared quality is better than the existing original's effective quality. After the download, the effective quality of the new file SHALL decide whether it replaces the existing original (see library and quality-analysis).

#### Scenario: Track already present
- **WHEN** a requested track already exists as FLAC and the source offers AAC 256
- **THEN** the track is not downloaded
- **AND** the job item is marked "already present"

#### Scenario: Offer better than an upscaled file
- **WHEN** a requested track exists as FLAC with effective quality "lossy origin, about 128 kbit/s" and the source offers FLAC 16/44.1
- **THEN** the track is downloaded

#### Scenario: Download turns out not better
- **WHEN** a downloaded file's analysis shows with high confidence that it is not better than the existing original
- **THEN** the downloaded file is discarded and the existing original stays
- **AND** the job item is marked "not better than existing"

#### Scenario: Inconclusive analysis
- **WHEN** the analysis of a downloaded file has medium or low confidence
- **THEN** the file is kept until a user decides in the review list whether it replaces the existing original
- **AND** the job item is marked "needs review"
