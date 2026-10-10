# Search syntax

Text syntax of the search (`openspec/specs/search/spec.md`). Every filter can also be set as a filter chip in the UI; syntax and chips produce the same query, which is also usable as a selection rule for bulk actions.

Status: draft – nothing built yet.

## Text

Free words are searched across all fields of all searchable items: prefix matching, case-insensitive, accents ignored, German umlaut spellings folded (`Mueller` = `Müller`), small typos tolerated from three characters on. Quoted text (`"Böhmischer Traum"`) matches the phrase.

## Filters

`field:value`, `field:"value with spaces"`, `field:>value`, `field:<value`.

| Field | Applies to | Example |
|---|---|---|
| `type` | all | `type:work`, `type:video` |
| `artist` | recordings, releases | `artist:Mozart` |
| `album` | recordings | `album:"Greatest Hits"` |
| `composer` | recordings, works | `composer:Dvořák` |
| `arranger` | works | `arranger:Smith` |
| `publisher` | works | `publisher:"Mitropa"` |
| `work` | recordings, videos | `work:"Abba Medley"` |
| `genre` | recordings, releases | `genre:Blasmusik` |
| `year` | releases, recordings | `year:>1990`, `year:<2000`, `year:1985` |
| `format` | recordings | `format:flac` |
| `quality` | recordings (effective quality) | `quality:lossless`, `quality:hires`, `quality:lossy` |
| `source` | recordings, videos | `source:cd`, `source:tidal` |
| `grade` | works | `grade:>3` |
| `favorite` | recordings, releases, artists, works (own favorites) | `favorite:true` |

Filters are combined with AND; free words and filters can be mixed: `artist:Mozart year:>1990 quality:lossless requiem`.

## Context

Searching inside an album, playlist, folder or work restricts the query to that context; the context is shown as a chip and can be removed.

## Errors

Unknown fields or invalid values are reported per token (e.g. "unknown field `colour`"); the rest of the query still runs.

## Offline

Without a server connection the same syntax searches the client's cached and offline items; results are marked as local only.
