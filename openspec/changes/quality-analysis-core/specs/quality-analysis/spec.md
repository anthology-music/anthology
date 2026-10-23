## ADDED Requirements

### Requirement: Analysis job
Editors and admins SHALL be able to start the quality analysis of all audio files without a stored result as a background job (the quality check of the whole library; acquisitions analyse only duplicate candidates, ADR 0022). A re-run on request SHALL analyse again the files whose result was produced by an older version of the analysis.

#### Scenario: Whole library on request
- **WHEN** an editor starts the quality check after an import has created 300 originals
- **THEN** a quality analysis job checks the files without a stored result

#### Scenario: One job at a time
- **WHEN** an editor starts the analysis while one is running
- **THEN** the request is refused and the running job continues

### Requirement: Stored result
For every analysed audio data the system SHALL store the status, the confidence, a finding with its measured values, the effective quality tier and, where measured, the cutoff frequency, the effective sample rate, the effective bit depth and the estimated bitrate of a lossy origin. Only a result with high confidence SHALL set the effective quality of the files; for other results the effective quality SHALL stay unknown until a user decides.

#### Scenario: Lossy origin detected
- **WHEN** a FLAC file of a 1998 release has a steep cutoff at 16 kHz
- **THEN** its status is "upscaled" with high confidence, the finding names lossy origin at about 128 kbit/s, and its effective quality is lossy

#### Scenario: Fake hi-res
- **WHEN** a 24-bit/96 kHz FLAC has no content above 22 kHz
- **THEN** its status is "upscaled" with high confidence and its effective quality is CD quality

#### Scenario: Genuine CD rip
- **WHEN** a 16-bit/44.1 kHz FLAC has content up to 21 kHz without a steep edge
- **THEN** its status is "genuine" with high confidence and its effective quality is CD quality

#### Scenario: Not conclusive
- **WHEN** a file shows a steep cutoff that matches no known encoder
- **THEN** its status is "suspicious" with medium confidence and its effective quality stays unknown

### Requirement: Quality overview
The system SHALL show editors and admins the number of analysed audio data per status and the number still unanalysed, updated live.

#### Scenario: Counts after a run
- **WHEN** an admin opens the library settings after an analysis
- **THEN** the numbers of genuine, suspicious, upscaled and unanalysed files are shown
