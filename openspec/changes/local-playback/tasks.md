# Tasks

## 1. Documentation and data model

- [x] 1.1 Add `PlayQueue` and `PlayQueueEntry` to `docs/architecture/data-model.puml`; verify the diagram renders without errors with PlantUML
- [x] 1.2 Describe the streams `playback.queue` and `playback.state`, the queue operations and the media endpoint in `docs/architecture/sync-protocol.md`, and the playback module in `server/AGENTS.md`; verify with `openspec validate --all --strict`

## 2. Server

- [x] 2.1 Create `server/anthology/playback/` with `play_queues` and `play_queue_entries` (migration), order keys with renumbering, and the removal of entries of deleted tracks with their change entries; verify with tests for insert positions, renumbering and a deleted track
- [x] 2.2 Implement starting playback (`replace` with start track, `next`, `append`) from IDs and list rules in list order with the 10,000-entry cap, and the state, remove, move and clear operations; verify with API tests for every mode and rule, the cap and another device's queue
- [x] 2.3 Implement the streams `playback.queue` and `playback.state` with deltas for queue and track changes; verify with protocol tests
- [x] 2.4 Implement the signed media endpoint for originals with range requests and `POST /api/v1/playback/urls`; verify with API tests for a full and a partial request, an expired, a tampered and a revoked URL, and a missing file (`signed-media-urls` 2.2 for originals)
- [x] 2.5 Verify with a performance test on the 500,000-track generator that starting playback of all tracks answers within 2 seconds and the first queue chunk follows within the interaction budget

## 3. Client

- [x] 3.1 Create `client/src/features/playback/` with the player store (audio element, queue and state subscriptions, reporting, resume paused, previous/next, skipping unplayable and missing entries, URL renewal before expiry, Media Session); verify with unit tests using a fake audio element and a fake clock (`signed-media-urls` 3.1)
- [x] 3.2 Add the player bar and the queue panel to the main layout, and the play actions on the album page, track rows, track list and search results with "play next" and "add to queue"; verify with component tests and an E2E test that plays an imported album, seeks and resumes after a reload

## Workflow follow-up

- Tick `signed-media-urls` 3.1; note in its tasks that 2.2 is done for originals and waits for transcodes, tagged copies and HLS.
- Archive the change after review and verify `openspec validate --all --strict` passes.
