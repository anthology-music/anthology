# Tasks

## 1. Documentation and data model

- [x] 1.1 Update ADR 0008: streams deliver originals unchanged, downloads/exports get a cached context-tagged copy, tagger writes copies instead of building headers; verify no "tag header" wording remains in the ADR
- [x] 1.2 Update `docs/architecture/data-model.puml`: `TranscodeCacheEntry.kind : CacheKind` (`TRANSCODE`, `TAGGED_COPY`), `bitrateKbps` optional; verify the diagram renders with PlantUML without errors
- [x] 1.3 Update the interface draft in `services/tagger/README.md`: replace `POST /v1/header/build` with `POST /v1/tags/copy`; verify the README lists the new endpoint and no header endpoint

## 2. Playback delivery

- [x] 2.1 Serve active originals for playback with HTTP range support and no modification; verify with a test that a requested range equals the same range of the file on disk

## 3. Tagged downloads

- [x] 3.1 Implement the tagger `POST /v1/tags/copy` endpoint in `services/tagger` and add WAV and AIFF (ID3 chunk) to the tagger; verify with a test per supported format (FLAC, MP3, M4A/AAC, M4A/ALAC, Opus, Ogg Vorbis, WAV, AIFF) that the copy carries the context tags and the source hash is unchanged
- [x] 3.2 Implement the download endpoints per context track (`POST /api/v1/library/tracks/{id}/download`, `GET /media/downloads/tracks/{id}`) that create or reuse a `TAGGED_COPY` cache entry of the original and serve it with range support; verify with tests for first download, cache hit, resumed range request and concurrent requests creating only one copy
- [x] 3.3 Invalidate tagged copies of originals on context tag or original change and ignore them in duplicate detection and quality ranking; verify with tests for both invalidation triggers
- [x] 3.4 Fall back to the untagged original with a notice when the tagger is unavailable; verify with a test with the tagger stubbed as down
- [x] 3.5 Implement the album download (`POST /api/v1/library/releases/{id}/download`, streamed zip of tagged copies, temporary copies removed); verify with tests that the zip holds every track with its context tags and file name and that the cache holds no new entries afterwards

## 4. Client

- [x] 4.1 Add "Download" to the track menu and "Download album" to the album page, with the notice when the files carry no context tags; verify with component tests and an E2E test that downloads a track
- [x] 4.2 Update `docs/architecture/sync-protocol.md` (download endpoints), the tagger README (formats), `docs/roadmap.md` (album export done) and regenerate the API types; verify `pnpm api-types` leaves no diff

## Workflow follow-up

- Archive the change after review and verify `openspec validate --all --strict` passes.
