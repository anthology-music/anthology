# Design

## Context

PostgreSQL in production, SQLite for development, tests and very small installations (ADR 0010); performance budgets are measured on PostgreSQL. Progressive loading with subscriptions, counts first and selection rules (sync-protocol). The library has artists, releases, recordings and tracks (one recording per track, one artist per recording, one album artist per release, genres and composers per recording, release date per release, effective quality per original). Every library write calls `record_change`/`record_changes` in its transaction. Bulk edits accept `ids` or a list `rule` (`tagging/edits.py`). Works, videos, playlists and offline storage do not exist yet (see proposal for the scope).

## Goals / Non-Goals

**Goals:**
- Fast, tolerant search without an extra search server.
- One query model for text syntax, chips and selection rules.

**Non-Goals:**
- Semantic/similarity search ("sounds like").
- Searching inside sheet-music notes or lyrics.
- Works, videos, offline search (later changes, see proposal).

## Decisions

### Searchable items

Artists, releases and tracks. A track is the recording in its release, so a recording on two releases appears twice, each with its album; the client shows the group as "Titel"/"Tracks". This keeps album context for playback and matches the bulk edits, which work on tracks.

### Normalisation

One Python function folds text for documents and queries: German umlauts first (ä→ae, ö→oe, ü→ue, ß→ss, also upper case), then Unicode NFKD with combining marks removed, case-folded, every non-alphanumeric character becomes a word break. "Müller", "Mueller" and "MÜLLER" all become `mueller`; "Dvořák" becomes `dvorak`. Folding in Python makes both engines behave the same and needs no `unaccent` extension.

### Search documents

Table `search_documents` with one row per item: `item_type` (artist, release, track), `item_id`, `text` (normalised words of all searchable fields), the normalised filter columns `artist`, `album`, `composer`, `genre`, the raw filter columns `year`, `format`, `quality`, the context columns `release_id`, `artist_id`, `album_artist_id`, and `sort_key` (the library list order). Contents:

- artist: name and sort name;
- release: title, album artist, year;
- track: title, artist, album title, album artist, composers, genres, year, format and effective quality of the active original.

Table `search_terms(term)` holds the vocabulary (every word of every document) for typo tolerance; terms are added with documents and rebuilt by `search_reindex` (implemented: no pruning by the library maintenance; words that left the library only cost a useless typo candidate until the next rebuild).

**Maintenance:** `core/changes.py` gets a registry of change listeners; `record_change` and `record_changes` hand the changed entities to them in the same transaction. The search listener collects them in the session and maps them to the affected documents (an artist change rewrites the artist – the library already writes change entries for the releases and tracks that show a renamed artist –; a release change the release and its tracks; a recording, track or original change the tracks), which are rewritten just before the commit (SQLAlchemy's `before_commit` event), so a transaction that writes the same album many times rewrites its documents once. `search.index.flush` rewrites them earlier for searches inside the transaction. Commands (`anthology …`) install the listener as the server does. The generator (`seed_library`) writes the documents in bulk. A job `search_reindex` rebuilds all documents; it starts at server start when the stored index version (table `search_index_state`) differs from the code's, so the migration only creates tables and a changed normalisation reindexes by itself.

Alternative considered: querying domain tables directly. Rejected: joins across artists, releases, recordings and originals per keystroke cannot meet 300 ms at 500,000 tracks.

Alternative considered: an external search server (Meilisearch, OpenSearch). Rejected: extra container and synchronisation for a household-scale dataset that PostgreSQL handles.

### Matching and ranking

- **Words:** every free word matches a word of the document by prefix. PostgreSQL: GIN expression indexes on `to_tsvector('simple', text)`, one partial index per item type, and `to_tsquery('simple', 'word:*')`. Implemented this way instead of a stored `tsvector` column: the narrower rows and the per-type indexes halved the time of the first results at 500,000 tracks. SQLite: an FTS5 table over `text` with prefix indexes, kept in step by triggers. Quoted text matches the words in order (`<->` / FTS5 phrase). Typo replacements are resolved inside the query (scalar subqueries), so the list query needs no extra round trip; SQLite gets a `similarity` function equal to pg_trgm's (`anthology/db/trigrams.py`).
- **Typos:** a word of three or more characters that matches no vocabulary term by prefix is replaced by up to five vocabulary terms with trigram similarity ≥ 0.3 (pg_trgm's default) (PostgreSQL: `pg_trgm` GIN index on `search_terms.term`; SQLite: FTS5 trigram table over the terms, similarity computed in Python). "Symphny" finds "symphony" and "symphonie".
- **Ranking:** three buckets – every word matches a whole word (0, checked with `LIKE '% word %'` on the matched rows), prefixes (1), with typo replacements (2) – then `sort_key`, then `item_id`. Rows are keyset-paged on `(bucket, sort_key, item_id)`; a page reads the keys from the documents first and joins the library rows for that page only.
- **Counts per type:** counted with a cap (`LIMIT 10001`); above 10,000 the client shows "10,000+" and the list ends at 10,000 rows with a hint to refine the search. Rules for bulk edits are not capped.

### Query model and syntax

The server parses the text into tokens (words, phrases, filters `field op value`) and validates them; the result is the query `{text, filters, context}`. Unknown fields and invalid values become token errors, and the query runs without those tokens. `GET /api/v1/search/parse?q=` returns the tokens with errors, and the client renders them as chips: removing a chip removes its token from the text, adding a chip appends a token. Syntax and chips are therefore one query by construction. Fields now: `type`, `artist`, `album`, `composer`, `genre`, `year`, `format`, `quality` (operators `:`, `:>`, `:<`, quoted values); see `docs/architecture/search-syntax.md`. A filter restricts the result to the types it applies to (`format:flac` returns tracks only). Text filters match the words of their column by prefix; `year` compares numbers; `format` and `quality` compare values.

Alternative considered: a parser in the client as well (immediate chips, needed for offline search). Rejected for now: two parsers to keep equal; `offline-sync` adds the client parser with shared test cases.

### Search as a subscription

Implemented as one stream per type – `search.artists`, `search.releases`, `search.tracks` – instead of one stream `search` with a `type` parameter, so that each delivers the library's typed rows (`LibraryArtistRow`, `LibraryReleaseRow`, `LibraryTrackRow`) and the client reuses the library row components. Parameters `q` and an optional context (`release_id` or `artist_id`). `snapshot_meta` carries the capped count (`total`, counter `capped`) before the rows. Deltas: a change of an artist, release, track, recording or original re-evaluates the affected items against the query and sends an upsert or a remove (the server keeps no list, so items that were never listed may be removed too; every delta counts again, capped). Typing re-subscribes (debounced 150 ms); unsubscribing cancels the running query. Search subscriptions stay out of the client's local cache (`cache: false`), which would otherwise keep one entry per typed text.

The overview shows each type with its count and its first rows; "show all" opens the type's full list (virtual list). The search field sits at the top of the Local view's navigation; text, type and context live in the address (`/local/search?q=…&type=…&release_id=…`).

### Context

Album context: tracks of that release. Artist context: releases with that album artist, and tracks whose recording artist or album artist is that artist. The client offers the search in the album and artist views; the context appears as a removable chip.

### Results as selection rule

`EditRule` gets the list `search` with `q` and the optional context; it selects all matching tracks without the cap. Preview, values and the bulk edit job resolve it like the other lists. The client offers "edit all results" in the full track list of a search.

## Risks / Trade-offs

- [Common words match many documents; ranking sorts all matches] → buckets and keyset paging; the performance test covers a common word, a two-letter prefix, a typo and a filter without words.
- [Trigram fallback is slow for very short terms] → typo tolerance only from 3 characters.
- [German folding can create false matches in other languages] → folding only adds matches; whole-word matches rank first.
- [Document maintenance makes artist renames costlier] → the documents of an artist are rewritten in one statement per table; bulk edits already run as jobs.
- [Index out of date after an upgrade with a changed normalisation] → `search_reindex` runs at start; until it finishes, search shows what is indexed.
