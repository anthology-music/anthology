# Tasks

## 1. Documentation and data model

- [x] 1.1 Add `covers` to the domain table in AGENTS.md and the domain list in `openspec/config.yaml`; add Pillow (MIT-CMU) to `THIRD_PARTY_LICENSES.md`; verify all three files
- [x] 1.2 Update `docs/architecture/data-model.puml`: replace `Cover` by `Image` (content hash, size, source), `ImageKind`, `ReleaseImage`, front image relations; verify the diagram renders without errors on the PlantUML server
- [ ] 1.3 Align the data model with the design (`Image.sha256` without `source`, `ReleaseImage.remoteUrl`, `Recording.frontImage`, provenance field `cover`) and document image URLs, the grant and the `cover` row field in `docs/architecture/sync-protocol.md`; verify the diagram renders

## 2. Server (pull request 1)

- [ ] 2.1 Migration `0023`, `core/blobs.py` (file system `BlobStore`) and `server/anthology/covers/` with the deduplicating image store; verify with tests that identical images are stored once and invalid images are refused
- [ ] 2.2 The `cover` field with provenance and rank (upload, removal, automatic replacement by rank, conflict for protected covers); editors and admins only; verify with tests for each rank pair, a manual cover meeting a Cover Art Archive cover (conflict with both images) and a listener's upload (refused)
- [ ] 2.3 Job `covers_fetch` (embedded images through the tagger, `source` for source downloads, Cover Art Archive front and gallery metadata), backfill once per installation, after imports and identifications and on request; verify with tests against a fake tagger and recorded Cover Art Archive answers, a run without the tagger (retried) and a resumed job
- [ ] 2.4 Gallery: entries, upload, removal, order and the download of Cover Art Archive images when the gallery is first opened; verify with API tests
- [ ] 2.5 Thumbnails (64, 256, 600; WebP and JPEG) cached with a size limit, the device grant and `GET /api/v1/media/images/{sha256}/{size}`; verify with tests for each size, a cache hit, the sweep, an expired and a revoked grant
- [ ] 2.6 The `cover` field in library rows and the playback state, the 600-pixel cover in DIDL-Lite for zones, and the 1200-pixel front cover embedded in transcodes and tagged copies (stale on cover change); verify with tests on generated images, the fake tagger and the fake Raumfeld host
- [ ] 2.7 Update `server/AGENTS.md` and regenerate the API types; verify `pnpm api-types` leaves no diff

## 3. Client (pull request 2)

- [ ] 3.1 Lazy thumbnails in album, artist and track lists, on the album page and in the player bar, with the grant renewed before expiry, and the placeholder; verify with component tests
- [ ] 3.2 Gallery on demand, cover upload and removal and gallery editing for editors, and both images in cover conflicts of the conflict list; verify with component tests
- [ ] 3.3 End-to-end test: upload a cover, see it in the album list and the player bar, open the gallery; verify it passes in CI

## Workflow follow-up

- Archive the change after review and verify `openspec validate --all --strict` passes.
