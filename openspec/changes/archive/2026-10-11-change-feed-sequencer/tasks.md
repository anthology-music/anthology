# Tasks

## 1. Documentation and data model

- [x] 1.1 Amend ADR 0003 (several server processes require PostgreSQL; outbox with sequencer; change feed) and `docs/architecture/sync-protocol.md`; update `ChangeLog` in `docs/architecture/data-model.puml` (internal `id`, nullable unique `changeSeq`); verify the diagram renders without errors on the PlantUML server

## 2. Implementation

- [x] 2.1 Migration `0003` and model change; `record_change()` without return value, with `pg_notify` on PostgreSQL; verify the migration round trip and the model comparison test on both engines
- [x] 2.2 Implement the sequencer with advisory-lock leadership; verify with tests that overlapping transactions are numbered in commit order and that only one of two app instances numbers rows on PostgreSQL
- [x] 2.3 Implement the change feed with consumers and the session cache invalidation; verify with a test that a sign-out through one app instance is rejected by another within one second
- [x] 2.4 Implement change log retention; verify with a test using old timestamps
- [x] 2.5 Start and stop the background tasks in the app lifespan; verify with a test that a change becomes numbered and delivered to a feed consumer without manual steps

## 3. Verification

- [x] 3.1 Run the full test suite on SQLite and PostgreSQL and the linters; tick task 3.1 of `sync-protocol-details`; archive this change before pushing
