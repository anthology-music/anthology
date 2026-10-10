# Tasks

## 1. Documentation

- [x] 1.1 Add `search` to the domain table in AGENTS.md and the domain list in `openspec/config.yaml`; verify both list it
- [x] 1.2 Create `docs/architecture/search-syntax.md` with fields, operators, examples and error behavior; verify every example from the search spec is covered

## 2. Server

- [ ] 2.1 Create `server/anthology/search/` with the `search_document` table, normalisation (unaccent + German folding) and maintenance from the owning domains' write paths; verify with tests that edits update the document in the same transaction
- [ ] 2.2 Implement matching and ranking with `tsvector`, `pg_trgm` and SQLite FTS5; verify with tests for prefix, umlaut folding, accents and typos on both engines
- [ ] 2.3 Implement the query model with syntax validation and per-token errors; verify with tests for valid filters, unknown fields and invalid values
- [ ] 2.4 Implement the `search` subscription with capped counts per type, keyset paging per type, context restriction and cancellation; verify with a performance test on the 500,000-track generator (first results ≤ 300 ms, interactive ≤ 2 s at p95)
- [ ] 2.5 Accept a search query as selection rule for bulk actions; verify with a test that a bulk edit affects exactly the result set

## 3. Client

- [ ] 3.1 Create `client/src/features/search/` with search field, parser shared with chips, grouped results and context scope; verify with unit tests for the parser and component tests for chips/syntax equivalence
- [ ] 3.2 Implement offline search over cached and offline items with local-only marking; verify with a test that offline results are returned without a connection

## Workflow follow-up

- Archive the change after review and verify `openspec validate --all --strict` passes.
