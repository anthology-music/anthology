# Design

## Context

- `library/service.py` already has the write functions (`update_artist`, `update_release`, `update_recording`, `update_track`) that keep sort keys, counters, change entries and the audit log consistent, and the change entries `release.moved` and `track.moved` for rows leaving a filtered list. `audit_log.change_set_id` exists but is never set.
- The library stores no genre, composer or label yet; the release date holds the year.
- The tagger service implements read, write (`atomic`, `in_place`), copy and health (`docs/architecture/tagger-api.md`); `TaggerClient` and the availability monitor exist. Nothing writes tags yet. ADR 0008: managed originals carry only neutral base tags; referenced files are written only with `tag_writes_allowed`.
- The review module (`anthology/review/`) provides entries, suppression, decisions, bulk jobs and a stream; the review spec keeps tag conflicts out of the review list.
- Neither transcodes nor tagged copies exist yet (`transcoding`, `context-tags-on-delivery`).

See proposal.md for the motivation.

## Goals / Non-Goals

**Goals:**
- One edit path for single and bulk edits, manual and automatic.
- Manual corrections never lost silently; conflicts are cheap to resolve in bulk.
- Undo for bulk edits from the audit log, without a separate history store.

**Non-Goals:**
- Covers (change `covers`), works and sheet metadata (works, sheet-music).
- Invalidating transcodes and tagged copies (task 3.3 waits for them).
- Rewriting the tags of managed originals that were imported before this change (their tags are written with the first edit; a normalisation job is a later topic).

## Delivery

Pull request 1: tasks 1–3 and 4.2 (editing, history and undo, provenance records, file writes, edit mode and history in the client). Pull request 2: tasks 5.x (tag conflicts, conflict list, MusicBrainz refresh, imported tags against MusicBrainz). The change is archived after the second.

## Decisions

### Fields and levels

| Level | Fields | Storage |
|---|---|---|
| Recording | `title`, `artist`, `isrc`, `mb_recording_id`, `composers`, `genres` | `recordings` (`composers`, `genres`: JSON lists of text, new) |
| Release | `title`, `album_artist`, `year`, `label` | `releases` (`label` new; `year` changes the year of `release_date` and keeps month and day, or sets 1 January) |
| Track context | `track_number`, `disc_number`, `context_title`, `context_artist` | `tracks` |

`artist` and `album_artist` name an artist by its credited text: the edit finds or creates the artist (`get_or_create_artist`) and keeps the text as display text, as the import does. Composers stay plain text until works models persons. `mb_recording_id` is unique; an edit to an ID another recording has is refused (`duplicate_id`), the identification outcome becomes `confirmed`.

Genres are a recording field (decided with the maintainer): a release can hold a march and a polka. Lists are stored as JSON text, not as tables: nothing filters by them yet, and `search` will index them.

### One edit service

`tagging.service.apply(session, edits, *, origin, user_id, change_set)` takes a list of `Edit(level, entity_id, fields)`. For each field it checks provenance (task 5.1 adds the conflict branch; in the first pull request every origin is manual), applies the value through the library service, records provenance and an audit row with old and new value and the change set, and collects the files to write. Values are validated per field (pydantic): text length, numbers ≥ 1, years 1000–9999, ISRC pattern, UUID.

### Moving tracks by album

An edit of `album` (or `album_artist`) on selected tracks is not a release edit: the tracks move to the release with that title and album artist (`library.service.move_track`), found by sort key or created with the old release's other values (year, label, release group type). Track number and disc number stay; a moved track whose position is taken keeps it (positions are not unique). Each move writes `track.moved` for the old release's list. An empty release is deleted with its counters, like an orphaned artist. Renaming an album is an edit of the release (album page).

### Field provenance

`field_provenance(entity_type, entity_id, field, source, set_by [0..1], set_at)`, primary key `(entity_type, entity_id, field)`. Sources: `manual`, `musicbrainz`, `import`, `source`, `publisher`, `review` (an accepted conflict counts as set by the accepting user). A field without a row was set by an import before provenance existed (all library entries so far come from imports or the generator), so it counts as `import`; imports do not write rows. `manual`, `import` and `review` are protected.

Alternative considered: a per-field "locked" flag. Rejected: the maintainer wants overwrites allowed after confirmation, which needs the source and the conflict, not a hard lock.

### Change sets and undo

Every edit operation creates `change_sets(id, user_id, kind (edit | undo), summary_json, rule_json [0..1], job_id [0..1], items, created_at, undone_by [0..1], undo_of [0..1])`; each audit row of the operation carries `change_set_id` and `{field: [old, new]}`. The history is the stream `tagging.changes` (newest first; editors and admins), each row with user, time, summary (fields, number of items) and whether it can still be undone.

Undo (`POST /api/v1/tagging/changes/{id}/undo`) creates a change set of kind `undo` and a `tagging_undo` job that reads the audit rows of the change set keyset-paged and writes the old value where the current value still equals the new one; others are skipped and listed in the job result (field, entity, current value). Track moves are undone by moving back (the old release is recreated if it was removed). An undo is undoable like any change set; a change set can be undone once.

### Bulk edits

`POST /api/v1/tagging/edits` takes `{ selection, fields, preview }`. `selection` is `{ "ids": [...], "level": ... }` (multi-select, at most 500) or a rule: the parameters of a library list (`release_id`, `artist_id`, or all tracks). With `preview: true` the answer is the count (counters or an index-only count) and nothing changes. Without it, up to 50 items are applied directly; more run as a `tagging_bulk` job that applies batches of 500 in keyset order, each in its own transaction with change entries, so deltas arrive while the job runs.

### File writes

After commit, the affected audio files are entered into `tag_writes(audio_file_id PK, requested_at, attempts, last_error [0..1], claimed_until [0..1])`; a repeated edit of the same file only updates `requested_at` (coalescing). A `TagWriter` task per process (next to the scheduler) claims due rows with a compare-and-swap on `claimed_until`, builds the tags from the database at write time, sends batches to the tagger and removes the rows of written files:

- managed active original → base tags (`title`, `artist`, `isrc`, `musicbrainz_recording_id`), `replace_all`, mode `atomic`;
- referenced active original with `tag_writes_allowed` → the home context's tags (title, artist, album, album artist, track and disc number with totals, date, genres, composers, label, ISRC, MusicBrainz IDs), not `replace_all`, mode `in_place` (keeps hardlinks; the tagger journals a backup);
- superseded files and referenced files without the opt-in are never entered (`check_file_operation(WRITE_TAGS)`).

Only edits of fields that end up in the file enter a file (base fields for managed originals, home-context fields for referenced ones). When the tagger is unavailable (`TaggerUnavailable`) rows stay and the worker sleeps until the monitor reports it available again; per-file errors are stored with the attempt count and retried with back-off (at most 5 attempts, then kept with the error and shown to admins). The audio hash covers audio data only, so a tag write changes neither the audio hash nor duplicate detection; the content hash of a managed original is updated after the write. The pending count is shown in the history (`tagging.changes` counters).

### Tag conflicts (pull request 2)

Entries are `ReviewItem`s of type `TAG_CONFLICT` (subject: the entity; proposal: field, value, source); `review.items` leaves them out and `tagging.conflicts` lists only them, with filters and group counts by field, release, artist and source (stored on the entry as `group_*` columns, indexed). Decisions reuse the review decisions and bulk job; accepting applies the value with origin `review`. The MusicBrainz refresh (`metadata-lookup` 2.4) is the first automatic source; differences between imported tags and MusicBrainz arise from it, because imported values are protected.

### Client

- Edit mode (`client/src/features/tagging/`) on album pages and the track list, per mockup `Lokal-Editieren`: switch Hören/Editieren, a checkbox per row, select all, shift-click for a range, "whole list" sends the list's rule; a sticky bar with the count; the tag editor shows the fields of the selection (mixed values as "verschiedene Werte", unchanged unless edited) and confirms bulk edits with the count.
- The album page edits the album's own fields.
- The history (Einstellungen › Änderungsverlauf, editors and admins) lists change sets with undo and its result.

## Risks / Trade-offs

- [Provenance rows for 500,000 tracks × fields] → stored only for values set after the import; narrow table with a composite primary key.
- [In-place writes can corrupt a referenced file on crash] → only with explicit opt-in; the tagger journals a backup and restores it on start.
- [Undo after many later edits produces long reports] → the report is the job result, listed per skipped field.
- [Moving tracks creates releases by title] → only when no release with the same title and album artist exists; the move is in the change set and can be undone.
- [JSON lists cannot be filtered in SQL] → accepted until `search`.

## Migration Plan

`0015_tag_editing`: `recordings.genres`, `recordings.composers` (JSON text, default `[]`), `releases.label`, `field_provenance`, `change_sets`, `audit_log` index on `change_set_id`, `tag_writes`. Pull request 2 adds `TAG_CONFLICT` and the group columns of `review_items`.
