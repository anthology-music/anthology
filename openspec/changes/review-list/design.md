# Design

## Context

Uncertain results exist today but are only counted:

- `library_import`: items with result `needs_review` (identifier or fingerprint match, different title; they become a track context of the matched recording) and `suspicious_quality` (an inconclusive quality comparison; also a context, nothing is replaced). Name matches (artist, title, duration ±2 s) whose fingerprint could not be compared become `new` recordings without a hint.
- `library.identification`: outcome `duplicate` names the other recording with the same MusicBrainz ID; outcome `no_match` has no suggestion.
- `quality_analysis`: results that are not high-confidence (`suspicious` medium/low, `genuine` medium `possible_lossy_origin`) leave the effective quality unknown. `confirmed_genuine` is reserved for the review list.

The data model already describes `ReviewItem` (task 1.2). `works`, `publishers`, `sources` and `sheet_music` are empty modules; their producers come with their implementation. See proposal.md for the motivation.

## Goals / Non-Goals

**Goals:**
- One table and one subscription for all review entries.
- Producers only create entries and register an apply handler; the review module owns decisions, suppression, counters and bulk jobs.
- Producers of library, library-import and quality-analysis, which closes the open tasks of four changes.

**Non-Goals:**
- Producers of works, publishers, sources and sheet-music (tasks 3.6–3.8 wait for those domains).
- Measure-level OMR correction UI (sheet-music).
- Recording automatic high-confidence decisions as entries; they go to the audit log only.
- Lossless reduction of upscaled files (`quality-analysis-core` 5.3).

## Decisions

### Generic `ReviewItem` with a typed proposal

```
review_items
  id, type, subject_type, subject_id, origin, confidence,
  evidence_json, proposal_json, summary_json, suppression_key,
  status (open, accepted, rejected, deferred, obsolete),
  note [0..1], created_at, decided_by [0..1], decided_at [0..1]
review_counters
  type, origin, confidence, status, value
```

`ReviewType`: `RECORDING_MATCH`, `MUSICBRAINZ_SUGGESTION`, `IMPORT_TITLE`, `IMPORT_REPLACEMENT`, `QUALITY_FINDING`, later `WORK_ASSIGNMENT`, `DOWNLOAD_REPLACEMENT`, `SHEET_OMR`. `ReviewOrigin`: `FUZZY_MATCH`, `MUSICBRAINZ`, `IMPORT`, `QUALITY_ANALYSIS`, later `PUBLISHER`, `LLM`, `SOURCE`, `OMR`. Confidence reuses high/medium/low.

`summary_json` is written by the producer: subject label, current and proposed value as display values, so the list renders without joins into other domains. `evidence_json` holds the measurements (e.g. durations, fingerprint similarity, finding values) and references (recording IDs, audio hashes for spectrograms). Per-type pydantic models (`review/schemas.py`) build proposal and evidence and parse them when deciding; their JSON schemas are published under `parts` of the sync message schema (`PART_SCHEMAS`), so the client reads them with generated types.

`WorkCandidate` is replaced by `ReviewItem` of type `WORK_ASSIGNMENT` (its fields map one to one; the publication reference moves into the evidence). `ReviewStatus.AUTO_ACCEPTED` stays only for `Sheet.reviewStatus`.

Alternative considered: keep per-domain candidate tables and build a union view. Rejected: decisions, suppression and bulk jobs would be implemented per table, and the union cannot be keyset-paged efficiently.

### Applying decisions through the owning domain

`review.register(type, handler)` at app start. A handler has:

- `still_applies(session, item) -> str | None` – None, or the reason why the proposal no longer applies;
- `accept(session, item, choice, user_id)` and optionally `reject(session, item, user_id)` (most rejections change nothing besides the entry).

Accept and reject call `still_applies` (read-only); a reason closes the entry as `obsolete` with that reason in `note`. Otherwise `prepare` does the file work outside the transaction (it may also find the proposal stale, e.g. a changed source file), then `still_applies` runs again and `apply` changes the data in the decision's transaction; `finished` runs after the commit (e.g. removing a moved source). An exception in `apply` rolls the whole decision back and the entry stays open (no savepoints: SQLite's driver does not handle them reliably). Decisions with file work run in the decision job and the entry stays `open` until its item finished. A type without a registered handler (an optional service missing) is shown as "cannot be applied right now" and only accepts reject and defer.

Entries of removed subjects are closed with `review.close_subject` (a merged recording's other entries, a quality result that became conclusive); all other stale entries are found when they are decided. No current type proposes a value that an edit elsewhere could set, so no general change hook is needed yet; `tagging` adds one with its first such type.

### Suppression

`suppression_key` = SHA-256 of type, subject and the normalised proposed value. A partial unique index on `suppression_key WHERE status IN ('open','deferred','rejected')` prevents duplicates and re-raising rejected suggestions; producers insert in batches with "on conflict do nothing". An accepted or obsolete entry does not suppress: the same suggestion may come back when the data changes again.

### Counters and progressive loading

`review_counters` holds one row per (type, origin, confidence, status), updated in the same transaction as inserts and decisions (like `library_counters`). Counts for any filter are a sum over at most a few hundred rows.

Subscription `review.items` with params (status, type, origin, confidence). `snapshot_meta.counters` carries counts per type and per status for the chosen filter. Rows are keyset-paged on `(status, confidence_rank, created_at, id)`: high confidence first, oldest first. Indexes: `(status, confidence_rank, created_at, id)` and `(status, type, confidence_rank, created_at, id)`; origin filters use the type index (origin is nearly determined by type). A decision emits a delta for the row; the row leaves the subscription when its status no longer matches.

### Decisions over HTTP, files in a job

`POST /api/v1/review/decisions` takes either `ids` (multi-select, at most 500) or a `rule` (the subscription filter) plus `decision` (`accept`, `reject`, `defer`, `reopen`) and an optional `choice` for types with two answers. One entry without file work is decided directly (200). Everything else creates a `review_decision` job (`JobType.REVIEW_BULK`) that iterates the selected entries in keyset order in batches and reports progress; each entry records the user and time of the decision. A rule is evaluated when the job starts: entries created later are not included.

Deferred entries leave the default view (`status=open`) and reappear under "deferred"; `reopen` brings deferred entries back.

### Entry types of this change

**`RECORDING_MATCH`** – subject: recording B, proposal: "same recording as A".
- Origin `FUZZY_MATCH`: created after an import applied a `new` item that had name candidates (`fingerprint_candidates`: artist, title, duration ±2 s). The classification stores the closest candidate on the import item (`name_match_recording_id` or `name_match_item_id` for an earlier file of the source, and `name_match_similarity`). Confidence medium when a fingerprint was missing and nothing could be compared; low when the fingerprints were compared and differ (usually another version: a remaster with different mastering, another mix, a re-recording). The evidence carries the fingerprint similarity, so the list can show "probably another version"; low-confidence entries are easy to filter out or reject in bulk.
- Origin `MUSICBRAINZ` (confidence high): created when identification records `duplicate`.
- Accept merges B into A (`library.merge_recordings`): B's tracks move to A, the better of the two active originals (effective quality, `ranking.compare`; inconclusive keeps A's) becomes A's active original, the other is superseded (`replace_original` semantics; a superseded managed file can be deleted later through the existing report, a referenced one never). Identifiers missing on A are taken from B, then B is deleted. `still_applies`: both recordings exist.
- Reject: both stay separate; the key suppresses the pair.

**`MUSICBRAINZ_SUGGESTION`** – subject: a recording with outcome `no_match`, proposal: MusicBrainz recording ID with title, artist and duration.
- The identification job searches MusicBrainz (`/ws/2/recording?query=` with artist, title; background priority, cached and rate-limited like every lookup) after the outcome `no_match` and after `not_possible` for lack of an AcoustID key (not for a missing file), and creates an entry when exactly one or the best result matches artist, title and duration ±2 s (confidence medium; low when several match). `ANTHOLOGY_MUSICBRAINZ_PUBLIC_URL` (default the public service) lets the end-to-end tests point the search at a closed port.
- Accept assigns the ID with outcome `confirmed` (new `IdentificationStatus.CONFIRMED`, counted like the others) and registers the refresh; if the ID meanwhile belongs to another recording, the outcome becomes `duplicate` and a `RECORDING_MATCH` entry is created instead. Nothing is merged automatically.

**`IMPORT_TITLE`** – subject: the track context created from a `needs_review` item, proposal: "same recording despite a different title".
- Accept: confirms, nothing changes.
- Reject: "separate recording": the file becomes a recording of its own, like a `new` item of its import (placed in the import's mode, verified; the track moves to the new recording, `library.separate_track`). `still_applies`: the track still belongs to the matched recording; `prepare` checks that the source still has the recorded size and modification time (hashing the audio again would decode the whole file), otherwise the entry closes as obsolete with `source_changed`.
- Because reject changes data here, it is not suppressing in the usual sense, but the key still prevents a second entry.

**`IMPORT_REPLACEMENT`** – subject: the recording, proposal: "replace the original with this file" for a `suspicious_quality` item. Evidence: both quality results and spectrograms.
- Accept: the file becomes the active original like a `replaces_lower_quality` item (placed in the import's mode, verified by checksum); the old original is superseded. `still_applies`: the source is unchanged and the recording's active original is still the one compared.
- Reject: keep the original.

**`QUALITY_FINDING`** – subject: an audio hash, created by `quality_analysis.store` for results that are not high-confidence, except `too_quiet` (nothing to judge). Confidence = the result's confidence. Evidence: finding and values, file facts, spectrogram.
- Two answers (`choice`): `genuine` sets `confirmed_genuine` with the declared quality as effective quality; `upscaled` sets `upscaled` with the estimated tier from the cutoff (`nearest_bitrate` → lossy tier). Both are human decisions.
- `quality_analyses` gains `decided_status`, `decided_quality`, `decided_by` and `decided_at`; `store` and `apply_stored` keep a human decision when the analysis runs again (a full re-run included) and apply it to new files with the same audio hash; the ranking treats it as conclusive. Re-running does not create a new entry for a decided hash, and a result that became conclusive closes an open entry (`now_conclusive`). One entry per audio hash.
- `still_applies`: at least one file with this audio hash exists.

### Spectrogram over HTTP

`GET /api/v1/quality-analysis/{audio_hash}/spectrogram.png` (editors and admins) renders the spectrogram of the active file with this audio hash on first request (30 seconds from the middle, 1024×512) and caches it under `<data>/spectrograms/`. FFmpeg decodes the excerpt to PCM as for the analysis; numpy computes the spectrogram and the PNG is written with zlib. FFmpeg's `showspectrumpic` was considered, but the server's FFmpeg build (ADR 0020) has neither the filter nor a PNG encoder, and adding both (with zlib) would widen that build for one image. Media stays off the WebSocket. The client loads it with its access token and shows it as an object URL. Inconclusive replacements show the current original's spectrogram; the imported file is not in the library and has none.

### Client

`client/src/features/review/`: route `/review`, navigation entry with the open count for editors and admins. Filter bar (status, type, origin, confidence) with counts from `snapshot_meta`, a virtual list, a detail panel with evidence and current vs. proposed value (both recordings for a match, spectrograms for quality), buttons with per-type labels ("Same recording" / "Keep separate", "Genuine" / "Upscaled", …), defer, multi-select and "decide all matching" with a confirmation that states the count. Job progress shows through the existing jobs view.

## Risks / Trade-offs

- [`proposal_json` is untyped in the database] → per-type pydantic models validate on write and read.
- [Very large lists after big imports] → counters, keyset paging, rules, batched inserts; performance test with 20,000 entries.
- [Merging recordings is hard to undo] → only on an explicit decision, audited with both IDs; originals are superseded, never deleted by the merge.
- [Fuzzy MusicBrainz search returns wrong recordings] → only suggestions, duration ±2 s and artist must match; low confidence when several results match.
- [Producers of absent domains] → their entry types are not created; existing entries of an unavailable handler can be rejected or deferred.
- [Spectrogram rendering is slow for large hi-res files] → only 30 seconds, cached per audio hash, rendered on demand.

## Migration Plan

`0014_review`: `review_items` with the indexes above, `review_counters`, the decision columns of `quality_analyses`.

Results from before this change (import items `needs_review`/`suspicious_quality`, non-high-confidence analyses, `duplicate` outcomes) get their entries from a one-time `review_backfill` job with one item per type (each handler's `backfill`). The app creates it at start-up when no job of this type exists and an admin owns it (a fresh installation creates it on a later start); it reads the sources keyset-paged and inserts in batches through the same producer functions, so suppression applies. Name matches of earlier imports without fingerprint comparison and MusicBrainz suggestions are not backfilled: the next identification run creates the suggestions.
