# sheet-music Specification

## Purpose
Store sheet music for works (conductor's scores and individual parts), interpret the notes, play them back and follow along on screen.

## Requirements

### Requirement: Sheets per work
The system SHALL store sheets per work with type (score or part), instrument, voice, transposition (C, B♭, E♭, F, other), clef, publication and the uploaded files (PDF, image, MusicXML, MEI).

#### Scenario: Upload a clarinet part
- **WHEN** an editor uploads a PDF and selects "Part", "Clarinet", "1st", "B♭"
- **THEN** the sheet is stored with these properties under the work

### Requirement: Display modes
The system SHALL display scores page by page and parts system by system (line by line); for keyboard, accordion, harp and organ parts one system SHALL comprise all braced staves.

#### Scenario: Conductor's score
- **WHEN** a score is played back
- **THEN** a whole page is visible and the page turns shortly before its end

#### Scenario: Accordion part
- **WHEN** an accordion part is played back
- **THEN** treble and bass staves of the current system are shown and advanced together

### Requirement: Playback with follow-along
The system SHALL play sheets at concert pitch using instrument sounds and SHALL highlight the current measure synchronised with playback.

#### Scenario: Transposing instrument
- **WHEN** a B♭ clarinet part is played
- **THEN** it sounds a major second lower than written

### Requirement: Preferred symbolic input
The system SHALL accept MusicXML directly and SHALL prefer it over recognition from images.

#### Scenario: MusicXML upload
- **WHEN** a MusicXML file is uploaded
- **THEN** no optical recognition is run

### Requirement: Optical music recognition with review
For PDFs and images the system SHALL run optical music recognition, store a confidence per measure, mark uncertain measures and release a sheet only after review.

#### Scenario: Uncertain measures
- **WHEN** recognition finishes with uncertain measures
- **THEN** the sheet is marked "needs review" and the uncertain measures are highlighted

### Requirement: Access control
Access to sheets SHALL be limited to signed-in users and configurable per sheet; the system SHALL offer no external sharing and SHALL log downloads.

#### Scenario: Musician sees own part
- **WHEN** a member with access to the 2nd trumpet part opens the work
- **THEN** only the parts they have access to are listed

### Requirement: Practice mode
The system SHALL allow playing all other parts of a score while muting or highlighting one selected part.

#### Scenario: Practice with the band
- **WHEN** a user mutes "1st Clarinet" in a score
- **THEN** all other parts play and the clarinet part follows along silently
