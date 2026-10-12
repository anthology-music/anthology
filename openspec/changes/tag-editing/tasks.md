# Tasks

## 1. Documentation and data model

- [x] 1.1 Add `tagging` to the domain table in AGENTS.md and the domain list in `openspec/config.yaml`; verify both list it
- [x] 1.2 Update the interface draft in `services/tagger/README.md` (read, write with `mode: atomic | in_place`, copy, health); verify the README lists all four endpoints and both write modes
- [x] 1.3 Update `docs/architecture/data-model.puml`: `FieldProvenance`, `ProvenanceSource`, `ChangeSet`, `AuditLog.changeSetId`, `ReviewType.TAG_CONFLICT`, `JobType.TAGGING_BULK`; verify the diagram renders without errors on the PlantUML server

## 2. Edit service (server)

- [ ] 2.1 Create `server/anthology/tagging/` with the edit service, field levels and provenance checks; verify with tests for manual edits, automatic updates of untouched fields and conflict creation for manual fields
- [ ] 2.2 Implement change sets with old/new values in the audit log and undo with skip report; verify with tests for undo, partial undo and undo of an undo
- [ ] 2.3 Implement bulk edits with count preview and a `TAGGING_BULK` job in keyset batches; verify with a test on 5,000 generated tracks that browsing queries stay within budget during the job

## 3. Propagation and tagger

- [ ] 3.1 Implement the persistent file write queue with coalescing, write modes per storage mode and resume after tagger outage; verify with tests using a fake tagger (down, up, managed, referenced with and without opt-in, superseded)
- [x] 3.2 ~~Implement `POST /v1/tags/write` modes in `services/tagger`~~ – moved to change `tagger-service` (task 2.4)
- [ ] 3.3 Invalidate transcodes and tagged copies of affected contexts and send deltas; verify with a test that a title edit discards the cache entries and a subscribed client receives a delta

## 4. Conflict list and client

- [ ] 4.1 Implement the `tagging.conflicts` subscription with grouping by field, album, artist and source and bulk decisions via the review bulk job; verify with protocol tests for grouping counts and a group accept
- [ ] 4.2 Create `client/src/features/tagging/` with single edit, bulk edit with count confirmation, history with undo, and the conflict list with multi-select and group actions; verify with component tests and an E2E test for bulk edit and undo

## Workflow follow-up

- Archive the change after review and verify `openspec validate --all --strict` passes.
