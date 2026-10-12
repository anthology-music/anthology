# Design

## Context

ADR 0004 moves mutagen into its own GPL service; `services/tagger/README.md` drafts interface v1 (read, write with `atomic | in_place`, copy, health). ADR 0008 defines managed and referenced originals; hardlinked files count as referenced. Changes `tag-editing`, `context-tags-on-delivery` and `covers` rely on the tagger. Quadlet and Compose already run `anthology-tagger` in the pod with the library, cache and imports volumes. See proposal.md for the motivation.

## Goals / Non-Goals

**Goals:**
- A small, stateless service that reads and writes tags of the common formats safely.
- An interface that does not change when covers and caches later move to S3.

**Non-Goals:**
- Core client, availability detection and write queue (6b and `tag-editing`).
- Image publishing and the `BlobStore` implementation (change `covers`).
- WAV/AIFF/APE/WavPack (later, when import needs them).

## Decisions

### Service shape

Python 3.12 with uv, FastAPI and uvicorn (MIT/BSD, inside the GPL container). Endpoints are synchronous functions: mutagen does blocking file I/O, FastAPI runs them in its thread pool. Batches of up to 200 files per request (configurable); the response always has one result per requested file, in request order, with `ok` or an error code (`not_found`, `forbidden_path`, `unsupported_format`, `corrupt`, `hardlinked`, `write_failed`). A failing file never fails the batch.

### Neutral tag fields

One typed field set for all formats (`docs/architecture/tagger-api.md`): titles and names, numbers, dates, multi-valued genres, composers and artists, label, catalog number, ISRC, barcode, comment, compilation flag and MusicBrainz IDs. The mapping per format follows MusicBrainz Picard, so files stay readable by other players and by Picard. Reading may also return the raw native keys (`include_raw`) for import diagnostics.

Write semantics: fields omitted in the request stay unchanged; `null` removes a field; `replace_all: true` removes every tag (including unknown ones) first – used for the neutral base tags of managed originals. `images` omitted keeps them, `[]` removes them, a list replaces them.

### Write modes

- **atomic** – copy to a temp file in the same directory, write tags, fsync, `rename` over the original, fsync the directory. A crash leaves either the old or the new file. Because rename breaks hardlinks, atomic writes are refused for files with a link count above one (`hardlinked`); ADR 0008 treats such files as referenced anyway.
- **in_place** – keeps the inode (and so the hardlinks). A backup copy is written to a journal directory in the cache volume first and recorded; then mutagen writes into the file; the journal entry is removed after a successful re-read. On start the service restores every file with a leftover journal entry from its backup (copying the bytes into the same inode). A crash therefore leaves the old or the new state, never a partial one.

Writes to the same path are serialized inside the process; the core sends at most one write per file at a time (write queue in `tag-editing`).

### Path restriction

Every path is resolved (symlinks followed) and must lie below one of the configured roots (`ANTHOLOGY_TAGGER_ROOTS`, default `/data/library,/data/cache,/data/imports`); copy targets, image staging and the journal must lie below the cache root. Referenced libraries outside these volumes are added as further roots by mounting them into both containers.

### Images and the BlobStore (ADR 0019)

The tagger never talks to a storage backend. `read` returns image descriptors (picture type, MIME, size, width, height, SHA-256); with `extract_images_to` it stores each image as `<sha256>.<ext>` in that staging directory (skipping existing ones). The core moves them into its `BlobStore`. For writes and copies the core provides images as files in the staging directory. Image dimensions come from Pillow.

### Copies

`copy` reads the source read-only, writes to a temp file next to the target, applies the complete tags (`replace_all`) and images, fsyncs and renames. The source's checksum is unchanged; this works for referenced and even superseded files.

### Versioning

Interface version `1.0` in `/v1/health`; additive changes raise the minor version, breaking ones the path (`/v2`). The core (6b) accepts major version 1.

### Tests

Fixtures are generated with FFmpeg (sine tones, a few hundred milliseconds, all five formats) once per test session; images are generated with Pillow. Crash safety is tested by killing a subprocess in the middle of a write.

## Risks / Trade-offs

- [In-place writes need a full backup copy per file] → only for referenced files with tag writing enabled; backups are deleted on success.
- [Album folders hardlinked to managed originals would break atomic writes] → refused with `hardlinked`; the library change decides that album folders of managed originals use symlinks or reflinks.
- [Field mapping differences between players] → follow Picard; raw keys available for diagnostics.
- [Large images inflate staging] → staging is part of the cache volume; the core moves or deletes files after import.

## Migration Plan

New service, nothing deployed. Images are published in step 7 (`pod-and-ci`).

## Open Questions

None.
