## ADDED Requirements

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
