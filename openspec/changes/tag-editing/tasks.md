# Tasks

Pull request 1: tasks 1–4. Pull request 2: task 5. The change is archived after both.

## 1. Documentation and data model

- [x] 1.1 Add `tagging` to the domain table in AGENTS.md and the domain list in `openspec/config.yaml`; verify both list it
- [x] 1.2 Update the interface draft in `services/tagger/README.md` (read, write with `mode: atomic | in_place`, copy, health); verify the README lists all four endpoints and both write modes
- [x] 1.3 Update `docs/architecture/data-model.puml`: `FieldProvenance`, `ProvenanceSource`, `ChangeSet`, `AuditLog.changeSetId`, `ReviewType.TAG_CONFLICT`, `JobType.TAGGING_BULK`; verify the diagram renders without errors on the PlantUML server
- [x] 1.4 Update the data model to this design: `Recording.genres`/`composers`, `Release.label`, `ChangeSet` fields, `TagWrite`, provenance without rows for imported values; verify the diagram renders

## 2. Edit service (server)

- [x] 2.1 Create the edit service in `server/anthology/tagging/` with field levels, validation, provenance records and migration `0015_tag_editing`; verify with tests for each level, a recording edit showing in every context, a release edit only in its own, the refused duplicate MusicBrainz ID and the recorded provenance
- [x] 2.2 Move selected tracks by album and album artist (`library.service.move_track`, release created or found, empty release removed); verify with tests for a move into an existing and a new album, the `track.moved` delta and consistent counters
- [x] 2.3 Implement change sets with old and new values in the audit log, the `tagging.changes` stream and undo as the `tagging_undo` job with skip report; verify with tests for undo, a skipped field changed since, undo of a track move and undo of an undo
- [x] 2.4 Implement `POST /api/v1/tagging/edits` with selection by IDs or list rule, count preview and the `tagging_bulk` job in keyset batches; verify that up to 50 items are applied directly, more run as a job with progress, listeners are refused, and with a performance test on 5,000 generated tracks that browsing stays within the budget during the job

## 3. Propagation and tagger

- [x] 3.1 Implement the persistent write queue with coalescing and the `TagWriter` (base tags of managed originals atomically, home-context tags of referenced files with opt-in in place, never superseded or without opt-in, resume after a tagger outage, retries with back-off, content hash updated); verify with tests using a fake tagger (down, up, managed, referenced with and without opt-in, superseded, two processes) (closes `managed-and-referenced-originals` 2.3)
- [x] 3.2 ~~Implement `POST /v1/tags/write` modes in `services/tagger`~~ – moved to change `tagger-service` (task 2.4)
- [ ] 3.3 (waits for `transcoding` and `context-tags-on-delivery`) Invalidate transcodes and tagged copies of affected contexts; verify with a test that a title edit discards the cache entries
- [x] 3.4 Deltas for edited rows in every list that shows them; verify with protocol tests that a recording edit reaches the track rows of all its contexts and a release edit its album row and track rows

## 4. Client

- [x] 4.1 Create `client/src/features/tagging/` with the edit mode (album page and track list: selection, select all, shift range, whole list by rule, sticky bar with count), the tag editor with mixed values and count confirmation, editing an album's own fields, and the change history with undo in the settings; texts de/en; verify with component tests
- [x] 4.2 E2E test: bulk edit of an album's tracks and undo from the history

## 5. Tag conflicts (pull request 2)

- [x] 5.1 Conflict branch of the edit service: automatic origins apply to unprotected fields and create `TAG_CONFLICT` entries for protected ones; migration for the type and the group columns; verify with tests for both cases and that a rejected proposal is not raised again
- [x] 5.2 `tagging.conflicts` stream with filters and group counts by field, release, artist and source; `review.items` without tag conflicts; decisions and group decisions through the review module; verify with protocol tests and a group accept recorded as set by the accepting editor
- [x] 5.3 MusicBrainz refresh job through the edit service (closes `metadata-lookup` 2.4), which also turns differences of imported tags into conflicts; verify with a faked MusicBrainz that unprotected fields update and protected fields create conflicts
- [x] 5.4 Client conflict list with grouping, multi-select and group actions, navigation entry with the open count; verify with component tests and an E2E test accepting a group

## 6. Documentation

- [x] 6.1 Update `docs/architecture/sync-protocol.md` (stream `tagging.changes`; `tagging.conflicts` with 5.2), `server/AGENTS.md` (edit service, write queue) and `docs/agent-notes.md`

## Workflow follow-up

- Archive the change after pull request 2 and verify `openspec validate --all --strict` passes.
