## MODIFIED Requirements

### Requirement: Works
The system SHALL store works with title, type (original, arrangement, medley, adaptation), credits (composers, lyricists and arrangers as persons, in order), instrumentation, grade, duration, MusicBrainz work ID and ISWC where available. Editors and admins SHALL be able to create, edit and delete works; every signed-in user SHALL be able to see them. Deleting a work SHALL remove its credits, relations and recording links but SHALL NOT remove any recording.

#### Scenario: Create an arrangement
- **WHEN** an editor creates a wind-band arrangement of an existing song
- **THEN** a work of type "arrangement" is stored with its arranger

#### Scenario: Listeners only read
- **WHEN** a listener tries to change the title of a work
- **THEN** the change is refused and the work stays unchanged

#### Scenario: Delete a work
- **WHEN** an editor deletes a medley that has two linked concert recordings
- **THEN** the medley, its credits and relations are gone and both recordings stay in the library

### Requirement: Work relations
The system SHALL link works with the relation types "arrangement of", "medley contains" (with order) and "part of". Editors and admins SHALL be able to add, remove and reorder relations. The system SHALL refuse a relation that makes a work contain, arrange or be part of itself, directly or through other relations.

#### Scenario: Medley with four originals
- **WHEN** a medley contains four original works
- **THEN** the medley lists them in order

#### Scenario: Reorder the originals of a medley
- **WHEN** an editor moves the fourth original of a medley to the first place
- **THEN** the medley lists it first and keeps the order of the others

#### Scenario: Cycle refused
- **WHEN** an editor adds medley A to medley B while B is already contained in A
- **THEN** the relation is refused with a message and no relation is added

### Requirement: Navigation between works and recordings
The system SHALL show for a medley or arrangement its originals with play actions when they are in the library and an action to acquire them when they are not, and for every recording or original work the arrangements and medleys it appears in. The acquire action SHALL open the source search filled with the original's title and its first composer or performer and SHALL NOT order anything by itself. A recording SHALL show the works it is linked to.

#### Scenario: Contained in
- **WHEN** a user opens an original song
- **THEN** a section "Contained in" lists all medleys and arrangements that include it

#### Scenario: Original not in the library
- **WHEN** a user chooses "Acquire" for an original of a medley that the library does not have
- **THEN** the Streaming view opens with the source search filled with that original's title and artist, and no order is sent

#### Scenario: Works of a track
- **WHEN** a user opens the menu of a track whose recording is linked to a work
- **THEN** the menu offers that work and opens its page

### Requirement: Recordings of works
The system SHALL link recordings to works, including the band's own concert and rehearsal recordings; a recording MAY be linked to several works (for example a medley performance). Editors and admins SHALL be able to link and unlink recordings.

#### Scenario: Concert recording
- **WHEN** a concert CD track is linked to a medley work
- **THEN** it appears under "Recordings of this work"

#### Scenario: Recording of a medley in MusicBrainz
- **WHEN** MusicBrainz links a recording to three works as a medley performance
- **THEN** the recording is linked to all three works

## ADDED Requirements

### Requirement: Persons
Composers, lyricists and arrangers SHALL be persons with a name, a sort name and a MusicBrainz artist ID where known; there SHALL be at most one person per MusicBrainz artist ID. Editors and admins SHALL be able to rename persons and merge two persons into one; a merge of two persons with different MusicBrainz artist IDs SHALL be refused. A person's page SHALL list their works grouped by role. A person without any credit SHALL be removed.

#### Scenario: Two spellings merged
- **WHEN** an editor merges the person "J. de Haan" into the person "Jacob de Haan"
- **THEN** all works credited to "J. de Haan" are credited to "Jacob de Haan" and only one person remains

#### Scenario: Works of an arranger
- **WHEN** a user opens the page of an arranger
- **THEN** all works they arranged are listed under "Arranger", ordered by title

#### Scenario: Different MusicBrainz artists
- **WHEN** an editor tries to merge two persons that have different MusicBrainz artist IDs
- **THEN** the merge is refused and both persons stay

### Requirement: Works from MusicBrainz
For every recording with a MusicBrainz recording ID, the system SHALL fetch the linked MusicBrainz works with their ISWC and their composer, lyricist and arranger credits in a background job, and SHALL link them to the recording without review. The job SHALL run after recordings are identified, once for the existing library and with the periodic refresh. A refresh SHALL NOT overwrite work fields a person set and SHALL NOT restore a work, credit or recording link a person removed.

#### Scenario: Identified recording gets its work
- **WHEN** a recording is identified with a MusicBrainz recording ID that MusicBrainz links to a work with a composer and an ISWC
- **THEN** the work exists with that composer and ISWC and is linked to the recording, without an entry in the review list

#### Scenario: Edited title kept
- **WHEN** an editor changed the title of a work from MusicBrainz and the refresh finds a different title there
- **THEN** the work keeps the editor's title

#### Scenario: Removed link stays removed
- **WHEN** an editor unlinks a recording from a work that MusicBrainz links to it
- **THEN** later refreshes do not link it again

#### Scenario: Existing library
- **WHEN** the server starts for the first time with this feature and the library has identified recordings
- **THEN** a job fetches their works in the background and reports its progress

### Requirement: Works list
The system SHALL list all works ordered by title, filterable by type, with the number of works per type shown before the rows; the list SHALL load progressively and follow changes live, like the library lists.

#### Scenario: Counts first
- **WHEN** a user opens the works list of an installation with 20,000 works
- **THEN** the counts of all works, arrangements and medleys appear at once and the rows load while scrolling

#### Scenario: Filter by type
- **WHEN** a user chooses "Medleys"
- **THEN** only works of type medley are listed
