# Importing a collection

Admins import folders from the server: **Streaming › Import folder**. Only folders below the import roots (`ANTHOLOGY_IMPORT_ROOTS`, default `/data/imports`) can be chosen.

<Screenshot name="import-dialog" alt="The dialog to choose a folder to import" />

## How an import runs

1. **Choose a folder** and the storage mode, then start the scan.
2. Anthology **scans and analyses** every file: tags, technical data and an audio fingerprint. Nothing is moved or changed yet.
3. You get a **report**: new tracks, duplicates of tracks you already have, better or worse copies, files that need a decision.
4. **Confirm** the report. Only now are the files stored and the library entries created. Anthology then identifies the recordings and fetches covers.

You can close the app while an import runs; it continues on the server, and its progress is shown live.

## Storage modes

| Mode | What happens |
|---|---|
| reference | the files stay where they are; Anthology never moves, renames or deletes them |
| link | a second name (hardlink) or a copy-on-write clone (reflink) in the library – no extra space; needs the folder on the same mount as the library |
| move | the files move into the library (across mounts: copied, verified by checksum, then removed) |
| copy | the files are copied and verified; the source stays unchanged |

The import proposes the most economical mode the mounts allow. Referenced files can later be adopted into managed storage in Settings.

## Duplicates and quality

When a file is a recording you already have, the import compares the **effective quality** of both: a genuinely better copy can replace the existing original, the worse one is skipped. Unclear cases go to the review list.
