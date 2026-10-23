# Design

## Context

The library service creates artists, releases, recordings and track contexts with sort keys, counters and change entries; audio files carry storage mode, original status and a file operation guard (`check_file_operation`); `recording-identification` provides fingerprints (FFmpeg with Chromaprint, ADR 0020) and the identification job; the job system runs resumable items. The pod mounts the volumes `library` (`/data/library`) and `imports` (`/data/imports`) into the server. See proposal.md for the motivation.

## Goals / Non-Goals

**Goals:**
- Import a 500,000-file folder unattended, resumable, without blocking the UI, and repeat it cheaply.
- Never lose or change a user's file unexpectedly: report first, verified transfers, guard for referenced files.

**Non-Goals:**
- Quality comparison of duplicates (effective quality) and review list entries.
- Album folder trees with links; FUSE view.
- Watching import folders for changes (`FileLocation.watched`).

## Decisions

### Module, entities and flow

New domain module `server/anthology/library_import/` (models, service, api, streams, jobs). Entities as in the data model: `LibraryImport` (id, source path, root, mode – `reference`, `move`, `reflink`, `hardlink` or `copy` –, same mount, allow tag writes, status, report JSON, current job, created by, timestamps) and `ImportItem` (import, path, size, mtime in ns, audio hash, tags JSON, artist/title/group keys, duration, ISRC, MusicBrainz ID, fingerprint, result, note, matched recording, duplicate of, planned recording ID, content hash, created audio file, release, applied at, failed).

Status flow: `scanning` → `reported` → (`importing` → `done`) or `cancelled`; `failed` on errors. Jobs:

1. `library_import_scan` – item 1 walks the folder (`os.scandir` in a thread, keyset by path, commits every 1,000 entries; idempotent by `(import, path)`), then creates `library_import_analyze` with one item per 200 files.
2. `library_import_analyze` – per file: tags and technical data (tinytag), audio hash (FFmpeg), classification; the last finished item computes the report and sets `reported`.
3. `library_import_apply` – after confirmation, one item per 200 files in path order; finally starts the identification job (unless one is running; the next run then covers the recordings).

Job items are created with their batch boundaries in the job parameters, like the identification job.

### Classification stages (spec: Staged duplicate detection)

1. **Unchanged:** same path, size and modification time as an item of an earlier finished import → `skipped` (repeat imports); the file is not read.
2. **Broken:** tinytag cannot read the file or FFmpeg cannot hash its audio.
3. **Audio hash:** `ffmpeg -i <file> -map 0:a:0 -c:a copy -f hash -hash sha256 -` hashes the audio packets without tags. Equal to an existing original → `already_present`; equal to an earlier item of this import → `duplicate_in_source`.
4. **Identifiers:** ISRC or MusicBrainz recording ID from the tags equal to an existing recording or an earlier item → `already_present` / `duplicate_in_source`.
5. **Fingerprint candidates:** still unmatched files whose normalized artist and title equal another file's or recording's within ±2 s; their Chromaprint fingerprints are compared locally: the stored compressed fingerprints are decoded to their 32-bit items and compared bit by bit at the best alignment within ±16 items (similarity ≥ 0.85). Match → `already_present` / `duplicate_in_source`; no match → `new`. Fingerprints of candidates are stored on the item (and on the original of a library recording), computed once.

`already_present` and `duplicate_in_source` items keep the matched recording; applying them adds a track context when their album differs from the recording's existing contexts. Quality is not compared here (open task for `quality-analysis`). "Needs review" is the result of a match whose title differs (e.g. same audio hash, different titles); such a file becomes a track context like a duplicate and a review entry later.

### Storage modes and transfers

Possible modes are probed in the import folder against `<library>/_originals`: `os.stat().st_dev` equality and a test `link()` for hardlinks, `ioctl(FICLONE)` on a probe file for reflinks; `EXDEV` means separate mounts. Default: reflink, else hardlink, else copy (spec: Default storage mode). In the standard pod `imports` is its own volume, so copy is the default; `docs/install.md` explains how to mount a collection below `/data/library` to allow linking.

Targets of managed originals: `<library>/_originals/<first two hex digits of the recording ID>/<recording ID>.<ext>`. Transfers write to a temporary name in the target folder, verify (SHA-256 of the whole file against the source) and rename; `move` within one mount is a rename, across mounts copy + verify + remove the source. Referenced files keep their path; hardlinks are created at the managed target name but stay `referenced`. Every write goes through `check_file_operation`.

### Library entries from tags

The apply job groups files by (album artist if tagged, album, album folder), where a disc folder (`CD 2`, `Disc 2`) counts as its parent folder and gives the disc number; a group without album artist whose files name several artists gets "Various Artists". Releases are found by group across imports, so a repeat import adds new files to the existing release. One release per group with disc and track numbers from the tags, falling back to file order. Artists via `get_or_create_artist`, recordings with ISRC and MusicBrainz IDs from the tags (the identification job verifies them later), audio file with `storage_mode` and `tag_writes_allowed` from the import. Tags are stored on the item (`tags_json`) for later tagging work; files are never written during import.

### Adoption (managed-and-referenced-originals 5.1)

Job `adopt_originals` for the referenced active originals below a folder (or all), mode move, copy or reflink (never hardlink). `check_file_operation` gains `FileOperation.ADOPT`, allowed only for active referenced files and only from this job. Per file: transfer to the managed target, verify, flip `storage_mode` to managed, then (move only) remove the source; checksum mismatch → item failed, file stays referenced. The settings show the number and size of referenced originals and start adoption after a confirmation dialog.

### API, stream and client

- `GET /api/v1/library-import/folders?path=` – subdirectories below the roots (admins), with the possible modes for the chosen folder.
- `POST /api/v1/library-imports` (path, mode, allow tag writes) → scan; `POST …/{id}/confirm`, `POST …/{id}/cancel`.
- `POST /api/v1/library/adoption` (folder, mode: move, copy or reflink).
- Stream `library.storage` (admins): one row with the number and size of active referenced originals (maintained counters), for the settings.
- Stream `library_import.imports` (admins): one row per import with status, mode, counts and sizes per category; deltas whenever the report or status changes.
- Client: Streaming page button "Import folder" (admins) → dialog (folder browser, mode with explanation managed/referenced, tag-write opt-in for referenced modes) → import row with report, "Import"/"Cancel"; progress through the existing jobs view. Adoption in Settings › Library.

### Dependencies and FFmpeg

`tinytag` (MIT) in the server. The FFmpeg build adds the `hash` muxer (ADR 0020: additions in the change that needs them). Settings: `ANTHOLOGY_IMPORT_ROOTS` (default `<data_dir>/imports`) and `ANTHOLOGY_LIBRARY_DIR` (default `<data_dir>/library`).

### Progressive loading

Folder listing returns one directory level. The imports stream has one row per import (few). Scans and imports work in keyset batches; reports are stored, not computed on request.

## Risks / Trade-offs

- [Reading 500,000 files takes hours] → background jobs, resumable, throttled by the global throttle; repeat scans skip unchanged files.
- [Hash collisions of audio packets across containers (same audio in FLAC vs. WAV differs)] → different encodings are found by identifiers or fingerprints, not by the hash; the hash only finds byte-identical audio.
- [Tags of large collections are inconsistent (album artist missing, compilations)] → grouping by folder as part of the key keeps albums together; later corrections through tagging.
- [Cross-device move fails half-way] → temporary name, verification, source removed last; a repeated item finds the verified target and only removes the source.

## Migration Plan

One Alembic migration: `library_imports`, `import_items`, `audio_files.content_hash`, a partial index of active referenced originals by path (adoption) and the counters `referenced_files`/`referenced_bytes`, filled from existing rows. Rollback drops the tables and the column.

## Open Questions

- Default throttle for imports vs. identification running at the same time – both use the global throttle for now.
