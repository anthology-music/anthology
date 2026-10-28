# tagging Specification

## Purpose
Let editors correct and complete metadata individually or in bulk, propagate changes to files and caches, protect manual corrections from silent automatic overwrites, allow undo, and define the interface to the tagger service.

## Requirements

### Requirement: Tagger service interface
The core SHALL read and write full tags only through the tagger service's versioned interface (read, write, copy, health) and SHALL batch requests; the tagger SHALL answer every file of a batch individually, so that one failing file does not fail the others, and SHALL report its interface version in its health response.

#### Scenario: Batch with a broken file
- **WHEN** the core asks the tagger to read 200 files and one of them is corrupt
- **THEN** the tagger returns tags for 199 files and an error code for the corrupt one

#### Scenario: Interface version
- **WHEN** the core queries the tagger's health
- **THEN** the response contains the service version and the interface version

### Requirement: Safe tag writes
The tagger SHALL write managed files atomically and referenced files in place so that hardlinks are preserved, and an interrupted write SHALL leave a file either unchanged or completely updated; the tagger MUST refuse an atomic write to a file with more than one hardlink.

#### Scenario: Hardlinked referenced file
- **WHEN** tags are written to a hardlinked referenced file with tag writing enabled
- **THEN** the file is modified in place and the hardlink to the user's folder still exists

#### Scenario: Interrupted write of a managed file
- **WHEN** the tagger is stopped during a write to a managed original
- **THEN** the original is either unchanged or completely updated, never partially written

#### Scenario: Interrupted in-place write
- **WHEN** the tagger is stopped during an in-place write and started again
- **THEN** the file is restored to its previous state and keeps its hardlinks

#### Scenario: Atomic write to a hardlinked file
- **WHEN** the core requests an atomic write to a file with two hardlinks
- **THEN** the tagger refuses the write and the file is unchanged

### Requirement: Tagger path restriction
The tagger SHALL only access files below its configured roots (the shared volumes) after resolving symbolic links, and SHALL write copies, extracted images and its journal only below the cache root.

#### Scenario: Path outside the volumes
- **WHEN** a request names `/etc/passwd` or a symbolic link pointing outside the roots
- **THEN** the tagger rejects that file with `forbidden_path` and does not open it

### Requirement: Embedded images by content hash
The tagger SHALL describe embedded images of a file (picture type, MIME type, size, dimensions, SHA-256) and, on request, SHALL store them in a staging directory named by content hash, so that the core can move them into its storage without the tagger knowing the storage backend.

#### Scenario: Same cover in twelve files
- **WHEN** the core reads twelve tracks of an album with image extraction, all embedding the same front cover
- **THEN** all twelve results name the same SHA-256 and the staging directory contains the image once

### Requirement: Read-only tagged copies
The tagger SHALL create tagged copies by reading the source read-only and writing complete tags and images into a new file below the cache root.

#### Scenario: Copy of a referenced original
- **WHEN** a tagged copy of a referenced original is created
- **THEN** the copy carries the requested tags and the original's checksum is unchanged

### Requirement: Tagger availability
The core SHALL check the tagger's health at startup and periodically, SHALL use the tagger only when it reports interface major version 1, SHALL keep running while the tagger is unavailable or incompatible, and SHALL use it again automatically once it is available.

#### Scenario: Start without tagger
- **WHEN** the server starts while the tagger is not running
- **THEN** the server starts and reports the tagger as unavailable

#### Scenario: Tagger comes back
- **WHEN** the tagger becomes reachable again
- **THEN** the core reports it as available within five seconds and uses it for new requests

#### Scenario: Incompatible tagger
- **WHEN** the tagger reports interface version 2.0
- **THEN** the core reports it as incompatible and sends it no tag requests

### Requirement: Tagged audio formats
The tagger SHALL read and write tags in every audio format the library accepts: FLAC, MP3, MP4 (AAC and ALAC), Ogg Vorbis, Opus, WAV and AIFF; WAV and AIFF carry their tags in an ID3 chunk.

#### Scenario: WAV original
- **WHEN** the core requests a tagged copy of a WAV original
- **THEN** the copy carries the requested tags in its ID3 chunk and the original's checksum is unchanged

### Requirement: Field levels
Metadata SHALL be stored on the level it belongs to: recording (title, artist, ISRC, MusicBrainz recording ID, composers, genres), release (album title, album artist, year, label; cover see covers) and track context (track number, disc number, context title and artist); an edit on a level SHALL apply in every context that uses it. Composers and genres MAY hold several values.

#### Scenario: Album title changed once
- **WHEN** an editor changes the title of an album with twelve tracks
- **THEN** all twelve tracks show the new album title in that album's context
- **AND** the same recordings in other albums keep their album titles

### Requirement: Moving tracks by album
Changing the album or album artist of selected tracks SHALL move them to the album with that title and album artist, creating it if none exists; renaming an album SHALL be an edit of the album itself.

#### Scenario: Tracks moved to another album
- **WHEN** an editor sets the album "Polarnacht (Deluxe)" for two tracks of "Polarnacht"
- **THEN** both tracks belong to "Polarnacht (Deluxe)" by the same album artist
- **AND** the other tracks of "Polarnacht" stay where they are

#### Scenario: Genre per recording
- **WHEN** an editor sets the genre "Marsch" for one track of an album
- **THEN** only that recording has the genre, in every album it appears on

### Requirement: Single and bulk edits
Editors and admins SHALL be able to edit fields of one item or of all items matching a selection rule; a bulk edit SHALL show the number of affected items before it is confirmed and SHALL run as a job with live progress.

#### Scenario: Genre for a folder
- **WHEN** an editor sets the genre "Blasmusik" for a folder rule covering 5,000 tracks
- **THEN** the number of affected items is shown for confirmation
- **AND** after confirmation a job applies the change and reports progress

#### Scenario: Listener cannot edit
- **WHEN** a listener tries to edit a field
- **THEN** the edit is rejected

### Requirement: Propagation of edits
After an edit the system SHALL update the base tags of affected managed originals, SHALL write the home-context tags of affected referenced files with tag writing enabled, SHALL invalidate transcodes and tagged copies of affected contexts, and SHALL send deltas to subscribed clients.

#### Scenario: Title edit on a managed original
- **WHEN** an editor changes the title of a recording with a managed original
- **THEN** the original's base tags contain the new title
- **AND** cached transcodes of the recording are discarded

### Requirement: File writes without the tagger
When the tagger service is unavailable, edits SHALL still be stored in the database and take effect for clients, and pending file writes SHALL be queued and executed when the tagger is available again.

#### Scenario: Tagger restarting
- **WHEN** an editor changes a title while the tagger is restarting
- **THEN** clients show the new title immediately
- **AND** the file is written once the tagger is back

### Requirement: Field provenance
The system SHALL record for every metadata field whether its value was set manually (with user and time) or by an automatic source (e.g. MusicBrainz, import, source service, publisher); a value without such a record SHALL count as imported.

#### Scenario: Manual edit recorded
- **WHEN** an editor changes the year of an album
- **THEN** the field is recorded as set manually by that editor at that time

#### Scenario: Value from an import
- **WHEN** a field has a value from a folder import and was never edited
- **THEN** it counts as imported and is protected from automatic updates

### Requirement: Automatic updates and tag conflicts
An automatic update SHALL apply directly to fields that were neither set manually nor imported from an existing collection; if it proposes a different value for such a protected field, it MUST NOT overwrite the field and SHALL create a tag conflict that shows the current value, the proposed value and the source.

#### Scenario: MusicBrainz refresh of an untouched field
- **WHEN** a MusicBrainz refresh changes the label of an album whose label was never edited manually
- **THEN** the new label is applied without confirmation

#### Scenario: MusicBrainz refresh of a corrected field
- **WHEN** a MusicBrainz refresh proposes a different title for a recording whose title was edited manually
- **THEN** the title stays unchanged
- **AND** a tag conflict with both values appears in the conflict list

#### Scenario: Imported tag differs from MusicBrainz
- **WHEN** an imported album title differs from MusicBrainz
- **THEN** the imported title is kept and a tag conflict appears in the conflict list

### Requirement: Conflict list
The system SHALL offer a dedicated list of open tag conflicts, separate from the review list, filterable and groupable by field, album, artist and source, where editors and admins can accept or reject conflicts individually, by multi-select or for a whole group (see review for decisions and bulk behavior).

#### Scenario: Accept all conflicts of one album
- **WHEN** an editor groups conflicts by album and accepts all conflicts of one album
- **THEN** the proposed values are applied to that album's fields and the fields are recorded as set by the accepting editor

#### Scenario: Reject by multi-select
- **WHEN** an editor selects three conflicts and rejects them
- **THEN** the manual values stay and the same proposals are not raised again

### Requirement: Undo
Editors and admins SHALL be able to undo a single or bulk edit from its history entry; the undo SHALL run as a job, SHALL restore the previous values, and SHALL skip and report fields that were changed again since.

#### Scenario: Undo a bulk edit
- **WHEN** an editor undoes the genre change on 5,000 tracks
- **THEN** a job restores the previous genres and reports progress

#### Scenario: Field changed again since
- **WHEN** an undo covers a field that another editor changed after the original edit
- **THEN** that field is left unchanged and listed in the undo report
