# Design

## Context

The data model has `WorkCandidate` (field, proposed value, origin, confidence, evidence, status), `QualityAnalysis.status`, `ImportResult.NEEDS_REVIEW`, `Sheet.reviewStatus` and an `AuditLog`. Change `effective-quality-duplicate-checks` adds `ItemOutcome.NEEDS_REVIEW` for downloads. Each of these needs the same list, decision and bulk mechanics. See proposal.md for the motivation.

## Goals / Non-Goals

**Goals:**
- One table and one subscription for all review entries.
- Producers only create entries; the review module owns decisions, suppression and bulk jobs.

**Non-Goals:**
- Measure-level OMR correction UI (sheet-music).
- Recording automatic high-confidence decisions as entries; they go to the audit log only.

## Decisions

### Generic `ReviewItem` with a typed proposal

```
ReviewItem
  id, type : ReviewType, subjectType, subjectId,
  origin : ReviewOrigin, confidence : Confidence,
  evidenceJson, proposalJson, suppressionKey,
  status : ReviewStatus (OPEN, ACCEPTED, REJECTED, DEFERRED, OBSOLETE),
  createdAt, decidedBy [0..1], decidedAt [0..1], changeSeq
```

`ReviewType`: `RECORDING_MATCH`, `QUALITY_FINDING`, `WORK_ASSIGNMENT`, `TAG_DIFFERENCE`, `DOWNLOAD_REPLACEMENT`, `SHEET_OMR`. `ReviewOrigin`: `PUBLISHER`, `MUSICBRAINZ`, `LLM`, `FUZZY_MATCH`, `QUALITY_ANALYSIS`, `IMPORT`, `SOURCE`, `OMR`.

`WorkCandidate` is replaced by `ReviewItem` of type `WORK_ASSIGNMENT` (its fields map one to one; the publication reference moves into `evidenceJson`). `ReviewStatus` keeps `AUTO_ACCEPTED` only for `Sheet.reviewStatus` (e.g. MusicXML uploads); automatic decisions never create a `ReviewItem`.

Alternative considered: keep per-domain candidate tables and build a union view. Rejected: decisions, suppression and bulk jobs would be implemented per table, and the union cannot be keyset-paged efficiently.

### Applying decisions through the owning domain

Each producer registers an apply handler per `ReviewType` (`review.register_handler(type, handler)`). Accept calls the handler, which re-validates the proposal against the current subject; if it no longer applies, the item becomes `OBSOLETE`. This keeps domain logic in the domain and makes "stale entries" a single code path.

### Suppression

`suppressionKey` = hash of type, subject and normalised proposed value. A partial unique index on `(suppressionKey) WHERE status IN ('OPEN','DEFERRED','REJECTED')` prevents duplicates and re-raising rejected suggestions; producers insert with "on conflict do nothing".

### Progressive loading

Subscription `review.items` with filter (type, origin, confidence, status). `snapshot_meta` carries counts per type and status from maintained counters (updated in the same transaction as inserts and decisions). Rows are keyset-paged on `(status, confidence, createdAt, id)` with composite indexes for the filter combinations. Decisions emit deltas with `changeSeq`.

### Bulk decisions

A bulk decision sends the selection rule (sync-protocol "Rule-based selection"); the server creates a `REVIEW_BULK` job that iterates matching items in keyset order, applies handlers in batches and reports progress.

## Risks / Trade-offs

- [`proposalJson` is untyped in the database] → per-type pydantic models validate on write and read; API types are generated per type.
- [Very large lists after big imports] → counts first, keyset paging, bulk rules; producers batch inserts.
- [Handlers of optional services (e.g. publishers plugin) missing] → items of unavailable producers stay open and are shown as "cannot apply right now".

## Migration Plan

No schema yet. Data model updated now; first migration of the review module creates the table, indexes and counters.
