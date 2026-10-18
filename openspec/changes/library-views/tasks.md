# Tasks

## 1. Server: entry subscriptions

- [x] 1.1 Add the streams `library.artist` (parameter `artist_id`) and `library.release` (parameter `release_id`) in `anthology/library/streams.py`: total 1 or 0, the list row shape, upsert/remove deltas for the entity; register them and their row schemas; protocol tests for snapshot, unknown ID, rename delta and removal delta pass on SQLite and PostgreSQL
- [x] 1.2 Regenerate `packages/api-types` (`pnpm api-types`) and update the library streams table in `docs/architecture/sync-protocol.md`; `git diff` shows only the new stream names

## 2. Client: library feature

- [x] 2.1 Add `client/src/features/library/format.ts` (duration, format label, disc/track number) with unit tests for lossless, lossy, unknown values and multi-disc numbers
- [x] 2.2 Add `initialPosition` to `VirtualList` and the `libraryPositions` store; unit test: a list mounted with an initial position requests the window around it
- [x] 2.3 Routes under `/local` (redirect, albums, artists, artist page, album page, tracks); `LocalPage.vue` as frame with breadcrumb and `<router-view>`; test: each address renders its view, `/local` redirects to albums
- [x] 2.4 `LibraryNav` with live counts (empty-window subscription to `library.artists`) in the sidebar and as tabs on narrow screens; test with the fake server: counts render and follow a delta
- [x] 2.5 Section views for albums, artists and tracks on `VirtualList` with link rows; test: rows render from the fake server, a track row links to its release
- [x] 2.6 Artist page (header from `library.artist`, releases list) and album page (header from `library.release`, track list with credited artist only where it differs, format label, duration); "does not exist" state for unknown and removed entries; tests for header, guest credit, unknown ID and removal
- [x] 2.7 Scroll restore when returning to a section or artist page; test: going back restores the stored position
- [x] 2.8 Texts in `de.ts` and `en.ts` (same keys, existing i18n test passes); `pnpm lint`, `pnpm test` and `pnpm build` pass

## 3. End to end

- [x] 3.1 Seed a generated library in `client/e2e/start-server.sh` (`ANTHOLOGY_E2E_LIBRARY_TRACKS`, default 20,000) and document it in `client/AGENTS.md`
- [ ] 3.2 E2E test: open Local, see the counts, open an artist, open a release, reload the album page, go back and find the previous scroll position; passes locally and in CI (live deltas are covered by 1.1 and 2.4–2.6, since no library editing API exists yet)

## 4. Documentation

- [x] 4.1 Update `docs/agent-notes.md` (state, next steps) and check `docs/architecture/data-model.puml` needs no change

## Workflow follow-up

- Archive commit `chore(specs): archive library-views` after CI is green, then PR.
