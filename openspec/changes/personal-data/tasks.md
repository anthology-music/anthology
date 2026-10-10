# Tasks

## 1. Documentation and data model

- [x] 1.1 Add `personal-data` to the domain table in AGENTS.md (server module `personal_data`) and the domain list in `openspec/config.yaml`; add smart playlists to `docs/roadmap.md`; verify all three files
- [x] 1.2 Update `docs/architecture/data-model.puml`: `Playlist.visibility`, `PlaylistFolder`, `PlaylistEntry.positionKey` and `addedBy`, entry → track context, generic `Favorite` target, `PlayHistory.deviceId`, `PlayStats`; verify the diagram renders without errors on the PlantUML server

## 2. Playlists (server)

- [ ] 2.1 Create `server/anthology/personal_data/` with playlists, visibility, owner-only operations and folders; verify with API tests for private, shared and owner-only actions
- [ ] 2.2 Implement fractional position keys with tie-break and rebalancing; verify with a test of concurrent inserts at the same position producing the same order
- [ ] 2.3 Implement playlist subscriptions with counts first and keyset paging, scoped deltas for private and shared playlists; verify with a protocol test and a 20,000-entry performance test
- [ ] 2.4 Implement M3U8 export and M3U/M3U8/PLS/XSPF import with unmatched report; verify with tests using generated playlist files

## 3. Favorites and history (server)

- [ ] 3.1 Implement favorites for recordings, releases, artists and works; verify with tests that favorites are private
- [ ] 3.2 Implement play recording with the 50 %/4-minute threshold and maintained `PlayStats` including imported counts; verify with tests for skip, threshold and imported counts
- [ ] 3.3 Map imported ratings ≥ 4 stars to favorites in library-import; verify with a test on a generated iTunes export

## 4. Client

- [ ] 4.1 Create `client/src/features/personal-data/` with playlists (folders, sharing toggle, drag-and-drop ordering, added-by display), favorites and history; verify with component tests and an E2E test of two users editing a shared playlist

## Workflow follow-up

- Archive the change after review and verify `openspec validate --all --strict` passes.
