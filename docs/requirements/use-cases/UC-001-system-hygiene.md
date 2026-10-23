# UC-001: System hygiene of the library storage

- **Goal:** the managed storage contains only files the library refers to. Files the library lost track of are found and removed, and missing files are reported, without endangering any original.
- **Primary actor:** the system (scheduled maintenance).
- **Supporting actor:** an admin, who configures the maintenance and reads its results (see US-001).
- **Scope:** the managed storage `<library>/_originals`. Referenced files outside it are never touched.

## Background

Several steps write or remove a file and change the database in separate steps: a transfer, a replacement that deletes the old managed original (ADR 0021), the deletion of superseded files, adoption. A crash between those steps can leave:

- **Orphaned files:** a file in `_originals` that no audio file refers to, e.g. the old managed original whose database entry was deleted while the file removal did not happen.
- **Leftovers:** temporary files of interrupted transfers (`.<name>.part`) and link probes (`.probe-<id>`).
- **Missing originals:** an audio file entry whose managed file no longer exists (a disk problem or a manual deletion). The library cannot fix these without the user.

## Preconditions

- The installation runs; maintenance is enabled with a schedule (default: daily at night).
- The library storage is mounted.

## Trigger

The scheduled time is reached. An admin may also start a run manually.

## Main flow

1. The system starts the maintenance run as a background job at background priority. Only one run is active at a time, also with several server processes.
2. The system walks `_originals` in batches and, for every file, checks whether an audio file entry refers to its path.
3. Files without an entry that are older than the grace period are classified:
   - leftovers (`.part`, `.probe-…`) and
   - orphaned files.
   Younger files are skipped: a running import may still write them.
4. The system walks the managed audio file entries in batches and checks that each file exists. Missing ones are classified as missing originals.
5. Depending on the configured action:
   - **"delete":** the system deletes leftovers and orphaned files;
   - **"report only":** it only lists them.
   It never deletes or changes an audio file entry.
6. The system stores the result of the run: when it ran, counts and sizes per class, deleted files, and the files still listed. It shows the result to admins.

## Alternative flows

- **A1 – Run already active:** a scheduled or manual start while a run is active does not start a second run.
- **A2 – Storage not available:** if `_originals` cannot be read, the run fails without deleting anything, and the result says why.
- **A3 – Import, adoption or deletion job running:** the grace period protects their files. The run continues.
- **A4 – Interrupted run:** the job continues after a process failure like every job; files already handled are not handled twice.
- **A5 – Unexpected amount:** if a run would delete more files than the safety limit, it only reports, and an admin must confirm the deletion from the result. The limit is a share of the managed files (default 1 %, at least 10 files) and can be switched off. Many orphans at once usually mean an error, e.g. a database restored from an older backup: the newer originals look orphaned but are the only copies.

## Postconditions

- **Success:** no leftovers or orphaned files older than the grace period remain (action "delete") or all are listed (action "report only"). Missing originals are listed, and the result is visible to admins.
- **Guarantee:** no file outside `_originals` and no file referred to by an audio file entry is deleted.

## Derived requirements

Change `system-maintenance`:

- `jobs` – Scheduled maintenance
- `jobs` – Maintenance configuration
- `library` – Orphaned files in managed storage
- `library` – Maintenance safety limit
- `library` – Missing originals
- `library` – Maintenance result
