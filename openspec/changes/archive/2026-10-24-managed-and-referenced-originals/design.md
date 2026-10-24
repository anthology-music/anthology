# Design

## Context

ADR 0008 and the library spec describe originals stored under `_originals/` with neutral base tags. library-import adds a reference mode and a hardlink mode in which the file is shared with a folder Anthology does not own. The data model already has `AudioFile.storageMode` (`MANAGED`, `REFERENCED`, `LINKED`) and models the original as `Recording "1" -- "0..1" AudioFile`, which cannot represent a kept, replaced file. No server code exists yet. See proposal.md for the motivation.

## Goals / Non-Goals

**Goals:**
- One unambiguous rule for when Anthology may write a file.
- Keep exactly one active original per recording while never touching foreign files.
- Make the rule visible in the data model and ADR 0008.

**Non-Goals:**
- How context tags are delivered for downloads and range requests (separate topic: tag header vs. range requests).
- Automatic cleanup of superseded files; Anthology only reports them.
- Watching referenced folders for external changes (already covered by `FileLocation.watched`; behavior unchanged).

## Decisions

### Writability decides the storage mode, not the location

`StorageMode` is reduced to two values with a precise meaning:

- `MANAGED` – Anthology owns the bytes: files written by Anthology, moved or copied in, or reflinked (copy-on-write, so later writes never reach the source).
- `REFERENCED` – the bytes are shared with or located in a place Anthology does not own: reference mode and hardlinks. Never moved, renamed or deleted; written only with the user's opt-in (see below).

`LINKED` is removed. A hardlink shares the inode with the user's folder, so writing base tags in place would change the user's file, and writing via temp file plus rename would silently break the link and double the space. Treating hardlinks as referenced avoids both.

Alternative considered: keep `LINKED` as a third mode with "write by rename" semantics. Rejected: it hides a storage cost and makes the write rule depend on a third case.

### Opt-in tag writing for referenced originals

library-import already lets the user allow tag writes for referenced files. The opt-in is chosen per import (`LibraryImport.allowTagWrites`) and copied to each resulting file (`AudioFile.tagWritesAllowed`, only meaningful for `REFERENCED`), so it can later be changed per file or folder. With the opt-in, Anthology writes the complete tags of the file's home context (the track context it was imported with), because the user wants that folder usable by other players; it still never moves, renames or deletes the file. For hardlinked files this deliberately changes the user's file as well – that is what the opt-in means. Superseded files are never written.

### Original status on the audio file

`AudioFile` gets `originalStatus : OriginalStatus` (`ACTIVE`, `SUPERSEDED`). The relation becomes `Recording "1" -- "0..*" AudioFile`, with a partial unique index guaranteeing at most one `ACTIVE` file per recording. Only referenced files can become `SUPERSEDED`; a replaced managed original is deleted after checksum verification of its successor, as today.

Alternative considered: a separate `SupersededFile` table. Rejected: the file keeps its quality analysis, location and source; moving rows between tables would duplicate those relations.

### Adoption is a job

Adopting referenced files (move, copy or reflink into `_originals/`) runs as a library job with progress, uses the existing checksum verification before any source file is removed, and flips `storageMode` to `MANAGED` per item. Hardlinking is not offered for adoption because it would not change ownership of the bytes.

### Progressive loading

Nothing changes in the protocol. List queries filter on `originalStatus = ACTIVE` through the partial index, so keyset pagination stays index-only. The superseded report is a normal subscription with `snapshot_meta` count first and keyset-paged rows.

## Risks / Trade-offs

- [Users expect "link" to save space and still get base-tag writes] → The dry-run report states whether originals will be managed or referenced; the import UI explains the hardlink limitation and suggests reflink-capable file systems (Btrfs, XFS).
- [Superseded files accumulate and use space] → Report shows total size; cleanup stays a manual user action outside Anthology.
- [Referenced files change or disappear outside Anthology] → Existing watched-location handling detects it; out of scope here.

## Migration Plan

No schema or data exist yet. The first Alembic migration of the library module creates `storage_mode` with two values and `original_status` with the partial unique index. No rollback needed.
