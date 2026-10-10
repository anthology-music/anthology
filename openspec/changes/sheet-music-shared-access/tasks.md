# Tasks

## 1. Documentation and data model

- [x] 1.1 Remove `SheetPermission` and its relations from `docs/architecture/data-model.puml`; verify the diagram renders without errors on the PlantUML server and contains no `SheetPermission`
- [x] 1.2 Add a note on operator responsibility for sheet music (legal conditions, restricting access to the installation) to README.md; verify the note is in the README

## 2. Implementation

- [ ] 2.1 Require sign-in for all sheet endpoints and list all sheets of a work for every signed-in user; verify with API tests for anonymous (rejected) and signed-in (all parts listed) access
- [ ] 2.2 Log sheet downloads in the audit log; verify with a test that a download creates an entry with user and time

## Workflow follow-up

- Archive the change after review and verify `openspec validate --all --strict` passes.
