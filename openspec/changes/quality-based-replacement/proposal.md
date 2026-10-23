# Proposal

## Why

The library can import collections and knows the effective quality of analysed files, but a better file of an existing recording is still only counted as "already present". The library spec requires quality-based replacement. The import report lacks the categories "replaces lower quality" and "suspicious quality" (`library-import-folders` 7.1). A managed original cannot be replaced at all yet. The maintainer decided how replaced managed originals and quality checks on acquisition work (ADR 0021, ADR 0022).

## What Changes

- **Quality comparison of duplicate candidates (ADR 0022):** during the scan, only files matched to an existing recording or to another file of the source by identifiers or fingerprint are analysed. The existing original is analysed too unless it has a result. Files with equal audio hash are the same audio and need no comparison.
- **Report categories:**
  - **"replaces lower quality":** the new file's effective quality is higher than the existing original's, both results conclusive.
  - **"suspicious quality":** a comparison was needed but at least one result is not conclusive. Nothing is replaced; the file becomes a track context, like "already present", and a review case later.
- **Best copy within the source:** among duplicates in the source, the file with the highest effective quality becomes the original, the others track contexts.
- **Replacement on import:**
  - The better file is stored in the import's mode and becomes the active original of the recording. Track contexts and references stay.
  - The old original is marked superseded.
  - Referenced originals stay untouched, as before.
- **Replaced managed originals per run (ADR 0021):**
  - New import option "delete replaced managed originals", on by default.
  - **On:** the old managed file is deleted after the new original's checksum is verified.
  - **Off:** it is kept, superseded, in the report.
- **Report of superseded files in the client:** in Settings, admins see superseded managed and referenced files with count and size. They delete superseded managed files after a confirmation (job, checksum of the replacement verified first). Referenced files are listed but never deleted.
- **No automatic analysis after imports (ADR 0022):** the analysis of all new files after an import is removed; the whole library is checked from the settings on request. This amends the open change `quality-analysis-core`.
- **Not part of this change:**
  - Review-list entries for "suspicious quality" (`review-list`).
  - Transcode cache invalidation (no transcodes exist yet).
  - Downloads and CD imports, which will use the same replacement step (`effective-quality-duplicate-checks`).

## Capabilities

### New Capabilities

_None._

### Modified Capabilities

- `library-import`: quality comparison of duplicate candidates, the two report categories, best copy within the source, replacement on import and the per-run deletion option.
- `library`: superseded managed originals, their deletion and the report in the client.
- `quality-analysis`: analysis on acquisition only for duplicate candidates, whole library on request.

## Impact

- **Domains:** library-import (classification, apply, dialog and report), library (replacement of managed originals, guard for superseded managed files, deletion job, superseded report view), quality-analysis (analysis of single files on request of the import, no automatic start).
- **Data model and migration:**
  - `ImportResult` gains `replaces_lower_quality` and `suspicious_quality`.
  - `LibraryImport.delete_replaced`.
  - Library counters for superseded managed files and bytes.
  - One Alembic migration; `data-model.puml` updated.
- **ADRs:** 0021 (replaced managed originals) and 0022 (quality checks on acquisition), ADR 0012 amended.
- **Non-functional requirements (2 s, 500,000 tracks):**
  - Only candidates are analysed, so a scan costs about 0.1–0.4 s extra per candidate pair, not per file.
  - The superseded report is an existing keyset stream.
  - Deletion runs as a job in batches.
