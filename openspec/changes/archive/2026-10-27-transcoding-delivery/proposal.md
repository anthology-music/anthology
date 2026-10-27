# Proposal

## Why

Listening works, but every device receives the original: the device's bitrate setting has no effect, FLAC-only libraries cannot play on devices without FLAC support, and a phone on mobile data downloads hi-res files. The transcoding spec (AAC at the device's bitrate, never upscale, shared cache, context tags) and the change `playable-delivery-format` (devices report their formats, compatibility transcodes) describe the target, but nothing is built.

## What Changes

- **Delivery decision** per device and track: original or transcode (AAC in M4A at the device's bitrate, ALAC in M4A for lossless compatibility), following "never upscale" and the format-aware delivery of `playable-delivery-format` (its tasks 2.1, 2.2, 3.1, 3.2 and 3.4 are done here; 3.3 waits for the Raumfeld adapter).
- **Devices report their playable formats** in `hello`; the server stores them on the device.
- **Bitrate setting in the client:** "Bitrate on this device" (Original, 320, 256, 192, 128 kbit/s) in the settings.
- **Transcoding while streaming:** a transcode that does not exist yet is created on the first request and streamed while FFmpeg writes it (fragmented MP4); seeking works once it is complete. The next entry of the queue is prepared ahead, so tracks follow each other without a pause.
- **Shared transcode cache:** one transcode per original, format and bitrate, shared by all users and devices, with a size limit (`ANTHOLOGY_TRANSCODE_CACHE_GB`, default 20) and eviction of the least recently used entries.
- **Context tags in transcodes:** for each context (track) a copy of the transcode is tagged through the tagger service (`POST /v1/tags/copy`); the cover follows with the change `covers`. While the tagger is unavailable, the untagged transcode plays and tagging happens on a later request. Tagged copies are discarded when the context's tags or the original change.
- **Quality before analysis:** until an original is analysed, its declared quality stands in for the effective quality in the delivery decision.
- The client shows the original's effective quality, never the transcode bitrate.
- Decided with the maintainer:
  - transcodes are streamed while they are being created;
  - transcodes are tagged now through the tagger;
  - declared quality stands in until the analysis.

## Capabilities

### New Capabilities

_None._

### Modified Capabilities

- `transcoding`: new requirements "Streaming while transcoding", "Transcode cache size", "Quality before analysis", "Tagged copies per context".
- `playback`: "Playback on this device" delivers according to the transcoding spec; "Formats the device cannot play" now means: no delivery is possible (a transcode failed).

## Impact

- **Domains:** transcoding (new server module `server/anthology/transcoding/`), playback (URLs and media endpoints), users (device formats, bitrate setting UI), sync-protocol (`hello` carries the formats), tagging (tagger client).
- **Data model:** `TranscodeCacheEntry` (kind `TRANSCODE` or `TAGGED_COPY`, original, format, bitrate, context track, status, size, last access) and `Device.supportedFormats` are already in `docs/architecture/data-model.puml`; `status` and `createdAt` are added. Migration needed.
- **Docs:** `docs/architecture/sync-protocol.md` (`hello`, media URLs), `server/AGENTS.md` (transcoding), ADR 0013 unchanged.
- **Dependencies:** none; FFmpeg's native AAC and ALAC encoders and the MP4 muxer are already in the LGPL build (ADR 0020).
- **Non-functional requirements (2 s, 500,000 tracks):** none for lists; the first byte of a new transcode arrives within about a second, later requests are served from the cache.
- **Two pull requests:** 1) delivery decision, device formats, bitrate setting, transcoding with streaming and cache; 2) tagged copies per context and their invalidation.
