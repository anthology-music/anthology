# Design

## Context

ADR 0013 fixes AAC/M4A with FFmpeg's native encoder and "never upscale". The transcode cache is keyed by recording, bitrate, format and context. Output adapters already declare capabilities (ADR 0011). Devices are registered on first sign-in (ADR 0015) and the WebSocket starts with `hello`. See proposal.md for the motivation.

## Goals / Non-Goals

**Goals:**
- Every target receives a format it can decode.
- Minimal generation loss and no misleading quality display.

**Non-Goals:**
- Opus as an additional transcode target (ADR 0013, later option).
- Sample-rate/bit-depth limits of targets (e.g. a speaker that cannot play 24/192); can be added to the same capability list later without changing this decision.
- Video formats (HLS, video spec).

## Decisions

### Where the format list comes from

- **Client devices:** the client determines playable formats at start-up (`HTMLMediaElement.canPlayType` / `MediaSource.isTypeSupported` on web, native checks in Tauri/Capacitor) and sends them in `hello`. The server stores the last list on `Device.supportedFormats`. Detection at runtime beats a static table because WebView capabilities differ between OS versions.
- **Output adapters:** each adapter reports `supportedFormats` per discovered device (Raumfeld from its UPnP `GetProtocolInfo`, otherwise a static default in the adapter), stored on `OutputDevice.supportedFormats`.
- If no list is known, the server assumes AAC/M4A and MP3 only.

### Delivery decision (one pure function)

Inputs: original (format, lossless flag, effective quality), configured bitrate, target formats. Output: original or (format, bitrate). Steps:

1. If the target plays the original's format and effective quality ≤ setting (or setting is Original) → original.
2. If the effective quality > setting → AAC at the setting (normal transcode, unchanged).
3. Else (format not playable): lossless and setting Original → ALAC if supported, else AAC 320; lossy → AAC at the lowest step ≥ effective quality, capped by the setting.

The function is unit-tested exhaustively over the format × setting × capability matrix.

### Next step up for lossy re-encoding

Re-encoding lossy audio at the same or a lower nominal bitrate adds audible artifacts, especially from Opus (more efficient than AAC) to AAC. One step up keeps the second-generation loss small while staying bounded by the user's setting. The displayed quality stays the original's effective quality, so nothing is "upscaled" from the user's point of view.

Alternative considered: highest step ≤ effective quality (strict reading). Rejected by the maintainer: audible loss for no storage benefit.

### ALAC for lossless compatibility

ALAC in M4A is decodable on all Apple platforms and in most WebViews where FLAC may be missing; FFmpeg's native `alac` encoder is LGPL. It keeps "Original" lossless.

### Cache

Compatibility transcodes are ordinary transcode cache entries; the key already contains format and bitrate, so ALAC and AAC variants coexist.

### Progressive loading

Not affected. The format list adds a few bytes to `hello`.

## Risks / Trade-offs

- [Client misreports formats (e.g. `canPlayType` returns "maybe")] → treat only "probably" as supported for web; allow a per-device override in settings.
- [ALAC files are large on mobile networks] → only used when the user chose "Original"; bitrate settings still apply.

## Migration Plan

Nothing deployed. Documentation updates only until the transcoding and playback modules exist.
