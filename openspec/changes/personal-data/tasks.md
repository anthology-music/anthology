# Tasks

## 1. Documentation and data model

- [x] 1.1 Add `personal-data` to the domain table in AGENTS.md (server module `personal_data`) and the domain list in `openspec/config.yaml`; add smart playlists to `docs/roadmap.md`; verify all three files
- [x] 1.2 Update `docs/architecture/data-model.puml`: `Playlist.visibility`, `PlaylistFolder`, `PlaylistEntry.positionKey` and `addedBy`, entry → track context, generic `Favorite` target, `PlayHistory.deviceId`, `PlayStats`; verify the diagram renders without errors on the PlantUML server
- [x] 1.3 Align the data model with the design (`PlaylistEdit`, `PlayHistory` zone, `PlayQueue.countedEntryId`) and document the streams in `docs/architecture/sync-protocol.md`; verify the diagram renders

## 2. Playlists (server, pull request 1)

- [x] 2.1 Migration `0024` and `server/anthology/personal_data/` with playlists, visibility, owner-only operations and folders; verify with API tests for private, shared and owner-only actions
- [x] 2.2 Implement fractional position keys with tie-break and rebalancing; verify with a test of concurrent inserts at the same position producing the same order
- [x] 2.3 Implement playlist subscriptions with counts first and keyset paging, scoped deltas for private and shared playlists (including a change of visibility); verify with a protocol test and a 20,000-entry performance test
- [x] 2.4 Implement M3U8 export and M3U/M3U8/PLS/XSPF import with unmatched report; verify with tests using generated playlist files
- [x] 2.5 Undo of playlist edits (author or owner, `changed_since`) and the queue rule `playlist`; verify with tests for an undone removal on a shared playlist, a refused undo and playing a playlist the user cannot see (refused)

## 3. Favorites and history (server, pull request 1)

- [x] 3.1 Implement favorites for recordings, releases and artists (works wait for change `works`); verify with tests that favorites are private
- [x] 3.2 Implement play recording from queue positions with the 50 %/4-minute threshold, for devices and zones, and maintained `PlayStats` including imported counts; verify with tests for skip, threshold, a zone play and imported counts
- [ ] 3.3 (waits for the iTunes import) Map imported ratings ≥ 4 stars to favorites in library-import; verify with a test on a generated iTunes export
- [ ] 3.4 (waits for `works`) Favorites for works; verify with a test that a favorite work is private

## 4. Client (pull request 2)

- [ ] 4.1 Create `client/src/features/personal-data/` with playlists (folders, sharing toggle, drag-and-drop ordering, added-by display, undo), favorites and history; verify with component tests and an E2E test of two users editing a shared playlist

## Workflow follow-up

- Archive the change once 3.3 and 3.4 are done (or moved to the changes that build the iTunes import and works) and verify `openspec validate --all --strict` passes.
