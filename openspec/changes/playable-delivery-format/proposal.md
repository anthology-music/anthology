# Proposal

## Why

The transcoding spec delivers the original whenever its effective quality is below the target bitrate, regardless of whether the target can play the format. An Opus original would be sent unchanged to an iPhone or a Raumfeld speaker, and FLAC/WAV/AIFF with the setting "Original" to devices that cannot decode them. ADR 0013 chose AAC precisely for universal playback, so the delivery rule must take the target's formats into account.

## What Changes

- Every playback target (client device and output adapter) SHALL declare the audio formats it can play.
- An original SHALL be delivered unchanged only if the target can play its format and its effective quality does not exceed the configured bitrate.
- Otherwise the system SHALL create a **compatibility transcode**:
  - lossless original with setting "Original" → ALAC in M4A if the target supports ALAC, otherwise AAC 320;
  - lossy original → AAC at the lowest bitrate step at or above its effective quality, capped by the configured bitrate.
- "Never upscale" is refined: a compatibility transcode MAY use the next bitrate step above the effective quality to limit generation loss, and the delivered stream SHALL never be presented as better than the original's effective quality.
- The target format is extended from "AAC in M4A" to "AAC or ALAC in M4A".

## Capabilities

### New Capabilities

_None._

### Modified Capabilities

- `transcoding`: "Never upscale" and "Target format" change; new requirements for format-aware delivery and compatibility transcodes.
- `playback`: "Output adapters" additionally declare supported audio formats.

## Impact

- **Domains:** transcoding, playback. sync-protocol only carries the client's format list (detail in design); users unchanged.
- **Data model:** `Device.supportedFormats` and `OutputDevice.supportedFormats` (set of `AudioFormat`). Migration only once the schema exists.
- **Docs:** ADR 0013 amended (ALAC as lossless compatibility format, next-step rule).
- **Dependencies:** none new; FFmpeg's native ALAC encoder is part of the LGPL build.
- **Non-functional requirements (2 s, 500,000 tracks):** none. Compatibility transcodes use the existing shared cache.
