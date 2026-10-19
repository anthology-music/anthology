# Tasks

## 1. Documentation and data model

- [x] 1.1 Add `metadata-lookup` to the domain table in AGENTS.md (server module `metadata_lookup`) and the domain list in `openspec/config.yaml`; amend ADR 0009 with rate limits, cache, mirror fallback and periodic refresh; verify all three files
- [x] 1.2 Create `docs/architecture/musicbrainz-mirror.md` (requirements, replication token, configuration, fallback, license notes marked as to be checked); verify the hardware figures and the configuration variable are documented
- [x] 1.3 Add `LookupCache`, `ExternalRef` and `JobType.METADATA_REFRESH` to `docs/architecture/data-model.puml`; verify the diagram renders without errors on the PlantUML server
- [x] 1.4 Check the licenses of `musicbrainz-docker`, the MusicBrainz server and the replicated data and record the result in `THIRD_PARTY_LICENSES.md`; verify the entries exist

## 2. Server

- [x] 2.1 Create `server/anthology/metadata_lookup/` with clients, token-bucket limiters, priority queue and persistent cache; verify with tests using a fake clock and recorded responses (rate, priority, cache hit, back-off)
- [x] 2.2 Implement mirror configuration, health check and per-request fallback; verify with tests for mirror up, down and unsupported request
- [x] 2.3 Implement the queue duration estimate and the mirror recommendation; verify with a test for the 24-hour threshold
- [ ] 2.4 (waits for `tag-editing`) Implement the `METADATA_REFRESH` job through the tagging service; verify with tests that unprotected fields update and protected fields create conflicts

## Workflow follow-up

- Archive the change after review and verify `openspec validate --all --strict` passes.
