# Proposal

## Why

Editing tags is a core activity of the Local view, but no spec defines it: which fields exist on which level, how bulk edits work, what happens to files and caches, how manual corrections relate to automatic updates (e.g. MusicBrainz), whether changes can be undone, and how the core talks to the tagger service. The tagger service and its client exist (change `tagger-service`); nothing writes tags yet.

Two implemented changes wait for this one: tag writes into referenced files with opt-in (`managed-and-referenced-originals` 2.3) and the MusicBrainz refresh that applies changes through tagging (`metadata-lookup` 2.4).

## What Changes

- New domain `tagging`:
  - Editable fields on recording level (title, artist, ISRC, MusicBrainz recording ID, composers, genres), release level (album title, album artist, year, label) and track-context level (track and disc number, context title and artist). Edits are stored in the database and apply in every context that uses the level. Genres belong to the recording (one album can hold a march and a polka); several genres and composers are allowed.
  - Changing the album of selected tracks moves them to the album with that title and album artist (created if needed); renaming an album is an edit of the album itself.
  - Single and bulk edits (explicit selection or a selection rule, count shown before confirming, job with progress) for editors and admins; every edit is audited.
  - **Change history and undo:** every edit operation is a change set; undo restores the previous values as a job, skips fields changed again since and reports them; an undo can be undone.
  - **Field provenance:** every field records whether it was set manually (user, time) or by an automatic source; values without a record come from an import and count as imported.
  - **File writes:** managed originals get their neutral base tags (title, artist, ISRC, MusicBrainz recording ID), referenced files with tag writing enabled get their home context's tags; a persistent queue coalesces writes and waits while the tagger is unavailable; superseded files are never written.
  - **Tag conflicts:** automatic updates apply directly to fields neither set manually nor imported; a differing value for such a protected field becomes a tag conflict in a dedicated conflict list (entries of the review module, shown separately), decided individually, by multi-select or per group.
  - The client gets an edit mode for lists and album pages (selection, sticky action bar with count, tag editor), the change history with undo and the conflict list.
- Delivered in two pull requests within this change: first editing, history, provenance and file writes; then tag conflicts with the conflict list, the MusicBrainz refresh (`metadata-lookup` 2.4) and differences between imported tags and MusicBrainz. The change stays open until both are merged.
- Covers are edited through change `covers`; invalidating transcodes and tagged copies waits for `transcoding` and `context-tags-on-delivery`, which do not exist yet.

## Capabilities

### New Capabilities

_None_ – `tagging` exists (tagger interface, safe writes); this change adds the editing requirements to it.

### Modified Capabilities

- `tagging`: field levels, single and bulk edits, moving tracks by album, propagation, writes without the tagger, field provenance, tag conflicts, conflict list, undo.
- `library-import`: "Existing tags preserved" – imported tags are protected like manual edits; differences to MusicBrainz become tag conflicts in the conflict list.

## Impact

- **Domains:** tagging; uses library, review, jobs, users, metadata-lookup.
- **Data model:** `FieldProvenance`, `ChangeSet` (with `AuditLog.changeSetId`), `TagWrite` (queue), `Recording.genres`/`composers`, `Release.label`; later `ReviewType.TAG_CONFLICT`. Migration `0015_tag_editing` (and one for the conflicts).
- **API:** `POST /api/v1/tagging/edits` (selected tracks or a list rule, fields per level; preview and apply), `POST /api/v1/tagging/values` (current values for the editor), `POST /api/v1/tagging/changes/{id}/undo`; streams `tagging.changes` (history) and later `tagging.conflicts`.
- **Docs:** `docs/architecture/data-model.puml`, `docs/architecture/sync-protocol.md`, `server/AGENTS.md`, `docs/agent-notes.md`.
- **Code:** server module `server/anthology/tagging/`, client feature `client/src/features/tagging/`.
- **Non-functional requirements (2 s, 500,000 tracks):** bulk edits run as jobs in keyset batches so that browsing stays within budget; provenance is stored only for values set after the import; file writes are throttled background work.
