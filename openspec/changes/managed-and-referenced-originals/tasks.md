# Tasks

## 1. Documentation and data model

- [x] 1.1 Amend ADR 0008 with the managed/referenced distinction, the hardlink rule, the superseded state and adoption; verify the ADR no longer states that every original lives under `_originals/`
- [x] 1.2 Update `docs/architecture/data-model.puml`: `StorageMode` with `MANAGED`/`REFERENCED` only, new `OriginalStatus` enum, `AudioFile.originalStatus`, relation `Recording "1" -- "0..*" AudioFile` with a note "at most one ACTIVE"; verify the diagram renders with PlantUML without errors

## 2. Library schema

- [ ] 2.1 Add `storage_mode` and `original_status` to the audio file model and the Alembic migration, including a partial unique index on `(recording_id) WHERE original_status = 'ACTIVE'`; verify with a test that inserting a second active original for a recording fails on PostgreSQL and SQLite
- [ ] 2.2 Add a library guard that refuses any move, rename or delete of a `REFERENCED` file and any write unless `tagWritesAllowed` is set (never for `SUPERSEDED`); verify with unit tests for each operation and both opt-in states
- [ ] 2.3 Write the home context's complete tags into referenced files with `tagWritesAllowed` after tag changes; verify with a test that the file's tags match the home context and the file is not moved

## 3. Replacement and superseding

- [ ] 3.1 Implement replacement of a referenced active original by a managed original that marks the old file `SUPERSEDED` and keeps all track contexts; verify with a test that the old file's bytes and mtime are unchanged and contexts still resolve
- [ ] 3.2 Exclude superseded files from playback, transcoding and download resolution; verify with a test that only the active original is resolved
- [ ] 3.3 Provide the superseded-files report as a keyset-paged subscription with count first; verify with a protocol test covering `snapshot_meta` and paging

## 4. Import storage modes

- [ ] 4.1 Map import modes to storage modes (move/copy/reflink → managed, reference/hardlink → referenced) and detect reflink support; verify with tests on a temporary file system for both cases
- [ ] 4.2 Show in the dry-run report whether the chosen mode yields managed or referenced originals; verify with a report test

## 5. Adoption

- [ ] 5.1 Implement the adoption job (move, copy, reflink; no hardlink) with confirmation, checksum verification before source removal and per-item failure reporting; verify with tests for success and checksum mismatch

## Workflow follow-up

- Archive the change after review and verify `openspec validate --all --strict` passes.
