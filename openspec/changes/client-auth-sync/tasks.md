# Tasks

## 1. Authentication

- [ ] 1.1 Implement the auth store, storage interface, HTTP client and single-flight refresh; verify with unit tests (refresh before expiry, concurrent requests trigger one refresh, failed refresh signs out)
- [ ] 1.2 Implement setup, sign-in and sign-out pages with route guards; verify with component tests

## 2. Sync layer

- [ ] 2.1 Implement `SyncConnection` (states, hello, auth renewal, reconnect, close codes); verify with a fake server (4401 → refresh and reconnect, 4426 → no reconnect)
- [ ] 2.2 Implement subscriptions with windows, acks, deltas, resume and resync; verify with a fake server
- [ ] 2.3 Implement the Dexie cache and cached-first display; verify that a subscription shows cached rows before the server answers and resumes with `since`

## 3. Views

- [ ] 3.1 Implement "My devices" and the admin user list on streams; verify with component tests
- [ ] 3.2 Show the real connection state and user in the navigation; verify with a component test

## 4. Verification

- [ ] 4.1 Run tests and linters; tick `signed-media-urls` 4.2; archive this change before pushing
