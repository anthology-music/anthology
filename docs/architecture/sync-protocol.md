# Sync protocol

One WebSocket per client carries all list and status subscriptions (ADR 0003, `openspec/specs/sync-protocol/spec.md`). Media never uses the WebSocket: audio is served over HTTP with range requests, video over HLS, both through signed URLs (ADR 0015).

Status: draft – nothing built yet. The normative message schema is generated from the server's pydantic models; client types live in `packages/api-types`.

## Envelope

```json
{ "type": "delta", "sub": "s12", "seq": 184467, "data": { } }
```

| Field | Required | Meaning |
|---|---|---|
| `type` | always | message type (see below) |
| `sub` | subscription-bound messages | subscription ID chosen by the client |
| `seq` | messages carrying a change | global change sequence number |
| `data` | per type | payload |

Clients and servers ignore unknown optional fields and unknown message types they do not need; such additions do not change the protocol version.

## Message types

| Type | Direction | `data` |
|---|---|---|
| `hello` | client → server | `protocol`, `token` (access token), `device_id`?, `last_seq`? |
| `welcome` | server → client | `protocol`, `current_seq`, `oldest_seq` |
| `auth` | client → server | `token` – renewed access token for the open connection |
| `subscribe` | client → server | `stream`, `params`, `since`? (newest `seq` the client has for this list), `start`, `end` (initial window) |
| `unsubscribe` | client → server | – |
| `window` | client → server | `start`, `end` – new visible window (+ buffer) by position |
| `snapshot_meta` | server → client | `total`, `counters`; envelope `seq` = feed position the snapshot is based on |
| `chunk` | server → client | `chunk` (number), `start` (position of the first row), `rows` |
| `ack` | client → server | `chunk` – chunk received (backpressure) |
| `delta` | server → client | `op` (`upsert` or `remove`), `id`, `key` (sort key), `row`?, `total`, `counters`? (subscriptions with counters); envelope `seq` |
| `resync` | server → client | – the client drops its cached rows; `snapshot_meta` and the window follow |
| `error` | server → client | `code`, `message`; connection stays open |

The first message must be `hello` within 10 seconds; the access token is never accepted in the URL.

Deltas are upserts or removals by `id` and must be applied idempotently: a delta may repeat a state that the snapshot already contained (changes committed shortly before the subscription are numbered after it).

## Windows and jumps

Clients request rows by position (`start`, `end`, end exclusive, at most 1,000 rows). The server answers in chunks of 200 rows, the requested window first; a new `window` replaces the previous one. To serve any position without `OFFSET`, the server keeps **anchors** per subscription – the sort key at every 1,000th position, computed in the database on demand (only every 1,000th key is returned) – and reads from the nearest anchor with keyset pagination. At most 4 chunks per subscription are unacknowledged.

## Close codes

| Code | Meaning | Client reaction |
|---|---|---|
| `4401` | access token expired | refresh token, reconnect, resume |
| `4426` | protocol version not supported | ask the user to update |

## Counters

`snapshot_meta.data` = `{ "total": n, "counters": { … } }`. The counter keys of each subscription type are defined by the owning domain's spec (e.g. jobs: `running`, `failed`; review: count per type and status). All values come from maintained counters, never from counting rows on request. Every `delta` of a subscription with counters carries the current `counters` along with `total`, so counter displays stay live without a new snapshot.

## Service availability

The stream `services` (all signed-in users, no parameters) lists the services the installation uses – currently the tagger – with `status` (`available`, `unavailable`, `incompatible`), `version`, `interface` and `message`; counters per status. Every server process checks the services and stores status changes with a change-log entry, so all connections receive the same deltas. Clients use it to hide features of unavailable services.

## Library lists

Seven streams for all signed-in users serve the library, plus a report and a storage summary for admins and the identification summary (`openspec/specs/library/spec.md`). The two entry streams deliver the one row of an artist or release (for page headers and deep links); the lists are one index range scan each; the sort keys are normalized (no case, no diacritics) and stored on the listed rows, and they compare bytewise on both engines (collation `"C"` on PostgreSQL). Row types are published with the message schema (`LibraryArtistRow`, `LibraryReleaseRow`, `LibraryTrackRow` in `packages/api-types`).

| Stream | Params | Sort key | Total | Counters |
|---|---|---|---|---|
| `library.artists` | – | sort name, id | artists | all four |
| `library.releases` | – | album artist sort name, title, id | releases | all four |
| `library.artist` | `artist_id` | id (one entry) | 1, or 0 if unknown | – |
| `library.release` | `release_id` | id (one entry) | 1, or 0 if unknown | – |
| `library.artist.releases` | `artist_id` | title, id | the artist's release count | – |
| `library.release.tracks` | `release_id` | disc number, track number, id | the release's track count | – |
| `library.tracks` | – | artist sort name, title, album title, id | tracks | all four |
| `library.superseded` (admins) | – | path, id | superseded files | `superseded_files`, `superseded_bytes`, `superseded_managed_files`, `superseded_managed_bytes` |
| `library.identification` (editors, admins) | – | one summary row | 1 | recordings per identification outcome |
| `library.storage` (admins) | – | one summary row | 1 | `referenced_files`, `referenced_bytes` (active referenced originals) |
| `quality_analysis.summary` (editors, admins) | – | one summary row | 1 | active originals per quality status and unanalysed |
| `library.maintenance` (admins) | – | started, id (newest first) | maintenance runs kept (the newest 30) | – |
| `library.maintenance.findings` (admins) | `run_id` | path | the run's findings | the run's counts and sizes |
| `review.items` (editors, admins) | `status`, `type`, `origin`, `confidence` | confidence, created, id | entries matching the filter | `status.*`, `type.*` |
| `tagging.changes` (editors, admins) | – | created, id (newest first) | change sets | `pending_writes`, `failed_writes` |
| `tagging.conflicts` (editors, admins) | `status`, `field`, `release_id`, `artist_id`, `source` | confidence, created, id | conflicts matching the filter | `status.*` |
| `playback.state` | – | one row (the queue of this device) | 1, or 0 before the first start | – |
| `playback.queue` | `generation` | position, id | the queue's entries | – |
| `sources.services` | – | configuration order, id | configured source services | `available` |
| `search.artists`, `search.releases`, `search.tracks` | `q`, optional `release_id` or `artist_id` | rank bucket, list order, id | matches, capped at 10,000 | `capped` (1 above the cap) |

The four library counters are `artists`, `releases`, `tracks` and `recordings`; all are maintained in the writing transaction. Track rows show the recording's active original with its effective quality and quality status (both null until analysed; the effective quality only after a high-confidence result); superseded files (kept after a better file replaced them; rows carry their `storage_mode`, and only managed ones can be deleted, ADR 0021) appear only in `library.superseded`. A change that alters what other rows show or sort by (e.g. an artist rename) writes one change entry per affected row, so each of them receives a delta. The filtered lists ignore changes of rows outside their filter; when a row leaves a filtered list, the library writes an extra entry of type `release.moved` or `track.moved`, which the list of the former parent answers with `remove`.

## Library maintenance

`library.maintenance` lists the maintenance runs (`MaintenanceRunRow`: trigger, status `running`/`done`/`held`/`reported`/`failed`, options, safety limit, and files and bytes per class – orphans, leftovers, missing originals – and per outcome – deleted, listed). Every step of a run writes one change entry for the run, so the row follows live. `library.maintenance.findings` lists one run's files (`MaintenanceFindingRow`: kind, size, outcome) by path; findings are written and updated in batches with one change entry per finding (`openspec/specs/library/spec.md`, Maintenance result). The schedule and options are read and changed over REST (`/api/v1/maintenance/schedule`).

## Review list

The stream `review.items` (editors and admins) lists the entries of the review list (`openspec/specs/review/spec.md`) of one status, optionally of one type, origin and confidence (params `status` – default `open` –, `type`, `origin`, `confidence`). Rows (`ReviewItemRow`) are ordered by confidence (high first), creation time and id and carry the producer's display values (`summary`: subject, current and proposed value), the typed `evidence` and `proposal` of the entry type (their schemas are published under `parts` in the message schema, e.g. `RecordingMatchEvidence`), the decision (user name, time, `note`), the answers of a type with two (`choices`) and whether the type can be applied right now (`applicable`). Counts come from maintained counters per type, origin, confidence and status: `total` is the filtered count, `counters` holds `status.<status>` (other filters applied) and `type.<type>` (other filters applied). Every insert and decision writes one change entry for the entry; a list answers an entry outside its filter with `remove`, so its counts follow every change. Decisions are made over REST (`POST /api/v1/review/decisions` with `ids` or a `rule`); selections and decisions that touch files run as the job `review_decision`.

## Tag editing

Edits are made over REST (`POST /api/v1/tagging/edits`: selected tracks or a list rule, fields per level – recording, release, track –, `preview` for the count; up to 50 tracks directly, more as the job `tagging_bulk`), and the tag editor reads the current values with `POST /api/v1/tagging/values` (`openspec/specs/tagging/spec.md`). The rows of the affected lists follow by the library's change entries (a recording edit reaches its tracks in every context, a release edit its album row and tracks, a move `track.moved`). The stream `tagging.changes` lists the change sets newest first (`ChangeSetRow`: kind `edit`/`undo`, user, summary of the fields, items and changed, whether it can still be undone); every change set and every change of the queue of file writes (counters `pending_writes`, `failed_writes`) writes one change entry. Undo: `POST /api/v1/tagging/changes/{id}/undo` (job `tagging_undo`, with the skipped fields in its result).

Tag conflicts (automatic values for protected fields) are review entries of type `tag_conflict` (`ReviewItemRow`, proposal `TagConflictProposal`: field and value); `review.items` leaves them out and `tagging.conflicts` lists only them, filtered by one group. The groups with their counts come over REST (`GET /api/v1/tagging/conflicts/groups?by=release|artist|field|source`, largest first); decisions and group decisions use `POST /api/v1/review/decisions` with a rule such as `{ "type": "tag_conflict", "release_id": … }`.

## Playback

Each user has one play queue per device (`openspec/specs/playback/spec.md`); both streams show the requesting user's queue on the requesting device only. `playback.state` is one row (`PlayQueueStateRow`): the queue's `generation`, the current entry with its track row (`current`), the next entry (`next_entry_id`), `position_ms`, `playing`, the number of entries and `shortened` (the last start was cut to 10,000 entries). `playback.queue` lists the entries (`PlayQueueEntryRow`: entry id, position, the `LibraryTrackRow` of the track) of one generation: replacing, renumbering or clearing the queue changes the generation instead of sending one delta per entry, and the client subscribes again with the new one. Insertions, moves and removals send deltas; track changes reach the entries through `track` events. Change entries are `play_queue` and `play_queue_entry` (scope `user`; entry IDs are integers, carried in the change entry as the UUID with that value).

The queue is changed over REST: `POST /api/v1/playback/queue` (`mode` `replace` with a `start` track, `next` or `append`; tracks as `ids` or a list `rule` like the bulk edits, taken in the list's order), `POST /api/v1/playback/skip` (`by` 1 or -1; at the end playback stops on the last entry), `PUT /api/v1/playback/state` (the client's report of current entry, position and whether it plays), `DELETE …/queue/entries/{id}`, `POST …/queue/entries/{id}/move` and `DELETE /api/v1/playback/queue`. `POST /api/v1/playback/urls` returns per entry a signed URL (one hour) of what this device receives, the delivered `format` and whether it is `transcoded` (spec: transcoding): the original (`GET /api/v1/media/originals/{id}`) or a transcode (`GET /api/v1/media/transcodes/{track_id}/{variant}`, `variant` `aac-128` … `aac-320` or `alac`). The decision uses the device's bitrate setting (`/api/v1/me/device-settings`) and the formats the device reported in `hello` (`formats`, e.g. `["aac", "flac", "mp3"]`; without a report AAC and MP3 are assumed). Requesting URLs starts the transcodes they need, so the next entry is prepared ahead. A complete transcode is served with range requests, as the copy with the track's context tags once the tagger has written it; a transcode in progress is streamed as fragmented MP4 while FFmpeg writes it (no ranges until it is complete). A URL is `null` when the track has no original or its transcode failed. Media endpoints need no auth header.

## Sources

`sources.services` lists every configured source service (`SourceServiceRow`: name, source, short name, version, capabilities, login needed and state, `available` and the `problem` of an unavailable one: `unreachable`, `incompatible`, `login_failed`, `login_missing`) for every signed-in user; clients offer only the available ones and show the problems in the source status view, which users open explicitly. Every change of a service's state writes one change entry (`source_service`). Search and links go over REST (editors, admins): `POST /api/v1/sources/search` (results per service, each with its own error, e.g. `timeout`) and `POST /api/v1/sources/resolve` (`url`, or `service` and `ref`; tracks with their duplicate status `present`, `better` or `new`). Logins: `GET`/`PUT`/`DELETE /api/v1/sources/services/{id}/login` (admins; answers with field names and the state, never the values). The source service interface itself is described in `docs/architecture/source-service-api.md`.

## Search

The search (`openspec/specs/search/spec.md`) is one stream per item type with the library's row types, so the client shows results with the library rows. `q` is the search text in the syntax of `docs/architecture/search-syntax.md`; the server parses it (`GET /api/v1/search/parse` returns the tokens with errors, which the client shows as chips and hints) and leaves out invalid tokens. The context restricts the results to one release (tracks only) or one artist (releases and tracks). Rows are ordered by rank bucket (0 whole words, 1 prefixes, 2 typo replacements), then the library list order, then id; the key is `[bucket, sort key, id]`. `total` counts at most 10,000 matches (counter `capped` is 1 when there are more) and the list ends there; every delta carries the capped count again. A change of an artist, release, track, recording or original re-evaluates the affected items: an item that matches is upserted, any other is removed (also items that were not listed, which clients ignore). Typing re-subscribes; search results are not kept in the local cache. A search is also a bulk-edit rule: `{ "list": "search", "q": …, "release_id": … }` selects all matching tracks without the cap.

## Library imports

The stream `library_import.imports` (admins, no parameters) lists the folder imports newest first (`created_at`, `id`; total = number of imports) with status (`scanning`, `reported`, `importing`, `done`, `cancelled`, `failed`), mode, whether the originals will be managed, whether replaced managed originals are deleted (`delete_replaced`), and the stored report: files and bytes per category, the storage the import adds and, after the import, the imported and failed files (`openspec/specs/library-import/spec.md`). Every status or report change writes one change entry, so the row is updated by a delta; job progress comes from the `jobs` streams.

## Change sequence and visibility

- One global, monotonically increasing change sequence covers shared data, personal data, jobs and devices.
- Each change log entry has a scope: `SHARED` (all users), `USER` (owner only), `DEVICE` (one device only).
- The server sends a delta only to connections that subscribed to the affected data and may see it.

## Several server processes

Change sequence numbers are assigned after commit by a single sequencer (outbox pattern, PostgreSQL advisory lock), so they appear in commit order. Every server process reads the numbered change log and delivers deltas to its own connections; clients may be connected to any process. Several processes require PostgreSQL.

## Resume and retention

- `hello` carries the client's last change sequence. If it is within the change log retention (default 7 days), the server sends the missed deltas.
- Otherwise each subscription receives `resync`, then `snapshot_meta` and the rows of the visible window.
