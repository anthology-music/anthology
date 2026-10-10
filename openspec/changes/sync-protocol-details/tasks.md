# Tasks

## 1. Documentation and data model

- [x] 1.1 Create `docs/architecture/sync-protocol.md` (envelope, message types, versioning, close codes 4401/4426, counters, global sequence, visibility, retention, resync); verify it lists every message type from the design
- [x] 1.2 Amend ADR 0003 with protocol versioning, the global change sequence and change log retention; verify the ADR references `docs/architecture/sync-protocol.md`
- [x] 1.3 Add `scope : ChangeScope`, `ownerUserId [0..1]` and `deviceId [0..1]` to `ChangeLog` in `docs/architecture/data-model.puml`; verify the diagram renders without errors on the PlantUML server

## 2. Protocol schema

- [ ] 2.1 Define the message models as pydantic discriminated unions, export JSON Schema and generate TypeScript types in `packages/api-types`; verify `pnpm --filter api-types generate` produces the message types and the client compiles
- [ ] 2.2 Implement version negotiation with close code 4426 and schema validation with `error` replies; verify with protocol tests for supported, unsupported and malformed messages

## 3. Change sequence and deltas

- [ ] 3.1 Implement the global change sequence and scoped `ChangeLog` writes in the same transaction as each change; verify with a test that concurrent changes get distinct increasing numbers on PostgreSQL and SQLite
- [ ] 3.2 Implement the change notifier and per-connection visibility filtering; verify with tests that personal and device deltas reach only their owners
- [ ] 3.3 Implement change log retention and `resync`; verify with a test using a fake clock that an outdated client is resynchronised with counts first

## Workflow follow-up

- Archive the change after review and verify `openspec validate --all --strict` passes.
