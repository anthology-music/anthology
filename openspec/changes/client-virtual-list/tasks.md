# Tasks

## 1. Virtual list

- [x] 1.1 Implement `VirtualList` (fixed row height, window + buffer, debounced requests, skeleton rows, jumps); verify with component tests using a fake subscription
- [x] 1.2 Add the developer demo page for `demo.items`; verify it is hidden when the stream is not offered

## 2. End to end

- [x] 2.1 Add Playwright tests against the real server: setup, sign-in, my devices, demo list jump to row 250,000 with the interaction budget; verify locally and in CI
- [x] 2.2 Add the E2E job to CI (PostgreSQL service, server, client); verify it runs green after push

## 3. Verification

- [x] 3.1 Run all tests and linters; archive this change before pushing
