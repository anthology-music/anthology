# Spec Delta

## MODIFIED Requirements

### Requirement: Single original per recording
The system SHALL keep exactly one active original audio file per recording and SHALL represent every additional album or compilation appearance as a reference (track context), not as a copy. Files that were replaced as original but must be kept (see "Superseded referenced originals") SHALL NOT count as active originals.

#### Scenario: Same recording on two albums
- **WHEN** a recording that already exists is added as part of a second album
- **THEN** no second audio file is stored
- **AND** a new track context links the second album to the existing recording

#### Scenario: One active original
- **WHEN** a recording has a superseded referenced file and a managed original
- **THEN** only the managed original is used for playback, transcoding and downloads

### Requirement: Context-dependent metadata
The system SHALL deliver album, track number, album artist and cover from the track context the recording is accessed through, for managed and referenced originals alike. Managed originals SHALL carry only neutral base tags (title, artist, recording ID, ISRC); the embedded tags of referenced originals SHALL be left untouched unless the user enabled tag writing for them (see "Managed and referenced originals").

#### Scenario: Playing from a compilation
- **WHEN** a client plays a recording via a compilation
- **THEN** the client receives the compilation's album title, track number and album artist
- **AND** the original file on disk is not modified

#### Scenario: Referenced original with its own album tag
- **WHEN** a referenced original whose embedded album tag is "Greatest Hits" is played via the studio album
- **THEN** the client receives the studio album's metadata from the database
- **AND** the embedded tags of the referenced file stay unchanged

### Requirement: Quality-based replacement
The system SHALL replace the active original of a recording with a new file of the same recording when the new file has a higher effective quality (see quality-analysis), and SHALL keep all references and track contexts unchanged. If the active original is referenced and the new file was acquired (downloaded or ripped), the new file SHALL become a managed original; a folder import keeps the storage mode the admin chose for it (see library-import).

#### Scenario: Better source arrives
- **WHEN** a recording stored as Opus 160 from YouTube is acquired again as FLAC 16/44.1 from Tidal
- **THEN** the FLAC file becomes the original
- **AND** cached transcodes of the old original are invalidated

#### Scenario: Better source for a referenced original
- **WHEN** a recording whose active original is a referenced MP3 is acquired as FLAC from Tidal
- **THEN** the FLAC file is stored as a managed original and becomes the active original
- **AND** the referenced MP3 is marked superseded and stays unchanged at its location

## ADDED Requirements

### Requirement: Managed and referenced originals
Every original SHALL have a storage mode: managed (stored in Anthology's storage; Anthology MAY write, move and replace it) or referenced (stored at a location outside Anthology's control; Anthology MUST NOT move, rename or delete it, and MUST NOT write it unless the user enabled tag writing for it).

#### Scenario: Referenced original is read-only
- **WHEN** an editor changes the title of a recording whose original is referenced
- **THEN** the change is stored in the database
- **AND** the referenced file is not written

#### Scenario: Tag writing enabled for a referenced original
- **WHEN** the user enabled tag writing for an imported folder and an editor changes the title of a recording from that folder
- **THEN** the referenced file receives the complete tags of the track context it was imported with

#### Scenario: Managed original receives base tags
- **WHEN** the title of a recording whose original is managed is changed
- **THEN** the neutral base tags of the managed file are updated

### Requirement: Superseded referenced originals
When a referenced original stops being the active original, the system SHALL mark it as superseded, SHALL keep its file unchanged at its location and SHALL list it in a report of superseded files with its path, size and the replacing original.

#### Scenario: Report of superseded files
- **WHEN** an admin opens the report of superseded files
- **THEN** each superseded referenced file is listed with path, size and the original that replaced it

#### Scenario: Superseded file is never deleted
- **WHEN** a referenced original is superseded
- **THEN** the system does not delete, move or modify the file, even if tag writing was enabled for it

### Requirement: Adopting referenced originals
The system SHALL let a user explicitly adopt referenced files into managed storage by moving, copying or reflinking them, SHALL ask for confirmation first and SHALL verify the checksum of the adopted file before removing or changing anything at the source location.

#### Scenario: Adopt by moving
- **WHEN** a user adopts a referenced folder with mode "move" and confirms
- **THEN** each file is copied into managed storage, its checksum is verified, and only then is the source file removed
- **AND** the originals become managed

#### Scenario: Hardlink is not an adoption
- **WHEN** a user wants to adopt a referenced file by hardlinking it
- **THEN** the system does not offer hardlinking for adoption because the file would still be shared with the foreign location

#### Scenario: Checksum mismatch
- **WHEN** the checksum of an adopted file does not match its source
- **THEN** the source file stays in place, the original stays referenced and the item is reported as failed
