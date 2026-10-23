## ADDED Requirements

### Requirement: Analysis on acquisition
During imports, uploads, downloads and CD imports the system SHALL analyse only files that are duplicate candidates of an existing recording or of another acquired file, together with the files they are compared with. Other files SHALL be analysed only when a user starts the quality check of the whole library.

#### Scenario: New album without duplicates
- **WHEN** an import adds an album whose recordings are not in the library
- **THEN** its files are not analysed during the import
- **AND** they are analysed when an editor starts the quality check of the library

#### Scenario: Candidate analysed once
- **WHEN** a file was analysed as a duplicate candidate during an import
- **THEN** the later quality check of the library reuses its result
