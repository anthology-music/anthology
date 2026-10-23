# ADR 0021: Replaced managed originals are deleted or kept per run

- Status: Accepted
- Date: 2026-10-23

## Context

When a better file of a recording arrives (import, later downloads and CD rips), it becomes the active original (spec: library, Quality-based replacement). A replaced **referenced** original is never touched: it is marked superseded and listed in a report (ADR 0008, change `managed-and-referenced-originals`). For a replaced **managed** original Anthology owns the bytes, but `AGENTS.md` allows deleting an original only after checksum verification and with an explicit rule or confirmation.

Users work differently. Some want a lean library without old files. Others want to compare the old and the new file, or keep the old one until they have listened to the new one.

## Decision

- Every run that can replace originals has an option **"delete replaced managed originals"**. A run is a folder import now; later also a download or CD import. The option is **on by default** and applies to all replacements of that run.
- **On:** after the new original is in place, its checksum is verified against the stored content hash, and only then is the old managed file deleted together with its database entry. If the verification fails, the old file is kept as superseded.
- **Off:** the old managed file is kept, marked superseded and listed in the report of superseded files, next to superseded referenced files. Admins delete superseded managed files later from the report after a confirmation, again with the replacement's checksum verified first.
- Referenced originals are never deleted, whatever the option says.

## Consequences

- The superseded state applies to managed files too. The file operation guard allows exactly one operation on a superseded managed file: deletion, by the replacement step or by the admin action of the report.
- The import dialog and the report show the option and what it means for the run.
- Counters and the report distinguish superseded managed files (deletable) from superseded referenced ones (never deleted).
