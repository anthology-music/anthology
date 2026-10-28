# Proposal

## Why

ADR 0008 delivers originals with a generated tag header in front of the audio data, while the sync-protocol spec requires media over HTTP range requests. A prepended header shifts every byte offset, and for Ogg/Opus and M4A/ALAC it is not even a pure prefix (page renumbering, `stco` offsets). Playback does not need embedded context tags at all – own clients get metadata from the API and Raumfeld from DIDL-Lite – so the header only matters when a file leaves Anthology.

## What Changes

- Playback streams SHALL deliver the active original byte-identical, with plain range requests; context metadata comes from the API or DIDL-Lite only.
- Downloads and exports of originals SHALL deliver a copy tagged for exactly one context, produced by the tagger service and kept in a shared, size-limited cache like transcodes; range requests are served from that copy.
- Tagged copies SHALL be invalidated when the context's tags or the original change.
- A whole album SHALL be downloadable as one zip archive of tagged copies, streamed without filling the cache.
- When the tagger is unavailable, downloads SHALL deliver the untagged original and the client SHALL say so.
- The tagger SHALL also tag WAV and AIFF (ID3 chunk), so every format the library accepts can be tagged.
- Every signed-in user may download, like playing. Covers join the copies with change `covers`.
- The "generated tag header" approach is dropped from ADR 0008 and from the tagger interface draft (**BREAKING** for the ADR wording only; nothing is implemented).

## Capabilities

### New Capabilities

_None._

### Modified Capabilities

- `library`: new requirements for unchanged originals in playback streams, context-tagged downloads with a cache and album downloads.
- `tagging`: the tagger tags every audio format of the library, WAV and AIFF included.

## Impact

- **Domains:** library, tagging (tagger formats). transcoding and sync-protocol are referenced, not changed (cache behavior mirrors the transcode cache; media stays on HTTP range requests).
- **Data model:** `TranscodeCacheEntry` gets a `kind` (`TRANSCODE`, `TAGGED_COPY`) and an optional bitrate, so both variants share one cache and one size limit. Migration only once the schema exists.
- **Services:** `services/tagger` interface draft replaces `POST /v1/header/build` with `POST /v1/tags/copy` (write context tags into a new file, leave the source untouched).
- **Client:** "Download" in the track menu, "Download album" on the album page.
- **Docs:** ADR 0008, `docs/roadmap.md` (album export leaves the later list), `docs/architecture/data-model.puml`, `services/tagger/README.md`.
- **Non-functional requirements (2 s, 500,000 tracks):** none. Playback gets cheaper (no header generation); a first download of a context costs one file copy.
