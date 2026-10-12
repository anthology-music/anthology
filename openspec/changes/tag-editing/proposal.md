# Proposal

## Why

Editing tags is a core activity of the Local view, but no spec defines it: which fields exist on which level, how bulk edits work, what happens to files and caches, how manual corrections relate to automatic updates (e.g. MusicBrainz), whether changes can be undone, and how the core talks to the tagger service. The tagger is a required service from the first milestone.

## What Changes

- New domain `tagging`:
  - Editable fields on recording, release and track-context level; edits are stored in the database and apply in every context that uses the level.
  - Single and bulk edits (selection rule, preview count, job with progress) for editors and admins; every edit is audited.
  - Propagation: managed originals get base tags, referenced files with opt-in get their home-context tags, transcodes and tagged copies of affected contexts are invalidated, clients receive deltas.
  - **Field provenance:** every field records whether it was set manually or by an automatic source. Automatic updates apply directly to fields that were not edited manually; a differing automatic value for a manually edited field becomes a **tag conflict** that a user must confirm.
  - **Conflict list:** a dedicated list of tag conflicts with multi-select, grouping/filtering (field, album, artist, origin) and bulk accept/reject.
  - **Undo** for single and bulk edits from the audit log, as a job; fields changed again since are skipped and reported.
  - **Tagger:** file writes go through the tagger service (interface and write safety specified by change `tagger-service`); queued file writes when the tagger is unavailable.
- Review list: bulk decisions also by multi-select and groups (folded into change `review-list`).

## Capabilities

### New Capabilities

- `tagging`: editing of metadata fields, propagation to files and caches, field provenance and tag conflicts, and undo (the tagger service interface is added by change `tagger-service`).

### Modified Capabilities

- `library-import`: "Existing tags preserved" – imported tags are protected like manual edits; differences to MusicBrainz become tag conflicts in the conflict list.

(library's "Change tracking" and "Context-dependent metadata" stay valid; review is extended in the unarchived change `review-list`.)

## Impact

- **Domains:** tagging (new); uses library, review, transcoding, jobs, users.
- **Data model:** `FieldProvenance` (entity, field, source, set by/at); `ChangeSet` (user, rule, job, created/undone) with `AuditLog.changeSetId`; `ReviewType.TAG_CONFLICT`. Migration only once the schema exists.
- **Docs:** domain table in AGENTS.md and `openspec/config.yaml`; `services/tagger/README.md`; data model.
- **Code:** server module `server/anthology/tagging/`, client feature `client/src/features/tagging/`.
- **Non-functional requirements (2 s, 500,000 tracks):** bulk edits run as jobs; the database change is applied in batches so that browsing stays within budget; file writes are throttled background work.
