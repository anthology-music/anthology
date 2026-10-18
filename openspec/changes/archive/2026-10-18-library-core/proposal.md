# Proposal

## Why

Milestone 2 (Core library) cannot start: no library tables exist, `server/anthology/library/` is an empty scaffold, and the open changes `managed-and-referenced-originals`, `metadata-lookup`, `review-list`, `tag-editing` and `search` all assume recordings, releases, tracks and audio files are already stored and browsable. The specs also do not say which library lists exist, how they are sorted or which counters they carry, although the Local view shows albums, artists and tracks with totals for 500,000 tracks.

## What Changes

- Store the library entities in the database: **artists**, release groups, releases, recordings, **track contexts** and audio files (the technical description of an original), following `docs/architecture/data-model.puml`.
- Introduce **artists** as entities with a name, a sort name and an optional MusicBrainz artist ID. Each recording references one artist, and each release references one album artist. The credited text as shown (e.g. "A feat. B") stays a separate display field. The album artist moves from the release group to the release.
- Provide five library lists over the sync protocol, each with maintained totals, keyset pagination, jumps by position and live deltas:
  - `library.artists`
  - `library.releases`
  - `library.artist.releases`
  - `library.release.tracks`
  - `library.tracks`
- Define a fixed sort order for each list on normalized sort keys that behave the same on PostgreSQL and SQLite.
- Maintain library counters (artists, releases, tracks, recordings) in the same transaction as every write. Counters are never computed by counting rows.
- Add a library write service for later domains (import, tagging, metadata lookup):
  - create recordings with their track context
  - update artists, releases, recordings and track contexts
  - record a change log entry for every row a change affects in a list, including derived values such as an artist name shown on 5,000 tracks
  - remove orphaned artists
- Publish the row schemas of the library lists with the sync message schema, so that client types are generated.
- Add a deterministic **test library generator** under `tools/` (fictional names, no media files) and a developer command to seed 500,000 tracks.
- Add performance tests for 500,000 tracks on PostgreSQL.
- Out of scope, each in its own change:
  - the client views (follow-up change `library-views`)
  - storage modes and superseded originals (`managed-and-referenced-originals`)
  - import (`library-import`)
  - editing through the API (`tag-editing`)
  - covers, quality analysis, sources and search
  - deleting library entries

## Capabilities

### New Capabilities

_None._

### Modified Capabilities

- `library`: new requirements for artists, the library lists with their sort orders, row contents and counters, deltas for derived values, and the test library at scale. The existing requirements stay unchanged; "Library scale" is backed by the new list requirements.

## Impact

- **Domains:** library. The sync-protocol mechanics are used unchanged. `jobs` and `users` are not affected. The open change `managed-and-referenced-originals` builds on the new `audio_file` table: its tasks add `storage_mode`, `original_status` and `tag_writes_allowed` and replace the unique original index with its partial index.
- **Data model:** new `Artist` class; `Recording.artist` becomes an artist reference plus `artistDisplay`; `ReleaseGroup.albumArtist` moves to `Release` as album artist reference plus `albumArtistDisplay`. `docs/architecture/data-model.puml` is updated. A new Alembic migration creates the library tables, indexes and counters (no existing data to migrate).
- **Non-functional requirements:** this change makes the 2 s / 500,000 tracks budget measurable for library lists. Every list is served from indexed keyset scans and maintained totals. Performance tests on PostgreSQL enforce the budget for opening each list and for jumping to the middle of the list.
- **API:** no new REST endpoints. New stream names and row schemas in the sync message schema; `packages/api-types` is regenerated.
- **Code:**
  - `server/anthology/library/` (models, schemas, service, streams)
  - a bulk helper for change log entries in `server/anthology/core/changes.py`
  - a CLI command `anthology dev seed-library`
  - `tools/library-generator/`
- **Dependencies:** none new at runtime. The generator is an MIT-licensed local package without third-party dependencies, used by the server as a development dependency.
