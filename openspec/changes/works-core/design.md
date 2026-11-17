# Design

## Context

- **What exists:**
  - The `works` spec in outline (works, relations, recordings of works, external registers, review candidates), and `Work`, `WorkRelation` and `RecordingWork` in the data model. No server module, no table and no client page ("Works" leads to a placeholder).
  - Recordings carry `mb_recording_id` after identification (ISRC, fingerprint, review). The MusicBrainz client (`app.state.lookups.musicbrainz`) is rate-limited and caches answers; `external_refs` drives the periodic refresh.
  - Recordings have a `composers` tag field (text list) from their files; it stays a tag and is not replaced by work credits.
  - The search index (`search_documents`) has the item types artist, release and track; the fields `arranger`, `work`, `grade` are reserved as "not available yet".
  - Favorites (`personal-data`) know recordings, releases and artists; the open change specifies works too (its task 3.4).
  - The mockup `docs/design/mockups/Werk.html` shows the works list counters and the work page.
- **Decided with the maintainer:**
  - original works come from MusicBrainz automatically, without review;
  - composers, lyricists and arrangers are persons, not text;
  - works in the search, favorite works and "Acquire" for missing originals are part of this change;
  - one pull request.

## Goals / Non-Goals

**Goals:**
- Editors can model an arrangement or medley with its originals in a few steps, and everyone can play the originals from it.
- Identified recordings get their MusicBrainz works and composers without any action.
- Works and persons are searchable and listed progressively like the library.

**Non-Goals:**
- Publishers, publications, ISMN and the LLM extractor (`publisher-adapters-core-split`); therefore no `WORK_ASSIGNMENT` review entries yet (`review-list` 3.6).
- Sheet music.
- Work-to-work relations imported from MusicBrainz (arrangement and medley relations there are sparse); editors set them.
- Undo for work edits; edits are written to the audit log.
- Merging persons with library artists: a person and an artist with the same MusicBrainz ID stay separate entities (they can be linked later).

## Decisions

### Model

- `works(id, title, sort_title, type, instrumentation, grade, duration_sec, mb_work_id unique, iswc, created_at, updated_at)`; `type` is `original`, `arrangement`, `medley` or `adaptation`.
- `persons(id, name, sort_name, mb_artist_id unique)`, with a counter `work_count`.
- `work_credits(work_id, person_id, role, position)`; `role` is `composer`, `lyricist` or `arranger`; ordered per role.
- `work_relations(id, source_work_id, target_work_id, type, position, origin)`; `type` is `arrangement_of`, `medley_contains` or `part_of`; `position` orders a medley's contents; unique per source, target and type. The data model's `sectionStart`/`sectionEnd` and `confidence` stay for the publisher candidates.
- `recording_works(recording_id, work_id, origin, created_at)`; `origin` is `musicbrainz` or `user`. A link exists or not; candidates are review entries (later), so the data model's `confirmed` is dropped.
- `work_tombstones` remembers removed MusicBrainz works, credits and links (see Refresh).
- `recordings.works_checked_at` marks recordings whose MusicBrainz works were fetched.
- Field provenance (`field_provenance`, entity type `work`) records which work fields a person set.
- Counters for the works list (`all`, per type) are kept in a `work_counters` row per type, maintained with every insert, type change and delete.

### Editing and rights

- Editors and admins create, edit and delete works, credits, relations and recording links, and rename and merge persons. Every signed-in user sees them.
- A person is created by name when an editor credits a new name; the editor can choose an existing person instead (search by name). A person without any credit is deleted.
- **Merging persons:** the credits of one person move to the other; a MusicBrainz artist ID moves with them if the target has none, and two different IDs refuse the merge.
- **Cycles:** a relation that would make a work contain or arrange itself (directly or through other relations) is refused.
- Deleting a work removes its credits, relations and recording links, not the recordings. A work from MusicBrainz that is deleted leaves a tombstone (see Refresh), so the refresh does not bring it back.

### Works from MusicBrainz

- Job `works_fetch`, one item per batch of 20 recordings:
  1. `GET /ws/2/recording/{mbid}?inc=work-rels` – the recording's `performance` relations give the works (a medley recording links to several).
  2. For each new work: `GET /ws/2/work/{mbid}?inc=artist-rels` – title, ISWCs (the first one), and the `composer`, `lyricist`, `writer` (as composer and lyricist) and `arranger` relations with the artist's MBID, name and sort name; persons are found or created by MBID.
  3. Links are written with origin `musicbrainz`; `works_checked_at` is set.
- **When:** after an identification sets `mb_recording_id` (the identification job and accepted review entries enqueue the recordings), once per installation for the existing library (backfill at start, as for covers), and with the periodic refresh (`external_refs`, entity type `work`).
- **Refresh:** fills fields that are empty or still from MusicBrainz, adds new credits and links. Fields with person provenance are kept, and a work, credit or recording link a person removed is not added again: removals of MusicBrainz data are remembered in `work_tombstones(kind, mb_work_id, mb_artist_id?, recording_id?)`.
- **Priority:** background, below interactive lookups; the queued requests count into the lookup status estimate (`register_backlog`).
- **Without MusicBrainz** (lookups not configured or unreachable), the job items fail retryably like the identification.

### Works list, pages and streams

New sync streams (`docs/architecture/sync-protocol.md`):

| Stream | Params | Order | Total | Counters |
|---|---|---|---|---|
| `works.list` | `type`? | sort title, id | works of the type | `all`, `original`, `arrangement`, `medley`, `adaptation` |
| `works.work` | `work_id` | id (one entry) | 1 or 0 | – |
| `works.work.contents` | `work_id` | position, id | the medley's or arrangement's originals | – |
| `works.work.recordings` | `work_id` | artist sort name, title, id | linked recordings | – |
| `works.work.containers` | `work_id` | sort title, id | works that contain or arrange it | – |
| `works.recording` | `recording_id` | sort title, id | the recording's works | – |
| `works.persons` | – | sort name, id | persons | – |
| `works.person.works` | `person_id` | role, sort title, id | the person's credits | – |

- Rows carry what the mockup shows: for an original in a medley, whether it is in the library and its best quality, from the linked recordings.
- All lists use keyset queries on indexed sort keys, like the library lists.

### Navigation

- **Work page:** header (type, instrumentation, grade, duration, credits), "Originals" (for medleys and arrangements; play when in the library, else **Acquire**), "Recordings of this work", "Contained in", favorite mark.
- **Acquire** opens Streaming with the source search filled with the original's first composer or performer and its title; nothing is ordered automatically.
- **Recordings:** the album page's track menu and the player show "Works" for a linked recording; a person's page lists their works by role.

### Search

- The index gets the item type `work`: text from title, credits and instrumentation; filter columns `composer` (composers), `arranger`, `work` (title) and `grade`.
- Tracks get the folded titles of their recordings' works in the `work` column, so `work:Nordlicht` finds the recordings of that work.
- `composer:` applies to tracks (their tag) and works (their credits). `arranger:` and `grade:` apply to works only; `work:` to tracks and works.
- The search context gains `work_id` (the recordings of a work), as for album and artist.
- Index updates follow the work, credit and link changes in the same transaction (`before_commit`), as for the library.

### Favorites

`FavoriteKind.WORK` (task 3.4 of `personal-data`); the work page and the works list show the mark. Favorites stay private.

### Client

- Feature folder `client/src/features/works/`: works list with type tabs and counters, work page, person page, editor dialogs (work fields, credits with person picker, relations with ordered originals, recording links through the library search), and the "Works" entries on track rows and in the player.
- UI texts in German and English.

### Progressive loading

DB: keyset indexes on `(sort_title, id)`, `(type, sort_title, id)`, `(work_id, position, id)` and the person's `(role, sort_title, id)`. Server: async generators per stream. Protocol: chunked snapshots with deltas from the change feed. Client: virtual lists for the works list, persons and recordings of a work.

### Dependencies

None.

## Risks / Trade-offs

- **Backfill duration:** two requests per new work on the public API (one per second); a large library needs days, as the identification does. The lookup status shows the estimate and recommends the mirror.
- **MusicBrainz credits are uneven:** popular songs have composers, many recordings have no work at all. Editors fill gaps; nothing blocks on missing works.
- **Persons and artists separate:** a composer who also performs appears once as artist and once as person. Accepted until a later change links them by MusicBrainz ID.

## Migration Plan

One Alembic migration with the new tables, `recordings.works_checked_at`, the search columns `arranger`, `work`, `grade` and the work counters; the search index version is raised so tracks are re-indexed with their works. The backfill job starts after the migration.
