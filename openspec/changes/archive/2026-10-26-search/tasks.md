# Tasks

## 1. Documentation

- [x] 1.1 Add `search` to the domain table in AGENTS.md and the domain list in `openspec/config.yaml`; verify both list it
- [x] 1.2 Create `docs/architecture/search-syntax.md` with fields, operators, examples and error behavior; verify every example from the search spec is covered
- [x] 1.3 Update `docs/architecture/search-syntax.md` to the fields available now (later fields marked with their domain; offline search moved to `offline-sync`), describe the search streams in `docs/architecture/sync-protocol.md`, and add works and videos in search to `docs/roadmap.md`; verify with `openspec validate --all --strict`

## 2. Server

- [x] 2.1 Create `server/anthology/search/` with normalisation, `search_documents`, `search_terms` and `search_index_state` (migration, `pg_trgm`), change listeners in `core/changes.py` and document maintenance for artists, releases and tracks; verify with tests that edits, moves and deletions update the documents in the same transaction
- [x] 2.2 Write the documents in `seed_library` and add the job `search_reindex`, started at server start on an index version change; verify with tests
- [x] 2.3 Implement the parser with tokens, filters (`type`, `artist`, `album`, `composer`, `genre`, `year`, `format`, `quality`), per-token errors and `GET /api/v1/search/parse`; verify with tests for valid filters, quoted values, unknown fields and invalid values
- [x] 2.4 Implement matching and ranking (prefix, phrase, typo replacement, buckets) on PostgreSQL and SQLite; verify with tests for prefix, umlaut folding, accents, typos, ranking and type restriction on both engines
- [x] 2.5 Implement the search streams with capped counts per type, keyset paging, context, live deltas and cancellation; verify with protocol tests and a performance test on the 500,000-track generator (first results ≤ 300 ms, interactive ≤ 2 s at p95)
- [x] 2.6 Accept the search as `EditRule` list `search` for preview, values and bulk edits; verify with a test that a bulk edit affects exactly the matching tracks beyond the cap

## 3. Client

- [x] 3.1 Create `client/src/features/search/` with the search field in the layout, the search page with chips from the parsed tokens (remove, add filter), token hints, grouped results with counts and "show all" lists, and the album and artist context; verify with component tests for chips/syntax equivalence, hints and context
- [x] 3.2 Offer "edit all results" to editors with the search as rule; verify with a component test and an E2E test that searches, filters and opens a result

## Workflow follow-up

- Archive the change after review and verify `openspec validate --all --strict` passes.
