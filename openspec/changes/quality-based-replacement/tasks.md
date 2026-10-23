# Tasks

## 1. Foundations

- [x] 1.1 Migration and models: `ImportResult` values `replaces_lower_quality` and `suspicious_quality`, `library_imports.delete_replaced`, counters `superseded_managed_files`/`superseded_managed_bytes`; update `docs/architecture/data-model.puml`; verify with the migration round-trip and model comparison tests on SQLite and PostgreSQL
- [x] 1.2 Remove the automatic quality analysis after imports and amend the delta of `quality-analysis-core` (requirement "Analysis job"); verify with a test that an import starts identification but no quality analysis

## 2. Library

- [x] 2.1 Quality ranking (`effective_rank`, better/inconclusive rules); verify with unit tests for each rule including equal ranks and upscaled existing files
- [x] 2.2 `replace_original` for managed current originals and replacements of any storage mode, managed counters, guard (superseded managed: delete only), `delete_superseded` with change entries; narrow the rule "the new file becomes managed" in the delta of `managed-and-referenced-originals` to acquisitions; verify with service tests (counters, contexts kept, guard matrix, referenced never deletable)
- [x] 2.3 Job `delete_superseded` with checksum verification of the replacement and `POST /api/v1/library/superseded/deletion` (admins); stream rows with storage mode and managed counters; verify with tests for success, a mismatching replacement and roles, and a protocol test

## 3. Import

- [x] 3.1 Classification: analyse candidates (both sides, stored per hash), `replaces_lower_quality`, `suspicious_quality`, best copy within the source (swap of earlier items); verify with generated files for each scenario of the spec, including an MP3-quality file in one folder and a genuine FLAC in another, and that non-candidates are not analysed
- [x] 3.2 Apply: transfer and replace, track context, deletion of the old managed file after verification when `delete_replaced`, otherwise keep superseded; referenced originals kept; report counts; verify with tests for both options, a referenced old original, a failed verification and the report categories
- [x] 3.3 API option `delete_replaced` (default true); verify with an API test

## 4. Client

- [x] 4.1 Import dialog option and report lines (new categories, replacements, deletion option); texts de/en; verify with client tests
- [x] 4.2 Settings › Library: superseded originals (counts, list, deletion of managed files with confirmation; referenced marked as never deleted); verify with a client test

## 5. Deferred

- [ ] 5.1 (waits for `review-list`) Review entries for "suspicious quality"

## 6. Documentation

- [x] 6.1 Update `server/AGENTS.md`, `docs/agent-notes.md`, the sync protocol stream table, and tick `library-import-folders` 7.1; verify the files and `openspec validate --all --strict`
