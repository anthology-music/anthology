# ADR 0013: AAC as the transcoding format

- Status: Accepted
- Date: 2026-10-09

## Context

Devices receive music in a configured bitrate (Original, 320, 256, 192, 128 kbit/s). The format must play on every target, including iOS, and sound good at 128 kbit/s.

## Decision

- Transcodes use **AAC in M4A**, encoded with FFmpeg's native AAC encoder (LGPL build, ADR 0004).
- **Never upscale:** if the effective quality of the original is below the target bitrate, the original is delivered – provided the target can play its format.
- **Format-aware delivery:** client devices and output adapters declare the audio formats they can play. If the target cannot play the original's format, a **compatibility transcode** is delivered:
  - lossless original with setting "Original" → **ALAC in M4A** (FFmpeg's native, LGPL encoder) if the target supports ALAC, otherwise AAC 320;
  - lossy original → AAC at the lowest bitrate step at or above its effective quality, capped by the configured bitrate (e.g. Opus 160 → AAC 192), to limit generation loss. The original's effective quality is still shown, never the transcode bitrate.
- Transcodes are cached and shared between users and devices; context tags are written automatically after transcoding.

## Alternatives considered

- **Opus:** better quality per bit, but less universal playback support (notably on Apple devices).
- **MP3:** universal but worse quality at 128 kbit/s.
- **libfdk_aac:** better AAC quality, but not free software; excluded.

## Consequences

- Universal playback; quality at low bitrates is good but not the best possible.
- Opus can be added later as an additional option per device.
