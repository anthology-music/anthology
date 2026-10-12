# Proposal

## Why

The core may not import mutagen (GPL-2.0-or-later, ADR 0004), yet reading full tags, embedded covers and writing tags into files is needed from milestone 2 on (library import, tag editing, tagged downloads). Step 6a of milestone 1 builds the tagger service itself; step 6b adds the core client.

Discussing where extracted covers go also raised the storage question: object storage (S3) is the natural home for binary tag data such as covers, but not for originals. The decision is recorded now so that the tagger's interface fits it from the start.

## What Changes

- **Tagger service** in `services/tagger` (GPL-2.0-or-later, own container, port 8410), interface v1:
  - `POST /v1/tags/read` – batched; per file: format, audio properties, neutral tag fields, embedded image descriptors (MIME, size, dimensions, content hash); optionally stores the images by content hash in a staging directory.
  - `POST /v1/tags/write` – batched; `mode: atomic` (temp file, fsync, rename; refused for hardlinked files) or `mode: in_place` (keeps hardlinks; journaled backup restored after a crash).
  - `POST /v1/tags/copy` – tagged copy into the cache; the source is opened read-only.
  - `GET /v1/health` – status, service version, interface version, supported formats.
  - Formats: FLAC, MP3, MP4/M4A (AAC, ALAC), Ogg Vorbis, Opus. Only paths below configured roots (the shared volumes) are accepted.
- **Interface document** `docs/architecture/tagger-api.md` with the neutral field set and its mapping per format (following MusicBrainz Picard).
- **ADR 0019:** originals stay on a file system; binary tag data (covers and other images) and caches (transcodes, tagged copies, thumbnails) are stored behind a `BlobStore` interface – file system by default, S3-compatible as an optional adapter later (roadmap).
- The requirement "Tagger service interface" moves from change `tag-editing` into this change (with refined scenarios); `tag-editing` task 3.2 is covered here.
- CI workflow for the tagger (lint, tests with generated media).

## Capabilities

### New Capabilities

_None._ (`tagging` is introduced by change `tag-editing`; this change adds its first requirements.)

### Modified Capabilities

- `tagging`: tagger service interface, safe writes, path restriction, embedded images via a staging directory, read-only copies.

## Impact

- **Domains:** `tagging` (spec); referenced: `library` (storage modes, ADR 0008), `covers`, `transcoding`.
- **Code:** new `services/tagger/` (Python, uv, FastAPI, mutagen, Pillow); no code in `server/` or `client/` (core client follows in 6b).
- **Data model:** `Image.path` and `TranscodeCacheEntry.path` become `blobKey` (documentation only; no tables exist yet, no migration).
- **Docs:** ADR 0019, `docs/architecture/tagger-api.md`, `services/tagger/README.md`, `docs/roadmap.md` (S3 adapter), change `tag-editing`.
- **Licenses:** mutagen (GPL-2.0-or-later) and Pillow (MIT-CMU) only inside the GPL tagger container; the core stays MIT.
- **Non-functional requirements:** none directly; batching keeps imports of 500,000 tracks to a few thousand requests.
