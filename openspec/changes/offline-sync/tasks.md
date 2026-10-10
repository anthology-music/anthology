# Tasks

## 1. Documentation and data model

- [x] 1.1 Add `offline` to the domain table in AGENTS.md and the domain list in `openspec/config.yaml`; add offline video to `docs/roadmap.md`; verify all three files
- [x] 1.2 Update `docs/architecture/data-model.puml`: `UserDeviceSettings.offlineBitrate`, `OfflineSelection`, `OfflineCopy` with variant and size; verify the diagram renders without errors on the PlantUML server

## 2. Server

- [ ] 2.1 Create `server/anthology/offline/` with offline selections and copy reports; verify with API tests for marking, unmarking and listing per user and device
- [ ] 2.2 Accept queued offline changes with original timestamps (history, favorites last-writer-wins, playlist merges); verify with tests for each kind including clock clamping

## 3. Client

- [ ] 3.1 Implement the offline storage layer for Tauri, Capacitor and the PWA with shared files per recording and variant and per-user references; verify with tests that a file is removed only when unreferenced
- [ ] 3.2 Implement the sync engine with offline bitrate, limit check and warning, Wi-Fi-only rule, metered warning for transfers, resumable downloads and renewal; verify with tests using fake network states and a fake server
- [ ] 3.3 Implement the offline change outbox; verify with a test that offline plays appear with original times after reconnect
- [ ] 3.4 Create `client/src/features/offline/` UI (mark/unmark, storage usage, best-effort notice, warnings); verify with component tests

## Workflow follow-up

- Archive the change after review and verify `openspec validate --all --strict` passes.
