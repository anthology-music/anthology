# ADR 0022: Quality checks on acquisition only for duplicate candidates

- Status: Accepted
- Date: 2026-10-23

## Context

ADR 0012 makes the effective quality the basis of ranking and replacement and expects an analysis step for every new file. Analysing every file of an import or download makes scans of large collections much slower (about 0.1 s per CD file and 0.4 s per hi-res file for the excerpts alone). It also fills the review list with "suspicious" findings for music the user only wanted to add. The decisions that need the effective quality during acquisition are only the duplicate decisions: is the new file better than the existing original, or better than another copy in the same source?

## Decision

- During an acquisition, Anthology analyses only **duplicate candidates**: files that match an existing recording or another file of the same source (by identifiers or fingerprint). Acquisitions are imports and uploads now, and downloads from streaming sources and CD imports later. Both sides of each comparison are analysed: the new file and the existing original or other copy, unless a result is stored already.
- Other new files are **not** analysed automatically.
- Users start a **quality check of the whole library** manually (editors and admins, in the settings). It analyses every file without a result.
- Results are stored per audio hash, so files analysed as candidates are skipped by the manual check.

This supersedes the consequence "An analysis step runs for every new file" of ADR 0012; its other decisions stay.

## Consequences

- Scans stay fast; the report's "suspicious quality" category counts the analysed candidates only.
- Quality badges appear for new files only after a manual check or when they were candidates.
- The automatic analysis after an import (change `quality-analysis-core`) is removed.
