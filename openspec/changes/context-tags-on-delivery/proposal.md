# Proposal

## Why

ADR 0008 delivers originals with a generated tag header in front of the audio data, while the sync-protocol spec requires media over HTTP range requests. A prepended header shifts every byte offset, and for Ogg/Opus and M4A/ALAC it is not even a pure prefix (page renumbering, `stco` offsets). Playback does not need embedded context tags at all – own clients get metadata from the API and Raumfeld from DIDL-Lite – so the header only matters when a file leaves Anthology.

## What Changes

- Playback streams SHALL deliver the active original byte-identical, with plain range requests; context metadata comes from the API or DIDL-Lite only.
- Downloads and exports of originals SHALL deliver a copy tagged for exactly one context, produced by the tagger service and kept in a shared, size-limited cache like transcodes; range requests are served from that copy.
- Tagged copies SHALL be invalidated when the context's tags or the original change.
- The "generated tag header" approach is dropped from ADR 0008 and from the tagger interface draft (**BREAKING** for the ADR wording only; nothing is implemented).

## Capabilities

### New Capabilities

_None._

### Modified Capabilities

- `library`: new requirements for unchanged originals in playback streams and for context-tagged downloads with a cache.

## Impact

- **Domains:** library. transcoding and sync-protocol are referenced, not changed (cache behavior mirrors the transcode cache; media stays on HTTP range requests).
- **Data model:** `TranscodeCacheEntry` gets a `kind` (`TRANSCODE`, `TAGGED_COPY`) and an optional bitrate, so both variants share one cache and one size limit. Migration only once the schema exists.
- **Services:** `services/tagger` interface draft replaces `POST /v1/header/build` with `POST /v1/tags/copy` (write context tags into a new file, leave the source untouched).
- **Docs:** ADR 0008, `docs/architecture/data-model.puml`, `services/tagger/README.md`.
- **Non-functional requirements (2 s, 500,000 tracks):** none. Playback gets cheaper (no header generation); a first download of a context costs one file copy.
