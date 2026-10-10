# Proposal

## Why

AGENTS.md and the sync-protocol requirement "Media over HTTP" say audio and video are served over HTTP with range requests, while ADR 0016 and the video spec stream video adaptively over HLS. In addition, "audio-only playback reads the audio track directly" from the video cannot be served as byte ranges of the video container. The wording must match the decided delivery paths.

## What Changes

- Audio SHALL be delivered over HTTP with range requests; video SHALL be delivered adaptively over HLS (HTTP segments); neither over the WebSocket.
- Audio-only playback of a video SHALL use an audio track extracted into the transcode cache (temporary, evictable) and delivered with range requests like any audio; no permanent second audio file is created.
- AGENTS.md and ADR 0016 are updated accordingly.

## Capabilities

### New Capabilities

_None._

### Modified Capabilities

- `sync-protocol`: "Media over HTTP" distinguishes audio (range requests) and video (HLS).
- `video`: "No duplicate audio" specifies extraction into the transcode cache for audio-only playback.

## Impact

- **Domains:** sync-protocol, video. transcoding referenced (cache), not changed.
- **Data model:** none – extracted audio is a `TranscodeCacheEntry` of kind `TRANSCODE` with the original format (or AAC if the target cannot play it, see change `playable-delivery-format`).
- **Docs:** AGENTS.md, ADR 0016.
- **Non-functional requirements (2 s, 500,000 tracks):** none.
