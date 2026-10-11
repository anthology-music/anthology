# Tasks

## 1. Documentation and data model

- [x] 1.1 Amend ADR 0015 with signed media URLs, revocation and WebSocket token renewal (`auth` message, close code 4401); verify the ADR states all three
- [x] 1.2 Add `UserDevice.revokedAt : DateTime [0..1]` to `docs/architecture/data-model.puml`; verify the diagram renders without errors on the PlantUML server

## 2. Signed URLs (server)

- [x] 2.1 Implement URL signing and verification with key generation and rotation; verify with tests for valid, expired, tampered and rotated-key URLs
- [ ] 2.2 Protect all media endpoints (originals, transcodes, tagged copies, HLS playlists and segments) with signed URLs including range requests; verify with API tests per endpoint
- [x] 2.3 Add the revocation check with cache invalidation on device sign-out and user deactivation; verify with tests that requests fail immediately after each

## 3. Clients and outputs

- [ ] 3.1 Request and refresh signed URLs for the play queue in the client; verify with a unit test that URLs are refreshed before expiry
- [ ] 3.2 Issue output-bound URLs with queue-length expiry (max 24 h) and refresh unplayed items in the Raumfeld adapter; verify with adapter tests using a fake clock

## 4. WebSocket token renewal

- [ ] 4.1 Handle the `auth` message and close with code 4401 on expiry; verify with protocol tests for renewal and expiry
- [ ] 4.2 Refresh the token in the client before expiry, and reconnect and resume after 4401; verify with a client test that no full reload happens

## Workflow follow-up

- Archive the change after review and verify `openspec validate --all --strict` passes.
