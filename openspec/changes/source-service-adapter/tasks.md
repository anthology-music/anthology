# Tasks

## 1. Documentation and data model

- [ ] 1.1 Complete `docs/architecture/source-service-api.md` with every v1 field and the errors; add `SourceService`, `SourceCredential`, `DownloadOrder`, `DownloadOrderItem`, `Source.kind` as a string and `AudioFile.source` to `docs/architecture/data-model.puml`; describe the streams in `docs/architecture/sync-protocol.md`, the module in `server/AGENTS.md` and the configuration in `docs/install.md`; verify the diagram renders and `openspec validate --all --strict` passes

## 2. Pull request 1: connection, search and links

- [x] 2.1 Create `tools/fake-source-service/` speaking interface v1 (catalogue, links, optional login, rate limit, FLAC tone downloads); verify with its own tests for every endpoint
- [x] 2.2 Create `server/anthology/sources/` with `source_services` (migration), the monitor with info, health and version check, and the stream `sources.services`; verify with tests against the fake for available, unavailable and incompatible-version services (`external-source-services` 3.1)
- [x] 2.3 Store login fields encrypted (key in the keys directory), log services in and in again after a logout; verify with tests that values are encrypted at rest, never returned, and sent again after a restart of the fake
- [x] 2.4 Implement search across services and link resolving with the duplicate status per track; verify with tests for ISRC and name matches, equal, better and missing quality, unrecognised links and a slow service
- [x] 2.5 Build the Streaming view search with results, the album's tracks with duplicate status and selection, the source status view for every user (opened explicitly) and the admins' source settings with login; verify with component tests, including that reasons appear only after opening the status

## 3. Pull request 2: orders and library

- [ ] 3.1 Create orders and the job `source_download` with one item per track, present tracks finished at once, download via the service, progress, rate-limit waiting and takeover; verify with tests against the fake (`external-source-services` 3.2, `effective-quality-duplicate-checks` 3.1)
- [ ] 3.2 Import the order folder automatically (managed, `move`) with the import's comparison, map the outcomes to the items, remove what is not better, create review entries for inconclusive comparisons; verify with tests for new, replaced, not better and needs review (`effective-quality-duplicate-checks` 3.2)
- [ ] 3.3 Store the source and retrieval date per original and show them in the album view; verify with a test and a component test
- [ ] 3.4 Build the orders list with counts and items in the Streaming view; verify with component tests and an E2E test that searches the fake service, orders an album and plays a downloaded track

## Workflow follow-up

- Tick `external-source-services` 3.1 and 3.2 and `effective-quality-duplicate-checks` 3.1 and 3.2; archive `external-source-services`.
- After pull request 2: archive this change and verify `openspec validate --all --strict` passes.
