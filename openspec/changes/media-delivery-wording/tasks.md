# Tasks

## 1. Documentation

- [x] 1.1 Update AGENTS.md: audio over HTTP range requests, video over HLS, never over the WebSocket; verify the "Architecture principles" bullet states both paths
- [x] 1.2 Update ADR 0016: audio-only playback uses audio extracted into the transcode cache and served with range requests; verify "reads the audio track directly" is gone

## 2. Audio-only playback of videos

- [ ] 2.1 Extract the audio track of a video into the transcode cache on first audio-only request (stream copy, or AAC if the target cannot play the codec) and serve it with range support; verify with a test that no file outside the cache is created and a range request returns the matching bytes of the cached file

## Workflow follow-up

- Archive the change after review and verify `openspec validate --all --strict` passes.
