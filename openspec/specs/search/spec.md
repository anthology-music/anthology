# search Specification

## Purpose
Let users find artists, releases and tracks quickly by text and field filters, with results that load progressively and can be used as selection rules.

## Requirements

### Requirement: Searchable items
The search SHALL cover the library's artists, releases and tracks, and SHALL return results grouped by type with a count per type.

#### Scenario: Search finds an album and its tracks
- **WHEN** a user searches for "Polarnacht"
- **THEN** the album "Polarnacht" is shown under releases and its tracks under tracks

### Requirement: Search as you type
The search SHALL start while the user types, SHALL match word prefixes, SHALL tolerate small typos in words of three or more characters and SHALL ignore case, accents and umlaut spelling.

#### Scenario: Umlaut spelling
- **WHEN** a user types "Mueller"
- **THEN** items by "Müller" are found

#### Scenario: Accent and typo
- **WHEN** a user types "Dvorak Symphny"
- **THEN** tracks of Dvořák's symphonies are found

#### Scenario: Prefix
- **WHEN** a user types "Pola"
- **THEN** the album "Polarnacht" is found

### Requirement: Search ranking
Results whose words match whole words SHALL come before prefix matches, and prefix matches before matches found through typo tolerance; within the same rank results SHALL follow the library list order.

#### Scenario: Whole word first
- **WHEN** a user searches for "Nord" and there are albums "Nord" and "Nordlicht"
- **THEN** "Nord" is listed before "Nordlicht"

### Requirement: Search performance
The first search results SHALL appear within 300 milliseconds and the result view SHALL be interactive within 2 seconds (95th percentile) for a library of 500,000 tracks; the count per type SHALL be shown before the rows. Counts above 10,000 MAY be shown as "10,000+", with the list limited to the first 10,000 results.

#### Scenario: Large library
- **WHEN** a user searches a library of 500,000 tracks for a common word
- **THEN** the counts per type and the first results appear within 300 milliseconds
- **AND** further results load progressively while scrolling

#### Scenario: Many matches
- **WHEN** a search matches 50,000 tracks
- **THEN** the track count is shown as "10,000+" with a hint to refine the search

### Requirement: Field filters
The search SHALL support field filters both as text syntax (e.g. `artist:Mozart year:>1990 quality:lossless`) and as filter chips in the UI; both SHALL produce the same query, a filter SHALL restrict the results to the types it applies to, and an invalid filter SHALL be reported without discarding the rest of the query.

#### Scenario: Syntax and chips agree
- **WHEN** a user types `genre:Blasmusik year:>2000`
- **THEN** the corresponding filter chips are shown and the results equal those of adding the chips manually

#### Scenario: Unknown field
- **WHEN** a user types `colour:red Mozart`
- **THEN** the search shows a hint for the unknown field and still searches for "Mozart"

#### Scenario: Filter for one type
- **WHEN** a user types `format:flac Nordlicht`
- **THEN** only tracks are returned

### Requirement: Search in context
The search SHALL be restrictable to the current album or artist.

#### Scenario: Search within an album
- **WHEN** a user searches inside an album
- **THEN** only tracks of that album are returned

### Requirement: Live results
Results of an open search SHALL follow library changes: an item that starts or stops matching after an edit SHALL appear in or disappear from the results without a new search.

#### Scenario: Renamed track
- **WHEN** an editor renames a track so that it no longer matches an open search
- **THEN** the track disappears from that search's results

### Requirement: Results as selection rule
A search with its filters and context SHALL be usable as a selection rule for bulk edits (see sync-protocol), without the limit of the result list.

#### Scenario: Tag all results
- **WHEN** an editor selects "all results" of a search and sets a genre
- **THEN** the bulk edit receives the search as rule and affects exactly the matching tracks
