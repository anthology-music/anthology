# Design

## Context

Playback (`local-playback`) issues signed URLs for queue entries (`POST /api/v1/playback/urls`) and serves active originals with range requests. Devices have a bitrate setting per user (`UserDeviceSettings.audio_bitrate`, `GET/PUT /api/v1/me/device-settings`), but no client UI for it. The client detects playable formats with `canPlayType` (`client/src/features/playback/formats.ts`). Originals carry format, bitrate, declared and effective quality tiers (`hires_lossless`, `cd_lossless`, `lossy_high` ≥ 256 kbit/s, `lossy_low`). FFmpeg is an LGPL build with the native `aac` and `alac` encoders and the `mp4`/`ipod` muxers (ADR 0020). The tagger service copies a file and writes tags into the copy (`POST /v1/tags/copy`, `TaggerClient.copy`). See proposal.md for the decisions.

## Goals / Non-Goals

**Goals:**
- Every device receives a format it can play in at most its configured bitrate, never upscaled.
- Playback of a new transcode starts at once; repeated plays come from the cache.
- Transcodes carry the context tags of the track they are played in.

**Non-Goals:**
- Cover images in transcodes (change `covers`), Opus as a target, sample-rate limits of targets.
- Output adapters (Raumfeld; `playable-delivery-format` 3.3), downloads and offline copies (`context-tags-on-delivery`, `offline-sync`; they reuse this cache).

## Decisions

### Delivery decision

A pure function `decide(original, setting, formats) -> Original | Transcode(format, bitrate)` in `transcoding/delivery.py`, after `playable-delivery-format`:

1. **Effective bitrate:** lossless tiers have none (above every step); `lossy_high` is the file's bitrate; `lossy_low` is the file's bitrate if it is below 256 kbit/s, otherwise 128 (an upscaled file: its real bitrate is unknown, so the lowest step keeps "never upscale"). Without an effective quality (not analysed), the declared tier stands in (spec: Quality before analysis).
2. The original is delivered if the device plays its format and the setting is Original or at least the effective bitrate.
3. If the effective bitrate is above the setting: AAC at the setting.
4. Otherwise the format is not playable (a compatibility transcode): lossless with setting Original → ALAC if the device plays ALAC, else AAC 320; lossy → AAC at the lowest step at or above the effective bitrate, capped by the setting.

Steps: 320, 256, 192, 128. Without a known format list the server assumes AAC and MP3 only.

### Device formats

`hello` gains `formats` (list of audio formats). The server stores them on `devices.supported_formats` (JSON) when they differ. The client sends the list it already computes with `canPlayType`, counting only "probably" (and "maybe" for FLAC, MP3 and WAV, which browsers report that way although they play them). A `hello` without `formats` keeps the last list. The decision reads the formats of the requesting device.

### Cache entries

Table `transcode_cache` (model `TranscodeCacheEntry`):

- `kind`: `transcode` (the audio of one original in one format and bitrate, untagged) or `tagged_copy` (a transcode with the tags of one context track);
- `audio_file_id`, `format` (`aac`, `alac`), `bitrate_kbps` (none for ALAC), `context_track_id` (tagged copies);
- `status` (`running`, `ready`, `failed`), `path` below `<data_dir>/transcodes/`, `size_bytes`, `created_at`, `last_accessed_at`.

A unique `variant_key` (kind, original, variant, context as one string; implemented this way instead of a unique index over the columns, because NULLs (no bitrate, no context) are distinct in unique indexes on SQLite) makes creation idempotent across processes: the process whose insert wins transcodes, the others follow its file. A stuck `running` row is taken over with a compare-and-swap on `created_at`, so only one process restarts it.

### Transcoding and streaming

`Transcoder` (one per process) runs FFmpeg as a separate process: `-i <original> -vn -c:a aac -b:a <n>k` (or `-c:a alac`), `-f mp4 -movflags +frag_keyframe+empty_moov+default_base_moof -frag_duration 1000000` into `<name>.part`; on success the file is renamed and the row set `ready`, on failure `failed`. At most two transcodes run at once per process (more wait); a stuck `running` row whose process died (no change of the `.part` file for 30 s) is taken over.

`GET /api/v1/media/transcodes/{track_id}/{variant}` (signed like originals; `variant` is `aac-128` … `aac-320` or `alac`) serves:

- **ready:** the tagged copy of the track if present, otherwise the transcode, as a `FileResponse` with range requests;
- **running:** the growing `.part` file as a chunked response that follows the file until FFmpeg finishes (no `Content-Length`, no ranges: the browser plays fragmented MP4 progressively; seeking waits for the complete file);
- **missing:** starts the transcode, then as running.

`POST /api/v1/playback/urls` returns per entry the URL of the decided variant, the delivered format and whether it is a transcode; for the next entry of the queue it also starts the transcode in the background (spec: Prepared next track). The client shows the original's effective quality from the track row in every case.

Alternative considered: transcode completely before playing. Rejected by the maintainer: playback should start at once.

### Tagged copies

When a ready transcode is requested for a track and no ready tagged copy exists, the server asks the tagger to copy it with the track's context tags (the same fields as the tag writer's home context, without images until `covers`). This happens in the request when the tagger answers within 5 seconds, otherwise the untagged transcode is served and the next request tries again. Running transcodes are always served untagged.

Invalidation: a change listener collects changed tracks, recordings, releases and originals; before the commit it marks the tagged copies of the affected tracks (and every entry of a replaced or superseded original) as stale (`status = failed` → removed by the cache sweep). Files are deleted after the commit by the sweep, never inside the transaction.

### Cache size

`ANTHOLOGY_TRANSCODE_CACHE_GB` (default 20). After every completed transcode or copy a sweep removes stale entries and then the least recently used ready entries until the cache fits; `last_accessed_at` is updated at most once a minute per entry. Running entries are never removed. Files without a row in `<data_dir>/transcodes/` are removed by the sweep after an hour.

### Pull requests

1. Delivery decision, device formats in `hello`, bitrate setting in the client, transcoding with streaming, cache with size limit, quality display.
2. Tagged copies per context with invalidation.

## Risks / Trade-offs

- **[Fragmented MP4 in some browsers]** Chrome, Firefox and Safari play fragmented MP4 progressively in an audio element. The E2E test plays a fresh transcode in Chromium.
- **[No seeking while a transcode runs]** Seeking before the transcode is complete waits; a three-minute track transcodes in a few seconds, and the next entry is prepared ahead.
- **[Tagger slow or down]** It is bounded by the 5-second timeout and the untagged fallback.
- **[Two processes start the same transcode]** The unique index lets only one transcode; the other follows the file on the shared data volume.
- **[Disk usage]** It is bounded by the cache limit; running entries may exceed it briefly.
