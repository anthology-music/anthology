# Design

## Context

- The sync infrastructure is complete and generic:
  - a stream implements `key_query`, `rows`, `meta` and `changes` (`anthology/sync/streams.py`)
  - the connection does windows, anchors, backpressure and resume
  - writes call `record_change()`, and the sequencer numbers entries after commit
- The jobs domain shows the pattern for maintained counters (`JobCounter`) and for streams with parameters (`job.items`).
- The library has no tables yet; migration head is `0005`. The only large list so far is the developer demo table (`demo_items`), which lives outside the migrations.
- `tools/` is empty; the server's `AGENTS.md` already announces the 500,000-track generator there.
- Artists are modeled as one artist per recording and one album artist per release, with the credited text kept as display text (decided with the maintainer; see proposal).

## Goals / Non-Goals

**Goals:**
- Library tables that the follow-up changes (originals, import, metadata lookup, tag editing, search) extend without restructuring.
- Five library streams that meet the budget at 500,000 tracks on PostgreSQL and behave the same on SQLite.
- One write path (the library service) that keeps sort keys, counters and change log entries consistent, so later domains cannot forget them.

**Non-Goals:**
- REST endpoints for editing; no deletion of recordings, tracks or audio files (deleting originals needs the verification rules of a later change).
- Alternative sort orders or filters for the lists. Filtering is the job of the `search` change.
- Multi-artist credits (several artists per recording). They can be added later as a credit table without changing the list contracts.

## Decisions

### 1. Tables

| Table | Main columns | Indexes |
|---|---|---|
| `artist` | `name`, `sort_name` (stored normalized), `mb_artist_id`?, `release_count`, `track_count` | `(sort_name, id)`, unique `mb_artist_id` |
| `release_group` | `title`, `type`, `mb_release_group_id`? | unique `mb_release_group_id` |
| `release` | `release_group_id`, `title`, `edition`?, `country`?, `release_date`?, `disc_count`, `album_artist_id`, `album_artist_display`, `track_count`, `sort_title`, `sort_album_artist`, `mb_release_id`? | `(sort_album_artist, sort_title, id)`, `(album_artist_id, sort_title, id)`, unique `mb_release_id` |
| `recording` | `title`, `artist_id`, `artist_display`, `duration_ms`, `isrc`?, `mb_recording_id`?, `acoust_id`? | `artist_id`, `isrc`, unique `mb_recording_id` |
| `track` | `release_id`, `recording_id`, `disc_number`, `track_number`, `context_title`?, `context_artist`?, `sort_artist`, `sort_title`, `sort_album` | `(sort_artist, sort_title, sort_album, id)`, `(release_id, disc_number, track_number, id)`, `recording_id` |
| `audio_file` | `recording_id`, `path`, `format`, `codec`, `bitrate_kbps`?, `sample_rate_hz`, `bit_depth`?, `channels`, `size_bytes`, `audio_hash`, `declared_quality`, `effective_quality`?, `home_track_id`?, `added_at` | unique `recording_id`, unique `path`, `audio_hash` |
| `library_counter` | `name` (PK), `value` | – |

- IDs are UUIDs, like in the other domains.
- Enums use the portable `str_enum` columns:
  - `AudioFormat`, `QualityTier` and `ReleaseGroupType` as in the data model
  - `effective_quality` stays empty until quality analysis exists
- The unique index on `audio_file.recording_id` enforces today's "at most one original per recording". The `managed-and-referenced-originals` change replaces it with its partial index on active originals and adds `storage_mode`, `original_status` and `tag_writes_allowed`.
- `FileLocation`, `Image`, `QualityAnalysis`, `TranscodeCacheEntry` and the link to `Source` are left out. Each belongs to the change that gives it behavior.
- Alternative: create every library class of the data model now. Rejected, because tables without behavior would be specified nowhere and would have to be redesigned by the changes that own them.

### 2. Denormalized sort keys on the listed row

Each list is served from a single index on the table it lists:
- `track` carries the normalized artist, title and album of its context
- `release` carries the normalized title and album artist

So a window is one index range scan plus primary-key joins for the 200 rows of a chunk. This holds both for the keyset scans and for the database-side anchor computation (`scan_anchors`).

- Alternative: sort by joined columns (recording title, artist name). Rejected: a keyset condition across joined tables cannot use one index, and anchors would need full joins over 500,000 rows.
- Cost: renaming an artist or a release rewrites the sort columns of all affected tracks. The service does this with set-based `UPDATE … WHERE id IN (subquery)` statements, not row by row.

### 3. Normalization and collation

- `sort_key(text)` in `library/service.py`:
  1. Unicode NFKD decomposition
  2. remove combining marks
  3. `casefold()`
  4. collapse whitespace and trim
- No article stripping and no natural number order: both are language-dependent and belong to editable sort names in `tag-editing`.
- Sort columns use collation `"C"` on PostgreSQL (`String().with_variant(String(collation="C"), "postgresql")`). PostgreSQL then compares bytes exactly like SQLite's default `BINARY` collation. Because UTF-8 byte order equals code point order, it also matches Python string comparison. The anchor invalidation in `anthology/sync/anchors.py` compares keys in Python, so all three must agree.
- Alternative: rely on the database's default collation. Rejected, because locale collations differ between engines and installations, which breaks the spec's "same order on both engines" and corrupts anchors.

### 4. Maintained counters

- `library_counter` holds `artists`, `releases`, `tracks` and `recordings`.
- `artist.release_count`, `artist.track_count` and `release.track_count` are maintained columns.
- The service adjusts all of them in the same transaction as the insert, update or removal (`UPDATE … SET value = value + :n`). The single counter rows serialize concurrent writers on PostgreSQL. That is acceptable at import speeds; jobs already use the same pattern.
- The three top-level streams return all four library counters in `meta`. A client therefore gets the sidebar totals from whichever list it opened.
- The filtered streams take `total` from the parent's count column and carry no counters.

### 5. Streams and change mapping

| Stream | Params | Key | Entity types |
|---|---|---|---|
| `library.artists` | – | `(sort_name, id)` | `artist` |
| `library.releases` | – | `(sort_album_artist, sort_title, id)` | `release` |
| `library.artist.releases` | `artist_id` | `(sort_title, id)` within `album_artist_id` | `release`, `release.moved` |
| `library.release.tracks` | `release_id` | `(disc_number, track_number, id)` within `release_id` | `track`, `track.moved` |
| `library.tracks` | – | `(sort_artist, sort_title, sort_album, id)` | `track` |

- `changes()` reloads the row by ID:
  - row gone: `remove`
  - row present: `upsert`, with its new key
- Filtered streams return nothing for a row outside their filter, so a tag edit on 5,000 tracks does not send 5,000 removals to every client that shows some other release.
- When a row leaves a filtered list (in this change: a release gets another album artist), the service also writes a change entry of type `release.moved`. The filtered stream answers that entry with `remove` when the row is not in its filter, and with `upsert` when it is.
- `track.moved` is defined for symmetry. It is first written by the tag-editing change, which moves tracks between releases.

**Fan-out of derived values (spec "Deltas for derived values"):** the service writes one `track` or `release` change entry for every row whose displayed or sorting value changed. Examples:
- an artist rename writes entries for the artist, its releases as album artist, and the tracks of its recordings
- a release title change writes entries for its tracks

Entries are written with a new bulk helper `record_changes(session, entity_type, ids, operation, scope)` in `core/changes.py`: one multi-row insert and one `pg_notify`.

- Alternative: one coarse "artist changed" event that each stream turns into a query for affected rows. Rejected: every stream would need reverse lookups, resume after a disconnect would have to replay those lookups, and the existing per-row delta contract would be bypassed.
- A very large fan-out (e.g. renaming "Various Artists") produces many deltas. The connection's existing queue limit already turns this into `resync` for clients that cannot keep up.

### 6. Row schemas

- Row payloads are pydantic models in `library/schemas.py`:
  - `ArtistRow`: name, counts
  - `ReleaseRow`: title, album artist, year, disc and track count
  - `TrackRow`: as listed in the spec, plus `recording_id` and `release_id`
- `anthology.sync.messages` gets a small registry of row schemas per stream. The published JSON Schema adds them under `rows`, so `packages/api-types` generates `LibraryTrackRow` and the others for the client follow-up change.
- The existing streams keep untyped rows until they are touched.

### 7. Write service

`library/service.py` is the only writer:

| Function | Purpose |
|---|---|
| `get_or_create_artist(name, sort_name=None, mb_artist_id=None)` | find or create an artist |
| `create_release(...)` | creates the release group if needed |
| `add_recording(...)` | recording, its home track and audio file |
| `add_track(release, recording, …)` | a further context for an existing recording |
| `update_artist`, `update_release`, `update_recording`, `update_track` | changes, with field dictionaries |

- Every function adjusts sort keys and counters, writes the change entries of section 5, and writes `audit_log` entries for the directly changed entity (not for the derived rows).
- Orphaned artists are removed at the end of `update_recording` and `update_release`, with a `delete` change entry.
- Callers pass the acting user (or `None` for system jobs) for the audit log.

### 8. Test library generator

- `tools/library-generator/` is a small MIT-licensed Python package (`anthology_library_generator`) without dependencies.
- `generate(tracks: int, seed: int = 1979)` yields batches per release:
  - artists, release groups, releases, recordings, tracks and audio-file descriptions
  - fictional names built from word lists, in the style of the demo stream
- Proportions for 500,000 tracks:
  - about 38,000 releases and 21,000 artists
  - artist sizes follow a Zipf-like distribution, so some artists have thousands of tracks
  - about 5 % compilation tracks by "Various Artists" that reuse existing recordings
  - about 5 % of release groups with a second edition
  - format mix: FLAC 16/44.1, FLAC 24/96, MP3, AAC, Opus, WAV
- The server lists it as a development dependency through a uv path source (`[tool.uv.sources]`). Production images (`--no-dev`) do not contain it.
- `anthology dev seed-library --tracks N [--reset]` requires `ANTHOLOGY_DEV_DEMO=true`:
  - refuses a non-empty library unless `--reset` is given
  - loads with `COPY` on PostgreSQL and batched inserts on SQLite
  - sets all counters
  - writes no change log entries, because seeding is an offline developer action; connected clients reconnect after it

Alternative: write the generator inside the server package. Rejected: `AGENTS.md` places test-data generation in `tools/`, and the generator must not ship in production images.

### 9. Progressive loading through all layers

- **DB:** every list has one covering-order index; windows are keyset scans from cached anchors; totals come from maintained counters. No query uses `OFFSET` or `COUNT(*)`.
- **Server:** the existing chunk pump streams 200-row chunks for the requested window first. Rows are built per chunk with primary-key joins; nothing loads a full list.
- **Protocol:** counts first in `snapshot_meta`, then chunks, then per-row deltas. Resume replays change entries within retention.
- **Client:** not part of this change. The follow-up `library-views` uses the existing virtual list and the generated row types.

### 10. Dependencies

None at runtime. `anthology-library-generator` (this repository, MIT) is a development dependency. No GPL/AGPL dependencies.

## Risks / Trade-offs

- [The sort-key columns duplicate data, and a bug in the service could leave them stale] → One service owns all writes. Tests assert that sort keys match a recomputation after every update kind.
- [The counter rows are a hot spot when several import jobs write at once] → Increments are single-row updates at the end of each item transaction; if contention shows up, batch increments per job item.
- [A large artist rename writes tens of thousands of change entries and deltas] → Set-based writes, a bulk insert of change entries, and the existing queue limit with `resync` for lagging clients. Renames of huge artists are rare editor actions.
- [Collation `"C"` sorts non-Latin scripts by code point instead of by language rules] → Acceptable for the first lists: normalization handles case and diacritics. Language-aware sort names come with `tag-editing`.
- [The uv path dependency could break the container build] → A task verifies `podman build -f server/Containerfile .` and that the image does not contain the generator.
- [Generated audio-file rows point to files that do not exist] → They are created only by the developer seed command, and never in installations without `ANTHOLOGY_DEV_DEMO`.

## Migration Plan

- Alembic revision `0006` creates the library tables, indexes and the four counter rows (value 0); downgrade drops them. There is no existing library data.
- Rollback: downgrade to `0005`. The library streams are registered only with their tables present, through the normal app startup after migration.
