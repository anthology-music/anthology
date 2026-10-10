# ADR 0016: HLS for video playback

- Status: Accepted
- Date: 2026-10-09

## Context

Videos (music videos, concert recordings) are played on desktop, phones and tablets over varying connections, with a maximum resolution per user and device.

## Decision

- Videos are stored once in their original container (MKV/MP4) in a separate storage area; their audio is not stored separately.
- Videos are a **separate media type**: a video's audio track is never an audio original and takes no part in quality ranking or replacement of audio originals (music videos often use a different mix, concert videos are different recordings). Duplicate checks for audio and video orders are separate.
- A recording without an audio original but with a linked video can be played as audio only through the video's audio track.
- Duplicate videos are detected by source item and content hash; a higher resolution of the same source item replaces the stored video, keeping links and chapters.
- Playback uses **HLS**: renditions per resolution are generated on demand with FFmpeg and cached.
- Clients use HTML5 video with **hls.js** (native HLS on Safari/iOS).
- Audio-only playback of a video uses its audio track extracted into the transcode cache (temporary, evictable) and served with range requests like any audio; no permanent second audio file is stored.

## Alternatives considered

- **Progressive MP4 download:** simple, but no adaptive quality and poor seeking on slow connections.
- **DASH:** comparable, but no native support on Apple devices.

## Consequences

- Extra CPU for generating renditions (hardware acceleration optional).
- Rendition cache needs its own size limit.
