# Proposal

## Why

The works domain is specified only in outline: works, relations, recordings of works and external registers, without editing, persons, a list, MusicBrainz works or search. The navigation item "Works" leads to an empty page. Milestone 4 starts here: wind-band members need to see which originals a medley contains, play them, and find every arrangement a song appears in. Favorite works (`personal-data` 3.4) and the search filters `work`, `arranger` and `grade` wait for this domain.

## What Changes

- **works:**
  - Works with title, type (original, arrangement, medley, adaptation), credits, instrumentation, grade, duration, MusicBrainz work ID and ISWC; editors and admins create, edit and delete them.
  - **Persons:** composers, lyricists and arrangers are persons, not text. A person has a name, a sort name and a MusicBrainz artist ID where known. Editors rename and merge persons, and a person's page lists their works by role.
  - Relations "arrangement of", "medley contains" (ordered) and "part of", edited by editors; no work contains itself.
  - Recordings linked to works by editors; a medley recording may belong to several works.
  - **Works from MusicBrainz:** a job fetches the works of identified recordings, with ISWC and credits, and links them without review (a hard identifier). It runs after identifications, once for the existing library, and with the periodic refresh. Values a person set are never overwritten.
  - Works list with counts per type, progressive like every list; the work page as in `docs/design/mockups/Werk.html` (originals with play actions, "Acquire" for originals missing from the library, recordings of the work, "Contained in").
- **search:** works become searchable items; filters `work:`, `arranger:` and `grade:` become available; the search can be restricted to a work.
- **personal-data** (open change): favorite works (its task 3.4) are implemented here; its requirement already covers works.
- The user manual gets a page on works in English and German, with screenshots.

## Capabilities

### New Capabilities

_None._

### Modified Capabilities

- `works`: works, persons, relations, recordings, MusicBrainz works, works list and navigation.
- `search`: works as searchable items, the filters `work`, `arranger` and `grade`, search in a work.

## Impact

- **Domains:** works, search; uses library (recordings), metadata-lookup (MusicBrainz, periodic refresh), jobs, personal-data (favorites), sources (the "Acquire" action opens the source search), sync-protocol (list subscriptions).
- **Data model:** `Work` gains `sortTitle`; `Person`, `WorkCredit` (work, person, role, position); `WorkRelation` and `RecordingWork` with origin; `Recording.worksCheckedAt`; field provenance for works. A migration is needed.
- **Docs:** data model, `docs/architecture/sync-protocol.md` (works streams), user manual (both languages), `server/AGENTS.md`.
- **Dependencies:** none.
- **Non-functional requirements (2 s, 500,000 tracks):** the works list and a person's works use keyset pagination and counters like the library lists; work pages load their sections as separate streams. The MusicBrainz job adds two requests per new work to the shared rate limit; with 500,000 recordings the backfill takes days on the public API and is estimated in the lookup status like the identification.
