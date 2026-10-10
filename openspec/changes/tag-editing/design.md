# Design

## Context

The core reads tags quickly with tinytag and writes/reads full tags through the GPL tagger service (ADR 0004). Change `managed-and-referenced-originals` defines base tags for managed originals and opt-in home-context tags for referenced files; `context-tags-on-delivery` adds tagged copies; `review-list` provides decisions, suppression and bulk jobs; `sync-protocol-details` provides the global change sequence. The `AuditLog` records changes but has no grouping. See proposal.md for the motivation.

## Goals / Non-Goals

**Goals:**
- One edit path for single and bulk edits, manual and automatic.
- Manual corrections never lost silently; conflicts are cheap to resolve in bulk.
- Undo for bulk edits without a separate history store.

**Non-Goals:**
- Cover management details (separate spec "covers").
- Editing of works and sheet metadata (works, sheet-music).

## Decisions

### One edit service

`tagging.service.apply(changes, actor, origin)` is used by the UI, by bulk jobs and by automatic sources. For each field it checks provenance: `origin = MANUAL` or field not manual → write; automatic origin on a protected field (`MANUAL`, `IMPORT`, `REVIEW`) with a different value → create review item `TAG_CONFLICT` (suppression key prevents duplicates). Writes, provenance, `ChangeLog` and `AuditLog` happen in one transaction per batch.

### Field provenance

`FieldProvenance(entityType, entityId, field, source, setBy [0..1], setAt)`; only rows for fields that have a value. Source values: `MANUAL`, `MUSICBRAINZ`, `IMPORT`, `SOURCE`, `PUBLISHER`, `REVIEW` (accepted review item counts as manual by the accepting user). `MANUAL`, `IMPORT` and `REVIEW` are protected: imported tags are the user's existing curation (library-import "Existing tags preserved").

Alternative considered: a per-field "locked" flag. Rejected: the maintainer wants overwrites allowed after confirmation, which needs the source and the conflict, not a hard lock.

### Conflict list as a view of the review module

The conflict list is its own entry in the navigation and its own subscription (`tagging.conflicts`), but entries are `ReviewItem`s of type `TAG_CONFLICT`, which replaces the earlier `TAG_DIFFERENCE` type and is excluded from the general review list. Grouping by field, album, artist or source uses indexed columns derived from `proposalJson` (stored as generated columns). Bulk decisions reuse the review bulk job (multi-select or group rule). This avoids a second decision and suppression implementation.

### Change sets and undo

Every edit operation creates a `ChangeSet(id, user, ruleJson [0..1], jobId [0..1], createdAt, undoneAt [0..1], undoOf [0..1])`; each `AuditLog` row gets `changeSetId` and stores old and new value. Undo creates a new change set that writes the old values for all rows whose current value still equals the change set's new value; others are reported. Undo itself is undoable.

### Bulk edits

The client sends field changes plus a selection rule (sync-protocol). The server first returns the count (maintained counters or an index-only count for the rule), then on confirmation starts a `TAGGING_BULK` job that applies batches of 500 items in keyset order, each batch in its own transaction with change sequence numbers and deltas.

### File writes

After commit, affected files are enqueued in a persistent write queue (one entry per file, coalescing repeated edits). A throttled worker sends batches to the tagger:

- managed originals → `POST /v1/tags/write` with `mode: atomic` (temp file + fsync + rename);
- referenced files with `tagWritesAllowed` → `mode: in_place` (keeps hardlinks; the tagger writes into the existing inode);
- never superseded files, never referenced files without opt-in.

If the tagger is unavailable, entries stay queued; health checks resume the worker. After a successful write the tinytag cache and audio hash stay valid because only tag blocks change (audio hash is computed over audio data only).

### Tagger interface v1

| Endpoint | Purpose |
|---|---|
| `POST /v1/tags/read` | full tags, cover and audio properties of one or more files |
| `POST /v1/tags/write` | write tags and cover into one or more files; `mode: atomic \| in_place` |
| `POST /v1/tags/copy` | write a tagged copy into the cache (change `context-tags-on-delivery`) |
| `GET /v1/health` | health and version |

### Progressive loading

Bulk edits and undo stream progress via the job subscription; the conflict list is a keyset-paged subscription with counts per group first.

## Risks / Trade-offs

- [Provenance rows for 500,000 tracks × fields] → only stored for set fields; narrow table with a composite primary key.
- [In-place writes can corrupt a referenced file on crash] → only with explicit opt-in; the tagger writes to a temp copy first, verifies, then copies the tag block in place; documented in the opt-in dialog.
- [Undo after many later edits produces long reports] → report is a paged list in the job result.

## Migration Plan

No schema yet. Data model and docs updated now.
