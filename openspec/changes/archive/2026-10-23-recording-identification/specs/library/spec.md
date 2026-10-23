## ADDED Requirements

### Requirement: Identification job
Editors and admins SHALL be able to start the identification of all recordings without MusicBrainz ID as a background job. For each recording the job SHALL look up the ISRC first and, if that does not identify exactly one MusicBrainz recording, the acoustic fingerprint of the recording's active original at AcoustID. Recordings checked without match SHALL be retried by a later run only after 30 days, unless a full re-run is requested.

#### Scenario: Identified by ISRC
- **WHEN** a recording's ISRC belongs to exactly one MusicBrainz recording
- **THEN** the recording gets that MusicBrainz recording ID
- **AND** no fingerprint is computed for it

#### Scenario: Ambiguous ISRC
- **WHEN** a recording's ISRC belongs to several MusicBrainz recordings and only one of them is within ±2 seconds of the recording's duration
- **THEN** the recording gets the ID of that one
- **AND** if none or several are within ±2 seconds, the fingerprint is looked up instead

#### Scenario: Identified by fingerprint
- **WHEN** a recording has no ISRC and AcoustID returns a result with a score of at least 0.9 that names exactly one MusicBrainz recording
- **THEN** the recording gets that MusicBrainz recording ID and the AcoustID

#### Scenario: Recently checked without match
- **WHEN** a recording was checked without match 10 days ago and the job runs again without a full re-run
- **THEN** the recording is skipped

### Requirement: Identification outcome
The system SHALL record for every checked recording the outcome – identified by ISRC, identified by fingerprint, no match, duplicate or not possible – and the time of the check, and SHALL show editors and admins the number of recordings per outcome.

#### Scenario: No AcoustID key
- **WHEN** a recording has no ISRC and no AcoustID key is configured
- **THEN** the outcome is "not possible" with the reason that fingerprint lookups are not configured

#### Scenario: Original file missing
- **WHEN** the fingerprint is needed and the active original's file cannot be read
- **THEN** the outcome is "not possible" with the reason that the file is missing
- **AND** the job continues with the next recording

#### Scenario: Counts per outcome
- **WHEN** an admin opens the library settings after a run
- **THEN** the number of identified, unmatched, duplicate, not possible and unchecked recordings is shown

### Requirement: Identifiers only
Identification SHALL set only identifiers (MusicBrainz recording ID, AcoustID) and register the recording for the periodic refresh (see metadata-lookup). It SHALL NOT change titles, artists or other metadata; those are applied through tagging.

#### Scenario: Different title at MusicBrainz
- **WHEN** a recording titled "Eisfeld (Remaster)" is identified as a MusicBrainz recording titled "Eisfeld"
- **THEN** the recording keeps its title
- **AND** it has the MusicBrainz recording ID

### Requirement: Identified duplicates stay separate
When the identified MusicBrainz recording already belongs to another recording of the library, the system SHALL NOT assign the ID a second time and SHALL NOT merge the recordings automatically; the outcome SHALL be "duplicate" and name the other recording.

#### Scenario: Same recording imported twice
- **WHEN** two recordings of the library are identified as the same MusicBrainz recording
- **THEN** the first keeps the MusicBrainz ID
- **AND** the second has the outcome "duplicate" naming the first, and both stay separate

### Requirement: Stored fingerprints
The system SHALL compute the acoustic fingerprint of an audio file at most once and SHALL store it with the file, so that later runs and other features reuse it.

#### Scenario: Re-run after a month
- **WHEN** a recording whose fingerprint was computed in an earlier run is checked again
- **THEN** the stored fingerprint is used and the file is not decoded again
