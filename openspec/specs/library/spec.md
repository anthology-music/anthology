# library Specification

## Purpose
Manage the shared music library so that every recording is stored exactly once, while albums, compilations and other contexts reference it and present context-specific metadata.

## Requirements

### Requirement: Single original per recording
The system SHALL store at most one original audio file per recording and SHALL represent every additional album or compilation appearance as a reference (track context), not as a copy.

#### Scenario: Same recording on two albums
- **WHEN** a recording that already exists is added as part of a second album
- **THEN** no second audio file is stored
- **AND** a new track context links the second album to the existing recording

### Requirement: Context-dependent metadata
The system SHALL deliver album, track number, album artist and cover from the track context the recording is accessed through, and SHALL keep only neutral base tags (title, artist, recording ID, ISRC) in the original file.

#### Scenario: Playing from a compilation
- **WHEN** a client plays a recording via a compilation
- **THEN** the client receives the compilation's album title, track number and album artist
- **AND** the original file on disk is not modified

### Requirement: Recording identification
The system SHALL identify recordings in this order: ISRC, acoustic fingerprint (AcoustID), and only as a suggestion a fuzzy match of artist, title and duration (±2 s). Fuzzy matches MUST NOT be merged automatically.

#### Scenario: Fuzzy match only
- **WHEN** a new file matches an existing recording only by artist, title and duration
- **THEN** the match is added to the review list as a suggestion
- **AND** the recordings stay separate until a user confirms

### Requirement: Quality-based replacement
The system SHALL replace an original with a new file of the same recording when the new file has a higher effective quality (see quality-analysis), and SHALL keep all references and track contexts unchanged.

#### Scenario: Better source arrives
- **WHEN** a recording stored as Opus 160 from YouTube is acquired again as FLAC 16/44.1 from Tidal
- **THEN** the FLAC file becomes the original
- **AND** cached transcodes of the old original are invalidated

### Requirement: Supported audio formats
The system SHALL support FLAC, WAV, AIFF, ALAC, MP3, AAC, Opus and Ogg Vorbis as originals. WAV and FLAC with equal sample rate and bit depth SHALL be treated as equal quality.

#### Scenario: WAV import
- **WHEN** a WAV file is added
- **THEN** it is identified, deduplicated and playable like any other format
- **AND** its metadata is taken from the database even if the WAV tags are incomplete

### Requirement: Change tracking
The system SHALL assign a monotonically increasing change sequence number to every change of shared library data.

#### Scenario: Tag edit
- **WHEN** an editor changes the title of a track context
- **THEN** a new change sequence number is recorded for that change
- **AND** connected clients receive the change as a delta (see sync-protocol)

### Requirement: Library scale
The system SHALL support libraries of at least 500,000 tracks while meeting the interaction budget of the sync-protocol spec.

#### Scenario: Large library browsing
- **WHEN** a client opens the track list of a library with 500,000 tracks
- **THEN** the total count and the first visible rows are interactive within 2 seconds

### Requirement: Artists
The system SHALL store artists as library entities with a name, a sort name and an optional MusicBrainz artist ID. Every recording SHALL reference exactly one artist and every release exactly one album artist. The credit as shown (e.g. "A feat. B") SHALL be kept as separate display text. An artist that no recording or release references any more SHALL be removed.

#### Scenario: Guest credit
- **WHEN** a recording is credited as "Mira Sand feat. Glas" with Mira Sand as its artist
- **THEN** the track shows "Mira Sand feat. Glas"
- **AND** the recording is counted for Mira Sand, not for Glas

#### Scenario: Last reference moves away
- **WHEN** the only recording of an artist is assigned to another artist
- **THEN** the first artist disappears from the artist list
- **AND** subscribed clients receive a removal delta for it

### Requirement: Library lists
The system SHALL offer every signed-in user the subscriptions `library.artists`, `library.releases`, `library.artist.releases` (parameter: artist ID), `library.release.tracks` (parameter: release ID) and `library.tracks`. Each SHALL support counts first, windowed chunks, jumps by position and deltas as defined by the sync-protocol spec.

#### Scenario: Browse from artist to tracks
- **WHEN** a user opens an artist and then one of the artist's releases
- **THEN** the client subscribes to `library.artist.releases` and then to `library.release.tracks`
- **AND** each list shows its total before its first rows

#### Scenario: Unknown release
- **WHEN** a client subscribes to `library.release.tracks` with an ID of a release that does not exist
- **THEN** the subscription reports a total of 0 and delivers no rows

### Requirement: List sort orders
The library lists SHALL have fixed sort orders:
- artists by sort name
- releases by album artist sort name, then title
- an artist's releases by title
- a release's tracks by disc number, then track number
- all tracks by artist sort name, title, then album title

Ties SHALL be broken by the entity ID, so that every position is stable.

#### Scenario: Equal titles
- **WHEN** two tracks have the same artist and title on the same album
- **THEN** they appear in the same order on every client and after every reload

### Requirement: Normalized sort keys
Sorting SHALL ignore case and diacritics and SHALL give the same order on PostgreSQL and SQLite. An artist's sort name SHALL default to the normalized name when no sort name is set.

#### Scenario: Umlauts and case
- **WHEN** the artists "Öhler", "oberli" and "Otto" are listed
- **THEN** they appear as "oberli", "Öhler", "Otto" on both database engines

### Requirement: Library counters
The library lists SHALL carry the counters `artists`, `releases`, `tracks` and `recordings`, taken from maintained counters that change in the same transaction as the data. `library.artist.releases` and `library.release.tracks` SHALL take their totals from maintained per-artist and per-release counts.

#### Scenario: Recording on a second album
- **WHEN** an existing recording is added as a track of a compilation
- **THEN** the counter `tracks` grows by one
- **AND** the counter `recordings` stays the same

### Requirement: Track rows by context
Track rows SHALL show the metadata of their track context:
- the context title and artist if set, otherwise the recording's title and artist credit
- album title and album artist of the release
- disc and track number
- duration
- format, sample rate, bit depth and bitrate of the original

#### Scenario: Context title on a compilation
- **WHEN** a recording titled "Polarnacht" appears on a compilation with the context title "Polarnacht (Radio Edit)"
- **THEN** the compilation's track row shows "Polarnacht (Radio Edit)"
- **AND** the recording's other track rows still show "Polarnacht"

### Requirement: Deltas for derived values
When a change alters a value that other list rows show or sort by, every affected row in subscribed lists SHALL receive a delta. Examples are an artist name shown on tracks and releases, or a release title shown on its tracks.

#### Scenario: Artist renamed
- **WHEN** an editor renames an artist that has 5,000 tracks while a client shows some of them in `library.tracks`
- **THEN** the visible rows update with the new name without reloading the list
- **AND** rows whose position changes because of the new sort name move to their new position

### Requirement: Test library generator
The project SHALL provide a deterministic generator for test libraries of a given size. It SHALL use fictional names only, without media files. The release and artist proportions SHALL resemble a real collection, including recordings that appear on several releases. A developer command SHALL seed a development database with it.

#### Scenario: Same seed, same library
- **WHEN** the generator is run twice with the same size
- **THEN** both runs produce the same artists, releases, recordings and tracks

#### Scenario: Seeding refused in production
- **WHEN** the seed command runs without developer mode enabled
- **THEN** it refuses to run and changes nothing

### Requirement: Library list budget
With a library of 500,000 tracks on PostgreSQL, each top-level library list SHALL show its totals and first rows, and SHALL deliver the window at any requested position, within the interaction budget of the sync-protocol spec. The top-level lists are artists, releases and tracks.

#### Scenario: Jump into the middle of all tracks
- **WHEN** a client subscribed to `library.tracks` of a 500,000-track library requests the window at position 250,000
- **THEN** the rows of that window arrive within 2 seconds
- **AND** no database query uses OFFSET

### Requirement: Library entries
The system SHALL offer every signed-in user the subscriptions `library.artist` (parameter: artist ID) and `library.release` (parameter: release ID). Each SHALL deliver the one row of that entry, with the same fields as the entry's row in `library.artists` or `library.releases`, or no row if the entry does not exist. Changes to the entry SHALL arrive as deltas; when the entry is removed, subscribed clients SHALL receive a removal delta.

#### Scenario: Open a release by link
- **WHEN** a client subscribes to `library.release` with the ID of an existing release
- **THEN** it receives a total of 1 and the release's row

#### Scenario: Entry renamed while open
- **WHEN** an artist is renamed while a client subscribes to `library.artist` for that artist
- **THEN** the client receives an upsert delta with the new name

#### Scenario: Unknown entry
- **WHEN** a client subscribes to `library.artist` with an ID of an artist that does not exist
- **THEN** the subscription reports a total of 0 and delivers no rows

### Requirement: Local library view
The Local view of the client SHALL let every signed-in user browse the library in the sections Albums, Artists and Tracks. Each section SHALL show its count from the library counters, kept live by deltas. Each section SHALL show its list with counts first, placeholder rows for rows not yet loaded and only the visible window loaded, as defined by the sync-protocol spec.

#### Scenario: Counts before rows
- **WHEN** a user opens the Local view of a library with 500,000 tracks
- **THEN** the counts of albums, artists and tracks are shown
- **AND** the first rows of the open section are interactive within 2 seconds

#### Scenario: Library changes while open
- **WHEN** another user adds a release while the album section is open
- **THEN** the album count and the list update without a reload

### Requirement: Artist page
Selecting an artist SHALL open the artist's page with the artist's name, release count, track count and the list of the artist's releases.

#### Scenario: Open an artist
- **WHEN** a user selects an artist in the artist section
- **THEN** the artist page shows the name, both counts and the artist's releases by title

### Requirement: Album page
Selecting a release SHALL open its album page with title, album artist, year, edition, disc count and track count, and the list of its tracks in disc and track order. The album artist SHALL link to the artist's page. Selecting a row of the track section SHALL open the album page of that track's release. When the release does not exist or is removed while open, the page SHALL say so and offer the way back to the library.

#### Scenario: Browse to an album
- **WHEN** a user selects an artist and then one of the artist's releases
- **THEN** the album page shows the release's header and its tracks in disc and track order

#### Scenario: Track section to album
- **WHEN** a user selects a row in the track section
- **THEN** the album page of that track's release opens

#### Scenario: Entry removed while open
- **WHEN** the release shown on an album page is removed
- **THEN** the page states that the release no longer exists and offers the way back to the library

### Requirement: Track rows
A track row on the album page SHALL show the disc and track number, title, the credited artist where it differs from the album artist, the file format and the duration.

#### Scenario: Guest credit on an album
- **WHEN** a track of a release by "Mira Sand" is credited "Mira Sand feat. Glas"
- **THEN** its row on the album page shows "Mira Sand feat. Glas"
- **AND** rows credited exactly "Mira Sand" show no artist

### Requirement: Library navigation
Every section, artist page and album page SHALL have its own address, so that links can be shared and a reload shows the same view. The artist and album pages SHALL show the path Library › artist › album. Returning to a section or artist page within the same session SHALL restore the list's previous scroll position.

#### Scenario: Reload an album page
- **WHEN** a user reloads the album page of a release
- **THEN** the same album page is shown with its header and tracks

#### Scenario: Back to the album list
- **WHEN** a user scrolls the album section to position 20,000, opens an album and goes back
- **THEN** the album section shows the rows around position 20,000 again

#### Scenario: Unknown address
- **WHEN** a user opens the address of an album page for a release that does not exist
- **THEN** the page states that the release does not exist and offers the way back to the library

### Requirement: Format label
Library rows SHALL show the file's format as technical information: the format name with bit depth and sample rate in kHz for lossless formats (e.g. `FLAC 24/96`, `WAV 16/44.1`) and with the bitrate in kbit/s for lossy formats (e.g. `MP3 320`). As long as the effective quality of a file is not known, the client SHALL NOT present the format as a quality rating.

#### Scenario: Lossy file
- **WHEN** a track's file is an MP3 with 320 kbit/s
- **THEN** its row shows `MP3 320`

#### Scenario: Effective quality not analysed
- **WHEN** a track's file has not been analysed for its effective quality
- **THEN** its row shows the format label and no quality badge

### Requirement: Orphaned files in managed storage
The maintenance SHALL find files in the managed storage that no library entry refers to, and temporary files of interrupted transfers. With the action "delete" it SHALL delete them, but only files older than the grace period, only inside the managed storage and only after checking again that no library entry refers to them. With "report only" it SHALL only list them.

#### Scenario: Orphan after an interrupted replacement
- **WHEN** the file of a deleted original was left in managed storage two days ago
- **THEN** the nightly maintenance with the action "delete" deletes it and lists it as deleted

#### Scenario: File of a running import
- **WHEN** an import wrote a file into managed storage one hour ago and the grace period is 24 hours
- **THEN** the maintenance does not touch it

#### Scenario: Report only
- **WHEN** the action is "report only" and a run finds an orphaned file
- **THEN** the file is listed and stays in place

#### Scenario: Referenced files
- **WHEN** a referenced original lies outside the managed storage
- **THEN** the maintenance never deletes or changes it

### Requirement: Maintenance safety limit
When a run would delete more files than the safety limit allows, the maintenance SHALL delete nothing and only list them; an admin SHALL be able to confirm the deletion of that run's files. The limit SHALL be the configured share of the managed files, but at least 10 files; when it is switched off, the maintenance SHALL delete without this check.

#### Scenario: Safety limit
- **WHEN** a library has 50,000 managed files, the safety limit is 1 % and a run would delete 5,000 files
- **THEN** it deletes nothing, lists the files and waits for an admin's confirmation

#### Scenario: Small library
- **WHEN** a library has 300 managed files, the safety limit is 1 % and a run finds 4 orphaned files
- **THEN** they are deleted, because the limit is at least 10 files

#### Scenario: Limit switched off
- **WHEN** the safety limit is off and a run finds 5,000 orphaned files
- **THEN** they are deleted

### Requirement: Missing originals
The maintenance SHALL report managed originals whose file does not exist, and SHALL NOT change or delete their library entries.

#### Scenario: File deleted outside Anthology
- **WHEN** the file of a managed original was deleted by hand
- **THEN** the next run lists it as missing and the recording stays in the library

### Requirement: Maintenance result
The system SHALL show admins the result of every maintenance run: when it ran, its status, and the numbers and sizes of deleted, listed and missing files, with the listed files browsable progressively.

#### Scenario: Result after a run
- **WHEN** an admin opens the system maintenance after a run
- **THEN** the run's time, status and counts are shown immediately and its files load progressively

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

### Requirement: Superseded managed originals
A managed original that stops being the active original and is not deleted right away SHALL be marked superseded and listed in the report of superseded files together with superseded referenced files, distinguishable by storage mode. Admins SHALL be able to delete all superseded managed files after a confirmation; each SHALL be deleted only after the checksum of the original that replaced it has been verified. Superseded referenced files SHALL never be deleted.

#### Scenario: Delete kept files later
- **WHEN** an admin confirms the deletion of superseded managed files in the report
- **THEN** each file whose replacement verifies is deleted and removed from the report
- **AND** superseded referenced files stay listed and unchanged

#### Scenario: Replacement does not verify
- **WHEN** the checksum of a replacing original does not match during the deletion
- **THEN** the superseded managed file is kept and the failure is reported
