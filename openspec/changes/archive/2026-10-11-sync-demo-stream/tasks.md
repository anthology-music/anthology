# Tasks

## 1. Implementation

- [x] 1.1 Implement the CLI `anthology dev seed-demo` with the safety check; verify with a test that seeding without `ANTHOLOGY_DEV_DEMO=true` is refused and that seeding 10,000 rows produces 10,000 rows
- [x] 1.2 Implement and register the `demo.items` stream behind `ANTHOLOGY_DEV_DEMO`; verify with protocol tests that it is available only with the flag
- [x] 1.3 Add the performance test (500,000 rows, PostgreSQL): counts and first window ≤ 2 s, jump to row 250,000 ≤ 2 s at p95; verify it passes locally and in CI
- [x] 1.4 Document seeding and enabling the demo in `server/AGENTS.md`; verify the section exists

## 2. Verification

- [x] 2.1 Run the full test suite on SQLite and PostgreSQL and the linters; archive this change before pushing
