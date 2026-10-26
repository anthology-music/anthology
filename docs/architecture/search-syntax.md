# Search syntax

Text syntax of the search (`openspec/specs/search/spec.md`). The server parses the text (`GET /api/v1/search/parse`) and the client shows the parsed filters as chips: removing a chip removes its token from the text, adding a chip appends a token, so syntax and chips are one query. The same text is a selection rule for bulk edits (`{ "list": "search", "q": … }`).

Searchable items: artists, albums (releases) and tracks. Works, videos, playlists and the fields that need them join the search with the changes that build those domains.

## Text

Free words are searched across all fields of artists, albums and tracks (title, artist, album, album artist, composers, genres, year):

- **Prefixes of words:** `Pola` finds "Polarnacht"; `eis` does not find "Treibeis".
- **Case, accents and umlauts are ignored:** `Mueller`, `Müller` and `MÜLLER` are the same word, `Dvorak` finds "Dvořák" (German umlauts are spelled out, other accents dropped).
- **Small typos** in words of three or more characters: a word that starts no word of the library is replaced by up to five similar words (`Symphny` finds "Symphony" and "Symphonie").
- **Phrases:** quoted text (`"Böhmischer Traum"`) matches its words in that order. A word with inner punctuation (`AC/DC`) is a phrase as well.

Ranking: whole-word matches first, then prefix matches, then matches through typo tolerance; within each, the library list order.

## Filters

`field:value`, `field:"value with spaces"`, `field:>value`, `field:<value`.

| Field | Applies to | Example |
|---|---|---|
| `type` | all (`artist`, `album` or `release`, `track` or `recording`) | `type:album` |
| `artist` | artists, albums, tracks (artist or album artist) | `artist:Mozart` |
| `album` | albums, tracks | `album:"Greatest Hits"` |
| `composer` | tracks | `composer:Dvořák` |
| `genre` | tracks | `genre:Blasmusik` |
| `year` | albums, tracks (`=`, `>`, `<`) | `year:>1990`, `year:<2000`, `year:1985` |
| `format` | tracks (`flac`, `wav`, `aiff`, `alac`, `mp3`, `aac`, `opus`, `vorbis`) | `format:flac` |
| `quality` | tracks (effective quality: `lossless`, `hires`, `cd`, `lossy` or a tier) | `quality:lossless` |

Text filters match prefixes of the words of their field (`artist:wien phil`). A filter restricts the results to the types it applies to (`format:flac Nordlicht` returns tracks only). Originals whose quality is not analysed yet have no effective quality and match no `quality` filter.

Filters are combined with AND; free words and filters can be mixed: `artist:Mozart year:>1990 quality:lossless requiem`.

Fields of later domains are recognised and reported as not available yet: `arranger`, `publisher`, `work`, `grade` (works), `source` (sources), `favorite` (personal data).

## Context

Searching inside an album returns its tracks; searching at an artist returns the artist's albums and tracks (as artist or album artist). The context is shown as a chip and can be removed. Playlist, folder and work contexts follow with their domains.

## Errors

Invalid tokens are reported per token and left out; the rest of the query still runs:

| Error | Example |
|---|---|
| `unknown_field` | `colour:red` |
| `unavailable_field` | `work:"Abba Medley"` |
| `missing_value` | `genre:` |
| `invalid_value` | `year:neunzehn`, `quality:best`, `type:song` |
| `invalid_operator` | `artist:>Mozart` (`>` and `<` only for `year`) |

## Offline

Offline search over the offline storage with the same syntax is part of the change `offline-sync`.
