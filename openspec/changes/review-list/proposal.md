# Proposal

## Why

Several specs send uncertain results "to the review list" – fuzzy recording matches (library), inconclusive quality findings (quality-analysis), work candidates (works, publishers), import results needing review (library-import) and inconclusive downloads (sources) – but no spec defines that list: what an entry contains, who decides, what accepting or rejecting does, or how it scales. Without one definition each domain would build its own.

Four implemented changes have tasks waiting for this list: fuzzy suggestions (`recording-identification` 5.1), "needs review" import results (`library-import-folders` 7.2), quality findings without high confidence (`quality-analysis-core` 5.1) and inconclusive quality comparisons (`quality-based-replacement` 5.1). Until the list exists, these results are only counted.

## What Changes

- New domain `review`: one central review list with typed entries (subject, origin, confidence, evidence, proposed change) and a status (open, accepted, rejected, deferred, obsolete) with user and time of the decision.
- Accepting an entry applies its proposed change through the owning domain, which re-validates it first; an entry whose proposal no longer applies is closed as obsolete. Rejecting is remembered so the same suggestion is not raised again.
- Filters by type, origin, confidence and status with counts first; progressive loading like every list; bulk decisions by selection or rule as a job.
- Only editors and admins can see and decide entries.
- Producers implemented with this change, for the domains that exist:
  - **Same recording?** Two recordings that may be one: an imported file that matches a recording by artist, title and duration (±2 s) without a fingerprint confirmation, and recordings identified as the same MusicBrainz recording. Accepting merges them (the better original stays active, the other is superseded).
  - **MusicBrainz suggestion:** a recording without ISRC or fingerprint match gets a suggested MusicBrainz recording found by artist, title and duration. Accepting assigns the ID.
  - **Different title:** an import match by identifier or fingerprint whose title differs. Accepting confirms the match; rejecting makes the file a recording of its own.
  - **Inconclusive replacement:** an imported file that may be better than the original, but the comparison was not conclusive. Accepting makes it the original.
  - **Quality finding:** an analysis result without high confidence, with a spectrogram. The decision is "genuine" (confirmed genuine) or "upscaled" (with the estimated effective quality); a human decision survives later analysis runs.
- Producers of works, publishers, sources and sheet-music register when those domains are implemented; their tasks stay open in this change.
- A "Review" page in the client for editors and admins, with the open count in the navigation.

## Capabilities

### New Capabilities

- `review`: central list of suggestions and uncertain results that need a human decision, with decisions, bulk actions, suppression of rejected suggestions and the entry types of library, library-import and quality-analysis.

### Modified Capabilities

_None._ Existing references to "the review list" in library, quality-analysis, works, publishers, library-import, sources and sheet-music keep their behavior and are now defined by `review`.

## Impact

- **Domains:** review (new). Producers now: library, library-import, quality-analysis (and metadata-lookup for the MusicBrainz search). Later: works, publishers, sources, sheet-music.
- **Data model:** new package "Review" with `ReviewItem` and `ReviewCounter`; `WorkCandidate` is replaced by `ReviewItem` (type work assignment); `ReviewStatus` gains `DEFERRED` and `OBSOLETE`; `CandidateOrigin` becomes `ReviewOrigin`; `ReviewType` gains `MUSICBRAINZ_SUGGESTION`, `IMPORT_TITLE` and `IMPORT_REPLACEMENT`; `QualityAnalysis` gains the human decision; `IdentificationStatus` gains `CONFIRMED`.
- **Migration:** `0014_review` (review tables, counters, quality decision columns).
- **API:** decisions and bulk decisions under `/api/v1/review`, spectrogram images over HTTP; sync stream `review.items`.
- **Docs:** `docs/architecture/data-model.puml`, `docs/architecture/sync-protocol.md`, `server/AGENTS.md`.
- **Code:** new server module `server/anthology/review/`, client feature `client/src/features/review/`.
- **Non-functional requirements (2 s, 500,000 tracks):** the list may hold very many entries after a large import; it is a keyset-paged subscription with maintained counters, filters are index-backed, producers insert in batches and bulk decisions run as jobs.
