# Tasks

## 1. Documentation and data model

- [x] 1.1 Update `docs/architecture/data-model.puml`:
  - new class `Artist` (name, sortName, mbArtistId)
  - `Recording.artistDisplay` with relation `Recording "0..*" -- "1" Artist`
  - move the album artist from `ReleaseGroup` to `Release` (`albumArtistDisplay`, relation to `Artist`)

  Verify the diagram renders without errors on the PlantUML server.
- [x] 1.2 Describe the library streams, their sort keys, counters and the `*.moved` change entries in `docs/architecture/sync-protocol.md`, and the seed command in `server/AGENTS.md`; verify the documented command runs as written once group 6 is done

## 2. Schema

- [x] 2.1 Add the library models (`artist`, `release_group`, `release`, `recording`, `track`, `audio_file`, `library_counter`) with sort columns in collation `"C"` on PostgreSQL, and migration `0006` with all indexes and the four counter rows; verify the migration round trip and the model comparison test on SQLite and PostgreSQL
- [x] 2.2 Implement `sort_key()` normalization; verify with unit tests for case, diacritics, whitespace and that "oberli", "Öhler", "Otto" sort the same in Python, SQLite and PostgreSQL
- [x] 2.3 Add `record_changes()` (bulk change log entries, one `pg_notify`) to `core/changes.py`; verify with a test that all entries are numbered by the sequencer in one commit on both engines

## 3. Write service

- [x] 3.1 Implement `get_or_create_artist`, `create_release`, `add_recording` and `add_track`, maintaining sort keys, library counters, artist and release counts, change log and audit log entries; verify with tests that a second context of an existing recording adds a track but no recording and no audio file, and that counters match a recount
- [x] 3.2 Implement `update_artist`, `update_release`, `update_recording` and `update_track`, with set-based sort-key updates and per-row change entries for derived values; verify with tests that an artist rename writes entries for the artist, its releases and all tracks of its recordings, and that stored sort keys equal a recomputation
- [x] 3.3 Remove orphaned artists and write `release.moved` when a release changes its album artist; verify with tests for the last-reference case (artist removed, `delete` entry, counter decremented) and the moved entry

## 4. Streams

- [x] 4.1 Add the row schemas (`ArtistRow`, `ReleaseRow`, `TrackRow`) and the per-stream row schema registry in `anthology.sync.messages`, then regenerate `packages/api-types`; verify the generated `sync.ts` contains the library row types and the schema test passes
- [x] 4.2 Implement and register `library.artists`, `library.releases` and `library.tracks` with all four counters; verify with protocol tests for counts first, sort order, jumps by position and live deltas after an artist rename (including a row moving position)
- [x] 4.3 Implement and register `library.artist.releases` and `library.release.tracks` with parameter validation, totals from the maintained counts, no deltas for rows outside the filter, and `remove` for `*.moved`; verify with protocol tests including an unknown release (total 0) and a release moving to another album artist
- [x] 4.4 Implement the context rules of track rows (context title and artist, otherwise recording values; release album data; format of the original); verify with a protocol test for the compilation scenario of the spec

## 5. Test library generator

- [x] 5.1 Create `tools/library-generator/` (MIT `pyproject.toml`, `LICENSE` reference, package `anthology_library_generator`, no dependencies) with deterministic batch generation and the proportions of the design; verify with its own tests that the same size gives the same output and that the proportions are within tolerance for 50,000 tracks
- [x] 5.2 Add it as a server development dependency through a uv path source; verify that `uv sync` works and that `podman build -t anthology-server -f server/Containerfile .` succeeds with an image that does not contain the generator

## 6. Seeding and performance

- [x] 6.1 Add `anthology dev seed-library --tracks N [--reset]`: requires `ANTHOLOGY_DEV_DEMO=true`, refuses a non-empty library without `--reset`, uses `COPY` on PostgreSQL and batched inserts on SQLite, and sets all counters; verify with tests for refusal without the flag, refusal on a non-empty library, and counters matching a recount after seeding 1,000 tracks
- [ ] 6.2 Add `@pytest.mark.performance` tests on PostgreSQL with 500,000 generated tracks: for `library.artists`, `library.releases` and `library.tracks`, totals and first rows within 2 s, the window at the middle position within 2 s, and no `OFFSET` in the executed SQL; verify the tests pass locally and in the CI performance job

## 7. Verification

- [x] 7.1 Run the full server test suite on SQLite and PostgreSQL, ruff check and format, `pnpm api-types` (no diff afterwards), client lint/test/build and `openspec validate --strict`; verify all pass

## Workflow follow-up

- Archive the change after review and verify `openspec validate --all --strict` passes.
- Update `docs/agent-notes.md` (current state, next step: `library-views` or `managed-and-referenced-originals`).
