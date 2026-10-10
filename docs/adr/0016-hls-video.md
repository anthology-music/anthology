# ADR 0016: HLS for video playback

- Status: Accepted
- Date: 2026-10-09

## Context

Videos (music videos, concert recordings) are played on desktop, phones and tablets over varying connections, with a maximum resolution per user and device.

## Decision

- Videos are stored once in their original container (MKV/MP4) in a separate storage area; their audio is not stored separately.
- Playback uses **HLS**: renditions per resolution are generated on demand with FFmpeg and cached.
- Clients use HTML5 video with **hls.js** (native HLS on Safari/iOS).
- Audio-only playback of a video reads the audio track directly.

## Alternatives considered

- **Progressive MP4 download:** simple, but no adaptive quality and poor seeking on slow connections.
- **DASH:** comparable, but no native support on Apple devices.

## Consequences

- Extra CPU for generating renditions (hardware acceleration optional).
- Rendition cache needs its own size limit.
