# Tasks

## 1. Documentation and data model

- [x] 1.1 Add `covers` to the domain table in AGENTS.md and the domain list in `openspec/config.yaml`; add Pillow (MIT-CMU) to `THIRD_PARTY_LICENSES.md`; verify all three files
- [x] 1.2 Update `docs/architecture/data-model.puml`: replace `Cover` by `Image` (content hash, size, source), `ImageKind`, `ReleaseImage`, front image relations; verify the diagram renders without errors on the PlantUML server

## 2. Server

- [ ] 2.1 Create `server/anthology/covers/` with the deduplicating image store and the `cover` tagging field with provenance; verify with tests that identical images are stored once and a manual cover creates a conflict instead of being replaced
- [ ] 2.2 Implement acquisition from embedded images, the Cover Art Archive (rate-limited, cached) and source services with the priority order; verify with tests against recorded CAA responses
- [ ] 2.3 Implement thumbnail generation and caching with signed, immutable URLs; verify with tests for each size and cache hit
- [ ] 2.4 Embed scaled front covers in transcodes and tagged copies and include the 600-px URL in DIDL-Lite; verify with tests on a generated image

## 3. Client

- [ ] 3.1 Show lazy thumbnails in lists, the gallery on demand, cover upload and the placeholder; verify with component tests and an E2E test uploading a cover

## Workflow follow-up

- Archive the change after review and verify `openspec validate --all --strict` passes.
