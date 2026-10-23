# Design

## Context

What exists:
- **Import:** the folder import classifies files in path order (unchanged, broken, audio hash, identifiers, fingerprint candidates) and applies them in path order. Matches become track contexts.
- **Quality analysis:** `quality_analysis.analysis.analyze` classifies one file; results are stored per audio hash (`quality_analyses`) and applied to the files through `library.apply_quality`.
- **Replacement:** `library.replace_original` replaces only a referenced active original with a managed file. The old file becomes superseded, counted and listed in `library.superseded`.
- **Guard:** `check_file_operation` refuses every operation on superseded files.
- **Storage:** `library/storage.py` verifies transfers and `content_hash` holds the SHA-256 of managed files.

ADR 0021 and ADR 0022 set the rules.

## Goals / Non-Goals

**Goals:**
- Replace originals on import only on conclusive evidence, never lose a file without verification, and keep the scan fast.

**Non-Goals:**
- Review entries.
- Replacement for downloads and CD rips (they reuse the step later).
- Transcode cache invalidation.

## Decisions

### Quality ranking

`effective_rank(tier)`: hires_lossless 4 > cd_lossless 3 > lossy_high 2 > lossy_low 1.

A file is **better** only if:
- both results have high confidence and the new rank is higher; or
- the new result is high-confidence lossless and the existing file is a high-confidence "upscaled" result of a lower rank.

Equal ranks never replace (WAV and FLAC of equal resolution are equal, spec: Supported audio formats).

A comparison is **inconclusive** when either result is not high-confidence. Then the result is `suspicious_quality`.

### Classification during the scan

Stage 2 (audio hash) is unchanged: equal audio needs no quality comparison.

Stages 4 (identifiers) and 5 (fingerprints) produce a candidate match. Then the analysis compares qualities.

**Existing recording matched:**
1. Analyse the new file and, if it has no stored result, the existing active original. Both are stored per hash through `quality_analysis.service.store`, so files and the later manual check reuse them.
2. Classify:
   - new better → `replaces_lower_quality` (matched recording kept);
   - inconclusive → `suspicious_quality`;
   - otherwise → `already_present` (or `needs_review` for a differing title, as before).

**Earlier file of the source matched:**
1. Analyse both.
2. Classify:
   - the new file better → it becomes `new`, and the earlier one becomes `duplicate_in_source` of it, together with the earlier one's own duplicates (`duplicate_of_id` rewritten in one update). This is allowed because nothing is applied before the confirmation, and analysis items run in path order one at a time.
   - inconclusive → `suspicious_quality` of the earlier file;
   - otherwise → `duplicate_in_source`.

If the earlier file itself replaces a library original (`replaces_lower_quality`), the better of the two takes that role in the same way.

**Unreadable file:** if the analysis of a file fails (decode error), the comparison counts as inconclusive.

Cost: one analysis per candidate pair side, about 0.1–0.4 s, only for candidates (ADR 0022).

### Applying replacements

Import option `delete_replaced` (`LibraryImport`, default true), set in the start request and the dialog.

For a `replaces_lower_quality` item, the apply job:
1. Plans and transfers the file exactly like a new file: recording ID of the matched recording, managed name `_originals/<xx>/<recording>-<first 8 hex digits of the item ID>.<ext>` (deterministic, so a repeated item finds its target), so it does not collide with the old managed file of the same recording. Replacements always store the content hash, also in referenced modes, because deleting the old file verifies the new one.
2. Calls `library.replace_original(recording, audio)` in one transaction. The item gets `audio_file_id`, `release_id` and a track context on its own album if it is new there.
3. **If the old original was managed and `delete_replaced` is set:**
   - Verify the new file: SHA-256 equal to its content hash. Referenced new files get their content hash computed at this point.
   - Then `library.delete_superseded(old)`: guard `DELETE` allowed for superseded managed files; delete the row with its counters and change entries.
   - Then remove the file.
   - If the verification fails, the old file stays superseded and the item note says so.

`replace_original` is extended:
- The current active original may be managed. It becomes superseded, and counters distinguish managed and referenced: new counters `superseded_managed_files` and `superseded_managed_bytes`.
- The replacement may have any storage mode. A referenced replacement is allowed only when it comes from an import in a referenced mode. Acquisitions (downloads, rips) stay managed, which keeps the rule of `managed-and-referenced-originals` ("if the active original is referenced, the new file becomes managed") for acquisitions; that wording is narrowed accordingly.

The apply job runs in two phases: first the originals (`new`, `replaces_lower_quality`), then the track contexts. A context can then refer to an original later in the path order, which the best-copy rule produces.

The verification before a deletion checks the recording's current active original (exists, SHA-256 equal to its content hash), which also covers chains of replacements.

Deletion order: the file is removed after the database commit. A crash in between leaves an orphaned managed file in `_originals`, which is harmless. The scheduled maintenance of change `system-maintenance` (UC-001) finds and removes such orphans.

### Guard

`check_file_operation`:
- A superseded **managed** file allows only `DELETE`.
- A superseded **referenced** file still allows nothing.

### Report of superseded files and deletion job

The stream `library.superseded` already lists superseded files by path. Its rows gain `storage_mode`, and its counters the managed split.

Job `delete_superseded`:
- Started with `POST /api/v1/library/superseded/deletion` (admins). Covers all superseded managed files, batches of 200 by path.
- Per file: the replacement (`superseded_by`) must exist and match its content hash, then delete. A failed verification keeps the file and fails the item.

Client, Settings › Library:
- Section "Ersetzte Originale": counts and sizes (managed, referenced) and the list (VirtualList over the stream; path, title, size, mode).
- "Ersetzte verwaltete Dateien löschen" with a confirmation dialog.
- Referenced rows show that they are never deleted.

### Quality analysis on request only (ADR 0022)

- Remove the automatic start of `analyze_quality` after an import (`library_import` apply).
- The delta of `quality-analysis-core` ("the system SHALL also start it after an import that created originals" and its scenario) is amended in that change's spec file; this change adds the acquisition rule to `quality-analysis`.

### Report and dialog

- The report shows the two new categories, the number of originals that will be replaced, and the deletion option ("replaced managed originals are deleted" or "kept in the report").
- The dialog has the checkbox "Ersetzte verwaltete Originale löschen", checked by default.

## Risks / Trade-offs

- **Swapping the original within the source** rewrites earlier classifications during the scan. This is limited to unapplied items and covered by tests.
- **Deleting old managed files is irreversible.** It requires a conclusive comparison, the default option the user can switch off per run, and a verified new file (ADR 0021).
- **Inconclusive comparisons never replace.** Users can check the library and re-import later; the review list will offer decisions.

## Migration Plan

One Alembic migration:
- import result values;
- `library_imports.delete_replaced` (default true for existing rows);
- the new counters, filled from existing superseded managed files (none so far).

Rollback drops them.

## Open Questions

None.
