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
The system SHALL offer the modes reference (files stay in place), move, link (hardlink or reflink) and copy, and SHALL default to the most economical mode possible.

#### Scenario: Same file system
- **WHEN** the source folder is on the same file system as the Anthology storage
- **THEN** the default mode is "link" and no additional space is used

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
