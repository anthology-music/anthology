# Tasks

## 1. Documentation and data model

- [x] 1.1 Update ADR 0008: streams deliver originals unchanged, downloads/exports get a cached context-tagged copy, tagger writes copies instead of building headers; verify no "tag header" wording remains in the ADR
- [x] 1.2 Update `docs/architecture/data-model.puml`: `TranscodeCacheEntry.kind : CacheKind` (`TRANSCODE`, `TAGGED_COPY`), `bitrateKbps` optional; verify the diagram renders with PlantUML without errors
- [x] 1.3 Update the interface draft in `services/tagger/README.md`: replace `POST /v1/header/build` with `POST /v1/tags/copy`; verify the README lists the new endpoint and no header endpoint

## 2. Playback delivery

- [ ] 2.1 Serve active originals for playback with HTTP range support and no modification; verify with a test that a requested range equals the same range of the file on disk

## 3. Tagged downloads

- [ ] 3.1 Implement the tagger `POST /v1/tags/copy` endpoint in `services/tagger`; verify with a test per supported format (FLAC, MP3, M4A/ALAC, Opus, Ogg Vorbis, WAV, AIFF) that the copy carries the context tags and the source hash is unchanged
- [ ] 3.2 Implement the download endpoint per context track that creates or reuses a `TAGGED_COPY` cache entry and serves it with range support; verify with tests for first download, cache hit, resumed range request and concurrent requests creating only one copy
- [ ] 3.3 Invalidate tagged copies on context tag or original change and ignore them in duplicate detection and quality ranking; verify with tests for both invalidation triggers
- [ ] 3.4 Fall back to the untagged original with a notice when the tagger is unavailable; verify with a test with the tagger stubbed as down

## Workflow follow-up

- Archive the change after review and verify `openspec validate --all --strict` passes.
