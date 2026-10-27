# Tasks

## 1. Documentation and data model

- [x] 1.1 Add `status`, `createdAt` and the original to `TranscodeCacheEntry` in `docs/architecture/data-model.puml`; describe `formats` in `hello`, the transcode endpoint and the URL answer in `docs/architecture/sync-protocol.md`, and the transcoding module in `server/AGENTS.md`; verify the diagram renders and `openspec validate --all --strict` passes

## 2. Pull request 1: delivery and transcoding

- [x] 2.1 Implement the delivery decision as a pure function in `server/anthology/transcoding/delivery.py`; verify with a parametrised test over formats × settings × format lists × qualities, including every scenario of the transcoding specs (`playable-delivery-format` 2.1)
- [x] 2.2 Accept `formats` in `hello` and store them on the device (migration), falling back to AAC and MP3; send them from the client; verify with protocol tests for both cases and a client unit test with a mocked `canPlayType` (`playable-delivery-format` 3.1, 3.2)
- [x] 2.3 Create the transcode cache (migration) and the transcoder with AAC and ALAC output in fragmented MP4, the unique entry per variant, the concurrency limit and the takeover of stuck entries; verify with tests on generated audio that AAC has the requested bitrate and ALAC decodes to identical PCM, and that two concurrent requests run FFmpeg once (`playable-delivery-format` 2.2)
- [x] 2.4 Serve transcodes at `GET /api/v1/media/transcodes/{track_id}/{variant}` (ready with ranges, running as a growing stream, missing started), return the decided variant from `POST /api/v1/playback/urls` and prepare the next entry; verify with API tests for each state, a signed and a tampered URL, and that the next entry's transcode starts
- [x] 2.5 Implement the cache size limit with least-recently-used eviction, stale entries and orphaned files; verify with tests using a small limit
- [x] 2.6 Add "Bitrate on this device" to the client settings, use the delivered format for playability, and show the original's effective quality; verify with component tests and an E2E test that plays a FLAC track at 128 kbit/s while it is being transcoded (`playable-delivery-format` 3.4)

## 3. Pull request 2: tagged copies

- [x] 3.1 Create tagged copies per context through the tagger with the 5-second bound and the untagged fallback; verify with tests using a fake tagger: first request, cache hit, tagger down, slow tagger
- [x] 3.2 Invalidate tagged copies on changes of the context's tags and entries of replaced or superseded originals; verify with tests for an album rename, a recording edit and a replaced original

## Workflow follow-up

- Tick `playable-delivery-format` 2.1, 2.2, 3.1, 3.2 and 3.4, and `context-tags-on-delivery` 2.1 (done with `local-playback`).
- After pull request 2: archive the change and verify `openspec validate --all --strict` passes.
