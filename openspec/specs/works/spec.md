# works Specification

## Purpose
Model musical works independent of recordings, and link arrangements and medleys (e.g. for wind bands) logically to their original works.

## Requirements

### Requirement: Works
The system SHALL store works with title, type (original, arrangement, medley, adaptation), composers, arrangers, instrumentation, grade, duration, MusicBrainz work ID and ISWC where available.

#### Scenario: Create an arrangement
- **WHEN** an editor creates a wind-band arrangement of an existing song
- **THEN** a work of type "arrangement" is stored with its arranger

### Requirement: Work relations
The system SHALL link works with the relation types "arrangement of", "medley contains" (with order) and "part of".

#### Scenario: Medley with four originals
- **WHEN** a medley contains four original works
- **THEN** the medley lists them in order

### Requirement: Navigation between works and recordings
The system SHALL show for a medley or arrangement its originals with play actions when they are in the library, and for every recording or original work the arrangements and medleys it appears in.

#### Scenario: Contained in
- **WHEN** a user opens an original song
- **THEN** a section "Contained in" lists all medleys and arrangements that include it

### Requirement: Recordings of works
The system SHALL link recordings to works, including the band's own concert and rehearsal recordings.

#### Scenario: Concert recording
- **WHEN** a concert CD track is linked to a medley work
- **THEN** it appears under "Recordings of this work"

### Requirement: External registers
The system SHALL resolve original works against MusicBrainz works and ISWC and SHALL keep its own identifiers for works that are not registered there.

#### Scenario: Arrangement not in MusicBrainz
- **WHEN** an arrangement does not exist in MusicBrainz
- **THEN** it is stored with an internal ID and its originals still link to their MusicBrainz works

### Requirement: Review list
Automatically found assignments SHALL be stored as candidates with origin, confidence and evidence; only candidates confirmed by a hard identifier (ISMN, ISWC) MAY be accepted automatically.

#### Scenario: Medium-confidence candidate
- **WHEN** a candidate has medium confidence
- **THEN** it waits in the review list until a user accepts or rejects it
