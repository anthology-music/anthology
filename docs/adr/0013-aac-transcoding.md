# ADR 0013: AAC as the transcoding format

- Status: Accepted
- Date: 2026-10-09

## Context

Devices receive music in a configured bitrate (Original, 320, 256, 192, 128 kbit/s). The format must play on every target, including iOS, and sound good at 128 kbit/s.

## Decision

- Transcodes use **AAC in M4A**, encoded with FFmpeg's native AAC encoder (LGPL build, ADR 0004).
- **Never upscale:** if the effective quality of the original is below the target bitrate, the original is delivered.
- Transcodes are cached and shared between users and devices; context tags are written automatically after transcoding.

## Alternatives considered

- **Opus:** better quality per bit, but less universal playback support (notably on Apple devices).
- **MP3:** universal but worse quality at 128 kbit/s.
- **libfdk_aac:** better AAC quality, but not free software; excluded.

## Consequences

- Universal playback; quality at low bitrates is good but not the best possible.
- Opus can be added later as an additional option per device.
