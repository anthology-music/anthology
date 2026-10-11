# Tasks

## 1. Documentation

- [ ] 1.1 Amend ADR 0003 (position anchors) and update `docs/architecture/sync-protocol.md` (message fields, `since`, hello timeout); verify both documents describe anchors and `since`

## 2. Protocol

- [ ] 2.1 Implement message models and JSON Schema export; verify with tests for valid and malformed messages
- [ ] 2.2 Implement the connection lifecycle (hello timeout, version check 4426, authentication, `auth` renewal, expiry 4401, `error` replies); verify with protocol tests for each case
- [ ] 2.3 Implement the stream framework with counts first, windowed chunks, visible window first, anchors for jumps and backpressure; verify with protocol tests using a test stream with several thousand rows, including that no query uses OFFSET
- [ ] 2.4 Implement the hub with deltas, scope visibility, resume with `since` and `resync`; verify with protocol tests for live deltas, private deltas, replay after reconnect and resync after retention
- [ ] 2.5 Verify deltas across processes with two app instances on PostgreSQL

## 3. Streams

- [ ] 3.1 Implement the `me.devices` and `users` streams; verify with protocol tests including that listeners cannot subscribe to `users`

## 4. Verification

- [ ] 4.1 Run the full test suite on SQLite and PostgreSQL and the linters; tick the completed tasks in `sync-protocol-details` and `signed-media-urls`; archive this change before pushing
