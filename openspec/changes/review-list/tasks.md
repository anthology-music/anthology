# Tasks

## 1. Documentation and data model

- [x] 1.1 Add `review` to the domain table in AGENTS.md and the domain list in `openspec/config.yaml`; verify both list `review` with server module `review`
- [x] 1.2 Update `docs/architecture/data-model.puml`: new package "Review" with `ReviewItem`, `ReviewType`, `ReviewOrigin`; `ReviewStatus` with `DEFERRED` and `OBSOLETE` (`AUTO_ACCEPTED` kept for sheets); `JobType.REVIEW_BULK`; replace `WorkCandidate`; verify the diagram renders without errors on the PlantUML server and contains no `WorkCandidate`
- [x] 1.3 Update the data model to this design: `ReviewCounter`, `summaryJson`, `note`, `decidedBy`; types `MUSICBRAINZ_SUGGESTION`, `IMPORT_TITLE`, `IMPORT_REPLACEMENT` (`TAG_CONFLICT` removed, tag conflicts belong to tagging); the decision of `QualityAnalysis`; `IdentificationStatus.CONFIRMED`; verify the diagram renders

## 2. Review module (server)

- [x] 2.1 Create `server/anthology/review/` with models, migration `0014_review`, partial unique index on `suppression_key`, maintained counters and the producer API (`propose` in batches); verify with tests that duplicates and rejected suggestions are not re-created and counters follow inserts and decisions on SQLite and PostgreSQL
- [x] 2.2 Implement handler registration and accept/reject/defer/reopen with `still_applies`, `obsolete` with reason and `subject_changed`; verify with tests for each decision, a stale proposal, a missing handler and the recorded user and time
- [x] 2.3 Implement the `review.items` subscription with counts first, filters and keyset paging; verify with protocol tests (snapshot, paging, delta when a decision changes the status) and a performance test with 20,000 entries meeting the 2-second budget
- [x] 2.4 Implement `POST /api/v1/review/decisions` with `ids` or `rule` and the `review_decision` job; verify that a single entry is decided directly, a selection and a rule run as a job with progress, entries created after the start are not included and each entry records the decision
- [x] 2.5 Restrict list, decisions and spectrograms to editors and admins; verify with API and stream tests for all three roles

## 3. Producers

- [x] 3.1 `RECORDING_MATCH`: entries for name matches of an import (medium without fingerprint comparison, low with differing fingerprints and their similarity as evidence) and for identification duplicates; `library.merge_recordings` (tracks moved, better original active, the other superseded, identifiers kept, audited); verify both confidences, that nothing merges before the decision, a merge keeps every track context and the superseded file stays on disk
- [x] 3.2 `MUSICBRAINZ_SUGGESTION`: MusicBrainz recording search in metadata-lookup (cached, background priority, rate-limited), suggestion after `no_match`, `IdentificationStatus.CONFIRMED`; verify with a faked MusicBrainz that accepting assigns the ID, an ID owned by another recording yields a `RECORDING_MATCH` entry and nothing is merged automatically (closes `recording-identification` 5.1)
- [x] 3.3 `IMPORT_TITLE` for `needs_review` items: confirm, or separate into a recording of its own in the import's mode; verify both decisions and `source_changed` when the source file changed (closes `library-import-folders` 7.2)
- [x] 3.4 `IMPORT_REPLACEMENT` for `suspicious_quality` items: accepting replaces the original with checksum verification; verify accept, reject and a stale entry after another replacement (closes `quality-based-replacement` 5.1)
- [x] 3.5 `QUALITY_FINDING` with spectrogram endpoint (FFmpeg `showspectrumpic`, cached) and the stored human decision; verify both answers, that a re-run keeps the decision and that `too_quiet` and high-confidence results create no entry (closes `quality-analysis-core` 5.1)
- [ ] 3.6 (waits for `works`/`publishers`) `WORK_ASSIGNMENT` entries from publisher searches and the LLM extractor
- [ ] 3.7 (waits for `sources`) `DOWNLOAD_REPLACEMENT` entries for inconclusive downloads (`effective-quality-duplicate-checks`)
- [ ] 3.8 (waits for `sheet-music`) `SHEET_OMR` entries, one per sheet, closed on release
- [x] 3.9 `review_backfill` job for results from before this change; verify that it runs once and creates no duplicates

## 4. Client

- [x] 4.1 Create `client/src/features/review/` with route, navigation entry with open count (editors and admins), filter bar with counts, virtual list, detail with evidence (both recordings, spectrograms) and current vs. proposed value, per-type decision labels, defer, multi-select and "decide all matching"; texts de/en; verify with component tests
- [x] 4.2 E2E test: accept a `RECORDING_MATCH` entry and see the merged recording

## 5. Documentation

- [x] 5.1 Update `docs/architecture/sync-protocol.md` (stream `review.items`), `server/AGENTS.md` (how a domain registers a review type) and `docs/agent-notes.md`; tick the closed tasks of the four changes named above

## Workflow follow-up

- Archive the change once tasks 3.6–3.8 are done, or split them out, and verify `openspec validate --all --strict` passes.
