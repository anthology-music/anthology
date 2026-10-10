# Spec Delta

## Purpose

Let users find recordings, releases, artists, works and videos quickly by text and field filters, online and offline, with results that load progressively and can be used as selection rules.

## ADDED Requirements

### Requirement: Searchable items
The search SHALL cover recordings, releases, artists, works (including composers, arrangers and publishers) and videos, and SHALL return results grouped by type.

#### Scenario: Search finds a medley and its recording
- **WHEN** a user searches for "Abba Medley"
- **THEN** results show the medley under works and its recordings under recordings

### Requirement: Search as you type
The search SHALL start while the user types, SHALL match word prefixes, SHALL tolerate small typos and SHALL ignore case, accents and umlaut spelling.

#### Scenario: Umlaut spelling
- **WHEN** a user types "Mueller"
- **THEN** items by "Müller" are found

#### Scenario: Accent and typo
- **WHEN** a user types "Dvorak Symphny"
- **THEN** recordings of Dvořák's symphonies are found

### Requirement: Search performance
The first search results SHALL appear within 300 milliseconds and the result view SHALL be interactive within 2 seconds (95th percentile) for a library of 500,000 tracks; the count per type SHALL be shown before the rows.

#### Scenario: Large library
- **WHEN** a user searches a library of 500,000 tracks for a common word
- **THEN** the counts per type and the first results appear within 300 milliseconds
- **AND** further results load progressively while scrolling

### Requirement: Field filters
The search SHALL support field filters both as text syntax (e.g. `artist:Mozart year:>1990 quality:lossless`) and as filter chips in the UI; both SHALL produce the same query, and an invalid filter SHALL be reported without discarding the rest of the query.

#### Scenario: Syntax and chips agree
- **WHEN** a user types `genre:Blasmusik year:>2000`
- **THEN** the corresponding filter chips are shown and the results equal those of selecting the chips manually

#### Scenario: Unknown field
- **WHEN** a user types `colour:red Mozart`
- **THEN** the search shows a hint for the unknown field and still searches for "Mozart"

### Requirement: Search in context
The search SHALL be restrictable to the current context (album, playlist, folder, work).

#### Scenario: Search within a playlist
- **WHEN** a user searches inside a playlist
- **THEN** only items of that playlist are returned

### Requirement: Results as selection rule
A search with its filters SHALL be usable as a selection rule for bulk actions (see sync-protocol).

#### Scenario: Tag all results
- **WHEN** an editor selects "all results" of a search and sets a genre
- **THEN** the bulk edit receives the search as rule and affects exactly the result set

### Requirement: Offline search
Without a server connection, the client SHALL search the items in its local cache and offline storage with the same syntax and SHALL mark the results as local only.

#### Scenario: Searching on a plane
- **WHEN** a user without connection searches for an artist whose albums are stored offline
- **THEN** the offline albums are found and marked as local results
