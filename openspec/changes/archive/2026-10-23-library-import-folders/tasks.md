# Tasks

## 1. Foundations

- [x] 1.1 Add `tinytag` (MIT) to the server, the `hash` muxer to the FFmpeg build stage, and `ANTHOLOGY_IMPORT_ROOTS`/library directory settings (compose, Quadlet, `docs/install.md` with the mount advice for linking); verify the image build check and `THIRD_PARTY_LICENSES.md`
- [x] 1.2 Migration and models `library_imports`, `import_items`, `audio_files.content_hash`; update `docs/architecture/data-model.puml`; verify with the migration round-trip and model comparison tests on SQLite and PostgreSQL
- [x] 1.3 Path safety: resolve requested folders below the import roots (no `..`, no symlink escape) and the folder listing endpoint for admins; verify with tests for allowed, escaping and symlinked paths and for roles

## 2. Storage

- [x] 2.1 Probe possible modes (reflink via FICLONE, hardlink on the same mount, copy, reference) and the default; verify with tests on temporary file systems for same mount and separate mount (EXDEV simulated) – task 4.1 of `managed-and-referenced-originals`
- [x] 2.2 Verified transfers to `_originals/<xx>/<recording>.<ext>` (temporary name, SHA-256 verification, rename; move across mounts removes the source last; hardlink stays referenced); verify with tests for each mode, a checksum mismatch and a repeated item after an interrupted move

## 3. Scan and report

- [x] 3.1 Job `library_import_scan` (resumable walk, items registered idempotently) and `library_import_analyze` (tags via tinytag, audio hash via FFmpeg, broken files); verify with generated files (tagged WAV/FLAC from sine tones, a broken file, a symlink loop)
- [x] 3.2 Classification stages (unchanged, broken, audio hash, identifiers, fingerprint candidates compared locally) and the report with counts, sizes, storage impact and managed/referenced statement; verify with tests for each category, the same song in three folders and a repeat import that skips unchanged files – task 4.2 of `managed-and-referenced-originals`
- [x] 3.3 REST: start, confirm, cancel; stream `library_import.imports`; verify with API tests (roles, confirmation only for `reported`, cancel leaves the library unchanged) and a protocol test (report delta)

## 4. Import

- [x] 4.1 Job `library_import_apply`: library entries from tags with the fallbacks of the spec, grouping into releases, track contexts for already present and duplicate items, audio files with storage mode and tag-write opt-in; start identification afterwards; verify with tests for an album, untagged files, a compilation spread over folders and the identification start
- [x] 4.2 End-to-end test on PostgreSQL and SQLite: scan → report → confirm → library lists show the albums; the source files are unchanged in mode reference and copy

## 5. Adoption

- [x] 5.1 `FileOperation.ADOPT`, job `adopt_originals` (move, copy, reflink; never hardlink) with checksum verification before any change at the source and per-item failures, REST endpoint for admins; verify with tests for success, checksum mismatch and refused hardlink mode – task 5.1 of `managed-and-referenced-originals`

## 6. Client

- [x] 6.1 Streaming page: "Import folder" dialog (folder browser, modes with managed/referenced explanation, tag-write opt-in) and import rows with report, confirm and cancel; texts de/en; verify with client tests (report renders from the stream, confirm and cancel call the API, link mode hidden when impossible)
- [x] 6.2 Settings › Library: referenced originals (count, size) and adoption with confirmation dialog; verify with a client test
- [x] 6.3 E2E test: import a generated folder in the pod-like test server and browse the new album

## 7. Deferred

- [x] 7.1 (waits for `quality-analysis`, done with `quality-based-replacement`) Report categories "replaces lower quality" and "suspicious quality"; replacement on import
- [x] 7.2 (done with `review-list`) Review entries for "needs review" items

## 8. Documentation

- [x] 8.1 Update `server/AGENTS.md`, `docs/agent-notes.md`, the sync protocol stream table and tick tasks 4.1, 4.2 and 5.1 of `managed-and-referenced-originals`; verify the files
