# Design

## Context

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

### Progressive loading

Not affected: no list or protocol change. Media stays on HTTP.

## Risks / Trade-offs

- [Album download fills the cache with copies of large lossless files] → copies count against the shared limit and are evicted first by LRU; a zip/album export can stream copies and drop them after delivery (decided when export is specified).
- [Tagger unavailable] → downloads fall back to the untagged original with a notice; playback is unaffected because it never calls the tagger.

## Migration Plan

Nothing deployed. Documentation updates only until the library and transcoding modules exist.
