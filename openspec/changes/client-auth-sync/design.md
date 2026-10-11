# Design

## Context

Server: `/api/v1/setup`, `/api/v1/auth/*`, `/api/v1/me/*`, `/api/v1/users/*`, WebSocket `/api/v1/ws` (see `docs/architecture/sync-protocol.md`). Generated types from `@anthology/api-types`.

## Decisions

- **Auth store (Pinia):** access token and expiry in memory; refresh token and device ID in `localStorage` (web) behind a small storage interface, so native shells can use secure storage later. Refresh 60 s before expiry; a single in-flight promise serialises refreshes; a 401 from refresh signs out locally.
- **HTTP client:** thin `fetch` wrapper typed with `openapi.ts` (no extra dependency); adds the bearer token and retries once after a refresh.
- **Sync connection:** class `SyncConnection` with explicit states; `hello` on open, `auth` after each refresh; reconnect with exponential backoff (0.5 s … 30 s, jitter); close codes 4401 → refresh then reconnect, 4426 → show update hint, no reconnect.
- **Subscriptions:** `useSubscription(stream, params)` returns reactive `total`, `counters`, a sparse row map by position and `setWindow(start, end)`; acks every chunk; applies deltas by `id` (upsert/remove, re-sorting within loaded windows by `key`); on resync drops cached rows.
- **Cache (Dexie):** table `rows(subKey, position, id, key, data)` and `meta(subKey, total, counters, seq)`; `subKey` = user + stream + params. On subscribe the cached window is shown immediately and `since` = cached `seq`.
- **Views:** "My devices" and "Users" use `useSubscription` and plain lists (they are small); virtual scrolling comes in step 4c.
- **Tests:** Vitest with a fake WebSocket server for the sync layer (windows, acks, deltas, resync, reconnect); component tests for setup/sign-in; one end-to-end run against the real server in CI (Playwright) is part of step 4c.
