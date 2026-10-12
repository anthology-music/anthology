# Tasks

## 1. Decisions and documentation

- [x] 1.1 Write ADR 0019 (originals on the file system; binary tag data and caches behind a `BlobStore`, file system by default, S3-compatible adapter later) and add the S3 adapter to `docs/roadmap.md` (Later); verify links between ADRs 0005, 0008 and 0019
- [x] 1.2 Update `docs/architecture/data-model.puml` (`Image.blobKey`, `TranscodeCacheEntry.blobKey`); verify the diagram renders on the PlantUML server
- [x] 1.3 Write `docs/architecture/tagger-api.md` (endpoints, errors, neutral fields and their mapping per format, write semantics, versioning) and update `services/tagger/README.md`
- [x] 1.4 Move the requirement "Tagger service interface" out of change `tag-editing` (delta spec, proposal, design, task 3.2); verify `openspec validate --all --strict`

## 2. Tagger service

- [x] 2.1 Project skeleton in `services/tagger` (uv, FastAPI, mutagen, Pillow, ruff, pytest), configuration, path restriction and `GET /v1/health`; verify with tests for allowed, forbidden and symlinked paths
- [x] 2.2 Test fixtures generated with FFmpeg and Pillow (FLAC, MP3, M4A AAC and ALAC, Ogg Vorbis, Opus); verify all formats are generated in a test session
- [x] 2.3 `POST /v1/tags/read` with neutral fields, audio properties, raw keys, image descriptors and extraction by content hash; verify round trips and per-file errors (missing, corrupt, unsupported) in one batch
- [x] 2.4 `POST /v1/tags/write` with field semantics (keep, remove, replace all, images), `atomic` and `in_place` modes, hardlink refusal and journal recovery; verify hardlinks are kept, atomic writes to hardlinked files are refused, and killed writes leave old or new state
- [x] 2.5 `POST /v1/tags/copy`; verify the copy's tags and the unchanged checksum of the source
- [ ] 2.6 `Containerfile` (non-root, port 8410, volumes as in Quadlet/Compose); verify the image builds and answers health (by the maintainer on the host with Podman)

## 3. CI and verification

- [ ] 3.1 CI workflow `tagger.yml` (standard runner, FFmpeg from apt, ruff, pytest); verify it passes
- [ ] 3.2 Run all tests and linters; archive this change before pushing
