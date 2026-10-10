# Tasks

## 1. Documentation and data model

- [x] 1.1 Amend ADR 0001: `anthology-publishers` holds only publisher-specific code plugins and profiles; generic adapters are in the core; verify the ADR states both
- [x] 1.2 Amend ADR 0011: in-process plugins (publishers) are loaded from the plugin volume `/data/plugins` via entry points; verify the ADR names the volume and the license constraint
- [x] 1.3 Add `Publisher.profileRef : String [0..1]` to `docs/architecture/data-model.puml`; verify the diagram renders without errors on the PlantUML server

## 2. Core adapters

- [ ] 2.1 Implement the generic adapters (structured data, HTML selectors, CSV/Excel import) as built-in entry points in `server/anthology/publishers/`; verify with tests against generated fixture pages and catalogues
- [ ] 2.2 Hide and skip the LLM extractor when no provider is configured; verify with a test that it is neither selectable nor called

## 3. Profiles and plugins

- [ ] 3.1 Implement profile import from file or URL with `profileRef`, inactive until a successful test search, and update with diff; verify with tests for import, activation gate and update
- [ ] 3.2 Load code plugins from `/data/plugins` at startup and mark publishers whose plugin is missing as unavailable; verify with tests for present and removed plugins

## Workflow follow-up

- Archive the change after review and verify `openspec validate --all --strict` passes.
