# Tasks

## 1. Documentation and data model

- [ ] 1.1 Update `docs/architecture/data-model.puml` (`Work.sortTitle`, `Person`, `WorkCredit`, `WorkRelation` and `RecordingWork` with origin, `WorkTombstone`, `Recording.worksCheckedAt`, `FavoriteKind.WORK`) and add the works streams to `docs/architecture/sync-protocol.md`; verify the diagram renders without errors on the PlantUML server

## 2. Server

- [ ] 2.1 Migration and `server/anthology/works/` models (works, persons, credits, relations, recording links, tombstones, counters); verify with model tests and `alembic check` on SQLite and PostgreSQL
- [ ] 2.2 Editing API for works, credits (person picker, new persons by name), relations (order, cycle check) and recording links, with rights, field provenance and audit log; persons rename and merge; verify with API tests including a listener's edit (refused), a cycle (refused), a merge with different MusicBrainz IDs (refused) and removal of persons without credits
- [ ] 2.3 Sync streams `works.list` (with counters), `works.work`, `works.work.contents`, `works.work.recordings`, `works.work.containers`, `works.recording`, `works.persons`, `works.person.works`, with deltas; verify with stream tests and a keyset performance test on generated data (20,000 works)
- [ ] 2.4 Job `works_fetch` (recording work relations, work credits and ISWC, persons by MBID) after identifications and accepted review entries, backfill once per installation, periodic refresh with provenance and tombstones, lookup backlog; verify with tests on recorded MusicBrainz answers, a medley recording, an edited title, a removed link and a run without MusicBrainz (retried)
- [ ] 2.5 Search: item type `work`, filters `work`, `arranger`, `grade`, `composer` on works, the work context and re-indexing of tracks with their works; verify with search tests for each filter and the context, and the search performance test at 500,000 tracks
- [ ] 2.6 Favorite works (`personal-data` 3.4, tick it there); verify with a test that a favorite work is private
- [ ] 2.7 Update `server/AGENTS.md` and regenerate the API types; verify `pnpm api-types` leaves no diff

## 3. Client

- [ ] 3.1 `client/src/features/works/`: works list with type tabs and counters, work page (originals with play and Acquire, recordings, Contained in, favorite), person page; verify with component tests
- [ ] 3.2 Editor dialogs for works, credits, relations with ordered originals and recording links, and person rename and merge; verify with component tests including the cycle message
- [ ] 3.3 Works in track menus and the player, works in the search results and the work context; verify with component tests
- [ ] 3.4 End-to-end test: create a medley with two originals from the library and one missing, play an original, open Acquire, link a recording; verify it passes in CI

## 4. User manual

- [ ] 4.1 Page "Works" in the user guide in English and German (list, work page, editing, MusicBrainz works, persons, search filters), the walkthrough with the screenshots `works`, `work` and `work-editor`, and the roles table; verify the manual check, the build and the walkthrough

## Workflow follow-up

- Archive the change after review and verify `openspec validate --all --strict` passes.
- Then `personal-data` waits only for 3.3 (iTunes).
