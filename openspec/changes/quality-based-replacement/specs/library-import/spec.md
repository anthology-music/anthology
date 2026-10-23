## ADDED Requirements

### Requirement: Quality comparison of duplicate candidates
When a file of an import matches an existing recording or another file of the source by identifiers or acoustic fingerprint, the system SHALL compare the effective quality of both files before the report. The file SHALL count as "replaces lower quality" only if both analyses are conclusive and its effective quality is higher; an inconclusive comparison SHALL count as "suspicious quality" and SHALL NOT replace anything.

#### Scenario: Better file of an existing recording
- **WHEN** an imported FLAC is identified as a recording whose original is an MP3 with conclusive results for both
- **THEN** the report counts the FLAC as "replaces lower quality"

#### Scenario: Upscaled file is not better
- **WHEN** an imported FLAC of an existing recording is analysed as lossy origin with high confidence and the existing original is a genuine AAC 256
- **THEN** the FLAC counts as "already present" and becomes a track context

#### Scenario: Inconclusive comparison
- **WHEN** the analysis of an imported candidate is not conclusive
- **THEN** it counts as "suspicious quality" and the existing original stays

### Requirement: Best copy within the source
Among duplicates within the source, the file with the highest effective quality SHALL become the original and the others track contexts.

#### Scenario: Best copy within the source
- **WHEN** a folder contains the same recording as MP3 in one album folder and as genuine FLAC in another
- **THEN** the FLAC becomes the original and the MP3 occurrence a track context

### Requirement: Replaced originals per import
An import SHALL let the admin choose whether replaced managed originals are deleted; the choice SHALL apply to all replacements of that import and SHALL default to deleting. A replaced managed original SHALL be deleted only after the checksum of the new original has been verified; otherwise, and when the admin chose to keep them, it SHALL be kept as superseded. Replaced referenced originals SHALL never be deleted.

#### Scenario: Default deletes after verification
- **WHEN** an import with the default option replaces a managed MP3 original by a FLAC
- **THEN** the FLAC becomes the original, its checksum is verified, and then the MP3 file is deleted

#### Scenario: Keep replaced originals
- **WHEN** the admin unchecked the deletion option before confirming the report
- **THEN** the replaced managed files are kept and listed in the report of superseded files

#### Scenario: Referenced original replaced
- **WHEN** an import replaces a referenced original
- **THEN** the referenced file stays unchanged at its location and is listed as superseded, whatever the option says
