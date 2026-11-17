## MODIFIED Requirements

### Requirement: Searchable items
The search SHALL cover the library's artists, releases and tracks and the works, and SHALL return results grouped by type with a count per type.

#### Scenario: Search finds an album and its tracks
- **WHEN** a user searches for "Polarnacht"
- **THEN** the album "Polarnacht" is shown under releases and its tracks under tracks

#### Scenario: Search finds a medley
- **WHEN** a user searches for "Nordlicht-Medley"
- **THEN** the medley is shown under works

### Requirement: Field filters
The search SHALL support field filters both as text syntax (e.g. `artist:Mozart year:>1990 quality:lossless`) and as filter chips in the UI; both SHALL produce the same query, a filter SHALL restrict the results to the types it applies to, and an invalid filter SHALL be reported without discarding the rest of the query. The filters `work` (tracks and works), `arranger` and `grade` (works) SHALL be available; `composer` SHALL apply to tracks and works.

#### Scenario: Syntax and chips agree
- **WHEN** a user types `genre:Blasmusik year:>2000`
- **THEN** the corresponding filter chips are shown and the results equal those of adding the chips manually

#### Scenario: Unknown field
- **WHEN** a user types `colour:red Mozart`
- **THEN** the search shows a hint for the unknown field and still searches for "Mozart"

#### Scenario: Filter for one type
- **WHEN** a user types `format:flac Nordlicht`
- **THEN** only tracks are returned

#### Scenario: Works of an arranger
- **WHEN** a user types `arranger:"de Haan" grade:3`
- **THEN** only works arranged by de Haan with grade 3 are returned

#### Scenario: Recordings of a work
- **WHEN** a user types `work:Nordlicht-Medley`
- **THEN** the medley is returned under works and the tracks of its linked recordings under tracks

### Requirement: Search in context
The search SHALL be restrictable to the current album, artist or work; in a work it SHALL return the tracks of the work's recordings.

#### Scenario: Search within an album
- **WHEN** a user searches inside an album
- **THEN** only tracks of that album are returned

#### Scenario: Search within a work
- **WHEN** a user searches for "Probe" on the page of a medley
- **THEN** only tracks of recordings linked to the medley are returned
