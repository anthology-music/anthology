# Spec Delta

## ADDED Requirements

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
