# Proposal

## Why

Five specs send uncertain results "to the review list" – fuzzy recording matches (library), inconclusive quality findings (quality-analysis), work candidates (works, publishers), import results needing review (library-import) and inconclusive downloads (sources) – but no spec defines that list: what an entry contains, who decides, what accepting or rejecting does, or how it scales. Without one definition each domain would build its own.

## What Changes

- New domain `review`: one central review list with typed entries (subject, origin, confidence, evidence, proposed change) and a status (open, accepted, rejected, deferred) with user and time of the decision.
- Accepting an entry applies its proposed change (as a job for bulk decisions); rejecting is remembered so the same suggestion is not raised again.
- Filters by type, origin and confidence; bulk decisions by selection rule; progressive loading like every list.
- Only editors and admins can see and decide entries.
- Sheets with uncertain OMR measures appear as one entry per sheet that leads to the sheet editor; measure-level correction stays in sheet-music.
- Other specs keep their "goes to the review list" wording and now refer to this domain.

## Capabilities

### New Capabilities

- `review`: central list of suggestions and uncertain results that need a human decision, with decisions, bulk actions and suppression of rejected suggestions.

### Modified Capabilities

_None._ Existing references to "the review list" in library, quality-analysis, works, publishers, library-import, sources and sheet-music keep their behavior and are now defined by `review`.

## Impact

- **Domains:** review (new). Producers: library, quality-analysis, works, publishers, library-import, sources, sheet-music.
- **Data model:** new package "Review" with `ReviewItem`; `WorkCandidate` is replaced by `ReviewItem` (type work assignment); `ReviewStatus` gains `DEFERRED` and `OBSOLETE`; `CandidateOrigin` becomes `ReviewOrigin` with additional values. Migration only once the schema exists.
- **Docs:** domain table in AGENTS.md, domain list in `openspec/config.yaml`, `docs/architecture/data-model.puml`.
- **Code:** new server module `server/anthology/review/`, client feature `client/src/features/review/`.
- **Non-functional requirements (2 s, 500,000 tracks):** the list may hold very many entries after a large import; it is a keyset-paged subscription with counts first, filters are index-backed, and bulk decisions run as jobs.
