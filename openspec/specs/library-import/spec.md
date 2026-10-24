# library-import Specification

## Purpose
Import existing music collections (folders, iTunes/Apple Music, other music servers, beets) with duplicate detection and minimal resource usage.

## Requirements

### Requirement: Import sources
The system SHALL import from server/NAS folders, folders on a user's PC via the desktop client, iTunes/Apple Music library exports, other music servers where an API is available, beets libraries and playlist files (M3U, M3U8, PLS, XSPF).

#### Scenario: iTunes export
- **WHEN** a user imports an iTunes library export with its music folder
- **THEN** music, playlists, ratings and play counts are imported

### Requirement: Storage modes
The system SHALL offer the modes reference (files stay in place), move, link (hardlink or reflink) and copy, and SHALL default to the most economical mode possible. Move, copy and reflink SHALL yield managed originals; reference and hardlink SHALL yield referenced originals (see library), because a hardlinked file stays shared with the source folder.

#### Scenario: Same file system
- **WHEN** the source folder is on the same file system as the Anthology storage
- **THEN** the default mode is "link" and no additional space is used

#### Scenario: Hardlinked import stays read-only
- **WHEN** a folder is imported with mode "link" on a file system without reflink support
- **THEN** the files are hardlinked into Anthology's storage
- **AND** the resulting originals are referenced and their files are never written

#### Scenario: Reflinked import is managed
- **WHEN** a folder is imported with mode "link" on a file system with reflink support
- **THEN** the files are reflinked and the resulting originals are managed

#### Scenario: Mode shown in the dry-run report
- **WHEN** the dry-run report is shown
- **THEN** it states for the chosen mode whether the originals will be managed or referenced

### Requirement: Dry-run report
Before changing anything the system SHALL show a report with counts and storage impact for: new, already present, replaces lower quality, duplicate within source, needs review, broken, suspicious quality.

#### Scenario: Confirm after preview
- **WHEN** the scan finishes
- **THEN** nothing is moved, linked or copied until the user confirms the report

### Requirement: Staged duplicate detection
The system SHALL detect duplicates in stages from cheap to expensive: path/size/modification time, audio-data hash, existing identifiers (MusicBrainz, ISRC), acoustic fingerprint only for files still unmatched, and fuzzy matching as suggestion only.

#### Scenario: Same song in three folders
- **WHEN** the same recording exists three times in the source
- **THEN** it is imported once and the other occurrences become track contexts

### Requirement: Upload only what is missing
When importing from a PC the client SHALL send hashes first and SHALL upload only files the server does not have.

#### Scenario: Files already on server
- **WHEN** 80% of the PC collection already exists on the server
- **THEN** only the remaining 20% are uploaded

### Requirement: Resource-friendly execution
Imports SHALL run as throttled, resumable and incremental jobs; files SHALL be imported in their original format without transcoding.

#### Scenario: Repeat import
- **WHEN** an import of the same source is run again
- **THEN** only new or changed files are processed

### Requirement: Existing tags preserved
Existing tags SHALL be imported and not overwritten; differences to MusicBrainz SHALL become review candidates. Tags of referenced files MUST NOT be written unless the user allows it.

#### Scenario: Different album title in MusicBrainz
- **WHEN** an imported album title differs from MusicBrainz
- **THEN** the imported title is kept and a suggestion appears in the review list

### Requirement: Personal data ownership
Imported playlists, ratings and play counts SHALL belong to the user who started the import.

#### Scenario: Import by one user
- **WHEN** a user imports their playlists
- **THEN** the playlists belong to that user and the music is visible to all

### Requirement: Import roots
Server folders SHALL be importable only below the import roots configured for the installation, and only by admins. The system SHALL refuse paths outside the roots, including paths that leave a root through `..` or symbolic links.

#### Scenario: Folder below a root
- **WHEN** an admin chooses `/data/imports/Vinyl Rips` and `/data/imports` is an import root
- **THEN** the folder can be scanned

#### Scenario: Path outside the roots
- **WHEN** a request asks to import `/data/imports/../keys`
- **THEN** the request is refused and nothing is read

#### Scenario: Editor
- **WHEN** an editor tries to start a folder import
- **THEN** the request is refused

### Requirement: Default storage mode
The system SHALL determine for the chosen folder which modes are possible and SHALL propose the most economical one: reflink if supported, otherwise hardlink if the folder is on the same mounted file system as the library, otherwise copy. Reference SHALL always be possible.

#### Scenario: Separate volume
- **WHEN** the import folder is on a different mounted file system than the library
- **THEN** "link" is not offered and "copy" is proposed

### Requirement: Report confirmation
The report SHALL show for each category the number of files and their size, the storage the import adds in the chosen mode, and whether the originals will be managed or referenced. The import SHALL start only when an admin confirms that report; a new scan replaces an unconfirmed report.

#### Scenario: Storage impact of copying
- **WHEN** a folder with 40 GB of new files is scanned in mode "copy"
- **THEN** the report shows that the import adds 40 GB

#### Scenario: Cancel after the report
- **WHEN** the admin cancels after reading the report
- **THEN** no file is moved, linked or copied and the library is unchanged

### Requirement: Verified transfers
When an import moves files across file systems or copies them, the system SHALL verify the checksum of each written file before removing anything at the source. A file whose checksum does not match SHALL stay at the source and be reported as failed.

#### Scenario: Move across file systems
- **WHEN** a file is moved from the import volume into managed storage
- **THEN** it is copied, its checksum is verified, and only then is the source file removed

### Requirement: Library entries from tags
For each new file the system SHALL create artist, release, recording and track context from the file's tags. Without an album tag the folder name SHALL be the album; without a title tag the file name SHALL be the title; without an artist tag the artist SHALL be "Unknown artist". Files of the same album SHALL form one release.

#### Scenario: Album from tags
- **WHEN** twelve files tagged with the same album and album artist are imported
- **THEN** one release with twelve track contexts in disc and track order is created

#### Scenario: Untagged files
- **WHEN** a folder "Kassette 1985" contains untagged files
- **THEN** they form the release "Kassette 1985" by "Unknown artist" with their file names as titles

### Requirement: Identification after import
After an import the system SHALL start the identification of the newly created recordings (see library).

#### Scenario: New recordings
- **WHEN** an import has created 300 recordings
- **THEN** an identification job checks them without a separate user action

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
