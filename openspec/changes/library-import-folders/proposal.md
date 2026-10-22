# Proposal

## Why

The library can be browsed and identified, but it can only be filled by the test generator. Most users start with an existing collection on their server or NAS. `library-import` specifies the import, and `managed-and-referenced-originals` waits for it (import modes 4.1/4.2, adoption 5.1). This change implements the first and most common source: folders on the server.

## What Changes

- **Import folders:** admins import a folder below the import roots configured for the installation (`ANTHOLOGY_IMPORT_ROOTS`, default `/data/imports`); other paths are refused.
- **Storage modes:** reference, move, link (reflink when the file system supports it, otherwise hardlink) and copy, with the most economical possible mode as default. Move, copy and reflink yield managed originals in `_originals/`, reference and hardlink yield referenced originals (tasks 4.1 of `managed-and-referenced-originals`). Moving across file systems and copying verify a checksum before a source file is removed.
- **Scan and dry-run report:** a scan job registers the files and classifies them – new, already present, duplicate within source, broken – with counts and storage impact; nothing is moved, linked or copied before the admin confirms. The report states whether the chosen mode yields managed or referenced originals (task 4.2 of `managed-and-referenced-originals`).
- **Staged duplicate detection:** path, size and modification time; audio-data hash (tags excluded); ISRC and MusicBrainz IDs from the tags; acoustic fingerprints only for still unmatched candidates (same artist and title within ±2 s), compared locally. Occurrences of a recording already present or found twice become track contexts, not second files.
- **Library entries from tags:** artists, releases, recordings and track contexts are created from the existing tags through the library service, with fallbacks (folder name as album, file name as title); tags of referenced files are never written unless tag writing is allowed for the import.
- **Repeat imports** of the same folder process only new or changed files; scan and import are resumable jobs at background priority. After an import, the identification job of `recording-identification` checks the new recordings.
- **Adopting referenced originals** (task 5.1 of `managed-and-referenced-originals`): admins move, copy or reflink referenced files of a folder into managed storage after confirmation; each file is verified by checksum before anything changes at the source.
- **Client:** "Import folder" on the Streaming page for admins – folder choice, mode, report with confirmation, live progress through the jobs view; adoption in the library settings.
- **Not part of this change:** report categories "replaces lower quality" and "suspicious quality" (need `quality-analysis`), review list entries for "needs review" (need `review-list`; the report counts them), PC folders and uploads (desktop client, milestone 3), iTunes, beets, other music servers, playlists, ratings and play counts (`personal-data`), album folder trees with links.

## Capabilities

### New Capabilities

_None._

### Modified Capabilities

- `library-import`: import roots and admin rights, report details and confirmation, verified transfers, library entries from tags, repeat imports. The existing requirements stay; categories that need quality analysis or the review list remain open tasks.
- `library`: adopting referenced originals is implemented as specified by `managed-and-referenced-originals` (no new requirement).

## Impact

- **Domains:** library-import (new server module `library_import`, client feature `library-import`), library (service for entries, guard for adoption), jobs (three job types), metadata-lookup and identification (run after an import).
- **Data model and migration:** `LibraryImport` (status, root, report, creator, tag-write opt-in) and `ImportItem` (path, size, mtime, audio hash, tags, result, matched recording) as in the data model; `audio_files.content_hash` for transfer verification. One Alembic migration; `docs/architecture/data-model.puml` updated.
- **Dependencies:** `tinytag` (MIT) for fast tag reading in the core; FFmpeg build gains the `hash` muxer (ADR 0020 rule).
- **Deployment and docs:** `ANTHOLOGY_IMPORT_ROOTS`; `docs/install.md` explains which mounts allow linking; `server/AGENTS.md`.
- **Non-functional requirements (2 s, 500,000 tracks):** scan and import are background jobs in batches; the UI shows counts from the import's maintained report and job progress. A scan of 500,000 files reads every file's tags and audio hash once; repeat scans skip unchanged files by path, size and modification time.
