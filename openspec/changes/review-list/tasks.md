# Tasks

## 1. Documentation and data model

- [x] 1.1 Add `review` to the domain table in AGENTS.md and the domain list in `openspec/config.yaml`; verify both list `review` with server module `review`
- [x] 1.2 Update `docs/architecture/data-model.puml`: new package "Review" with `ReviewItem`, `ReviewType`, `ReviewOrigin`; `ReviewStatus` with `DEFERRED` and `OBSOLETE` (`AUTO_ACCEPTED` kept for sheets); `JobType.REVIEW_BULK`; replace `WorkCandidate`; verify the diagram renders without errors on the PlantUML server and contains no `WorkCandidate`

## 2. Review module (server)

- [ ] 2.1 Create `server/anthology/review/` with model, migration, partial unique index on `suppressionKey` and maintained counters; verify with tests that duplicates and rejected suggestions are not re-created
- [ ] 2.2 Implement handler registration and accept/reject/defer with re-validation and `OBSOLETE`; verify with tests for each decision and a stale proposal
- [ ] 2.3 Implement the `review.items` subscription with counts first, filters and keyset paging; verify with protocol tests and a performance test with 20,000 entries meeting the 2-second budget
- [ ] 2.4 Implement bulk decisions by selection rule as a `REVIEW_BULK` job; verify with a test that progress is reported and each item records the decision
- [ ] 2.5 Restrict list and decisions to editors and admins; verify with API tests for all three roles

## 3. Producers

- [ ] 3.1 Register handlers and create entries in library (recording match), quality-analysis (finding), works/publishers (work assignment), library-import (needs review), sources (download replacement) and sheet-music (OMR); verify with one test per producer that an entry is created and accepting applies the change

## 4. Client

- [ ] 4.1 Create `client/src/features/review/` with filter bar, counts, virtual list, entry detail with evidence and current vs. proposed value, and bulk actions; verify with component tests and an E2E test accepting an entry

## Workflow follow-up

- Archive the change after review and verify `openspec validate --all --strict` passes.
