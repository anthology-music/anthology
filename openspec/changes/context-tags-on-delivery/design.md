# Design

## Context

_Written before the code existed; the decisions below were updated when the downloads were built (2026-10-28)._

ADR 0008 lists "downloads and streams of originals: a generated tag header in front of the original audio data", and the tagger draft (`services/tagger/README.md`) has `POST /v1/header/build` returning audio-data offsets. sync-protocol requires HTTP range requests for media. The data model has `TranscodeCacheEntry` (format, bitrate, optional context track). No code exists yet. See proposal.md for the motivation.

## Goals / Non-Goals

**Goals:**
- Range requests on originals are plain file ranges.
- Files leaving Anthology carry correct context tags in every supported format.

**Non-Goals:**
- Virtual header splicing (possible later optimization for FLAC/MP3, see Decisions).
- Tagging of transcodes – already specified in transcoding.
- Offline copies on devices: the client keeps metadata in its own cache and stores raw originals or transcodes; no change.
- FUSE view for foreign programs (ADR 0008, later).

## Decisions

### Separate playback and download paths

Playback serves the original file directly (FastAPI file response with range support; later possibly via a reverse proxy). Downloads go through a tagged-copy endpoint per context track.

Alternative considered: virtual splicing of a generated header with the original's audio data for every request. Rejected for now: it needs format-specific rewriting (Ogg page renumbering and CRCs, MP4 `stco`/`co64` offsets) and makes every playback request depend on the tagger. It remains possible as an optimization for FLAC and MP3 without changing the specified behavior.

### Tagger writes into a copy

The tagger interface gets `POST /v1/tags/copy`: source path, target path in the cache volume, complete context tags and cover. The source is opened read-only; this also works for referenced originals (see change `managed-and-referenced-originals`). `POST /v1/header/build` is removed from the draft.

### One cache for transcodes and tagged copies

`TranscodeCacheEntry` gets `kind : CacheKind` (`TRANSCODE`, `TAGGED_COPY`) and `bitrateKbps` becomes optional. Both kinds share eviction (LRU) and the size limit, and the existing invalidation on tag or original changes (`changeSeq`) applies unchanged. A tagged copy is created on first download, with the request waiting for it (a copy plus tag write takes well under the time of the download itself); concurrent requests for the same key wait on the same creation.

Alternative considered: a separate cache. Rejected: two limits to configure and two eviction policies for the same kind of data.

### Download endpoints

- `POST /api/v1/library/tracks/{track_id}/download` creates (or finds) the tagged copy of the track's active original and answers with a signed media URL (one hour, like playback), the file name and `tagged` (false with `notice: "tagger_unavailable"` when the tagger could not write it). The request waits for the copy, at most `DOWNLOAD_TAGGING_TIMEOUT` (60 s); concurrent requests for the same key wait on the one row that won the insert.
- `GET /media/downloads/tracks/{track_id}` (signed) serves the cached copy with range support and `Content-Disposition: attachment`; it repeats the lookup, so an evicted copy is written again (the tagger writes the same bytes for the same tags). Without a copy it serves the original.
- The cache entry is `kind = TAGGED_COPY` with the original's format and no bitrate; its variant key names `original` instead of a transcode variant. The existing invalidation (context track, inactive original) covers it unchanged.
- File names: `NN Title.ext` (`D-NN` on albums with more than one disc), with characters that are invalid on Windows, macOS or Linux replaced.

### Album download as zip

`POST /api/v1/library/releases/{release_id}/download` answers with a signed URL to `GET /media/downloads/releases/{release_id}`, which streams a zip (stored, not compressed – audio is compressed already; ZIP64 for large albums) named `Album artist - Title.zip`. Each track uses its cached tagged copy if there is one; otherwise the tagger writes a temporary copy below the cache root that is deleted right after it was streamed, so an album export does not fill the cache. The zip is written by the standard library's `zipfile` into a non-seekable stream (data descriptors), so the response starts with the first track. Range requests are not offered for the zip. A track whose copy fails is delivered untagged; when the tagger is unavailable the POST answers `tagged: false` with the notice, and the client shows it.

Alternative considered: an export job that builds the zip on disk. Rejected: it doubles the disk use of an album and makes the user wait for the whole archive.

### WAV and AIFF

mutagen stores ID3 tags in a chunk of WAV (`id3 `) and AIFF (`ID3 `) files; the tagger handles them with the ID3 family it uses for MP3. This also enables tag writes into referenced WAV/AIFF files.

### Covers

Covers are not stored yet (change `covers`). Copies carry all context tags except the cover; `covers` adds it to `context_tags` and thereby to transcodes and downloads.

### Progressive loading

Not affected: no list or protocol change. Media stays on HTTP.

## Risks / Trade-offs

- [Album download fills the cache with copies of large lossless files] → copies count against the shared limit and are evicted first by LRU; a zip/album export can stream copies and drop them after delivery (decided when export is specified).
- [Tagger unavailable] → downloads fall back to the untagged original with a notice; playback is unaffected because it never calls the tagger.

## Migration Plan

No schema change: `transcode_cache` already has `kind` and an optional bitrate.
