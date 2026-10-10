# Tasks

## 1. Decision and documentation

- [x] 1.1 Add ADR 0017 "Source services outside the core repository"; verify it lists the three services, their licenses and the generic interface
- [x] 1.2 Amend ADR 0001 (source services as a second exception), ADR 0004 (streamrip handled in the external Tidal repository), ADR 0005 (source service containers, configured via `ANTHOLOGY_SOURCE_SERVICES`), ADR 0006 (spotDL/yt-dlp no longer used in the server) and ADR 0011 (generic service adapter instead of thin per-service clients); verify each ADR references ADR 0017
- [x] 1.3 Create `docs/architecture/source-service-api.md` with the v1 interface from the design; verify it covers info, search, resolve, download, tasks and health
- [x] 1.4 Update AGENTS.md, server/AGENTS.md, README.md, THIRD_PARTY_LICENSES.md and openspec/config.yaml so no file describes spotDL, yt-dlp, streamrip or tidalapi as part of the core or `services/`; verify with `grep -rn "spotDL\|yt-dlp\|streamrip\|tidalapi\|source-tidal"` that remaining hits only point to the external services

## 2. Repository move (maintainer)

- [ ] 2.1 Create the repositories `anthology-source-streamrip`, `anthology-source-spotdl` and `anthology-source-ytdlp`; verify they exist with their LICENSE files
- [ ] 2.2 Move `services/source-tidal/` and `deploy/quadlet/anthology-source-streamrip.container` into `anthology-source-streamrip`, then remove them and the Tidal service and `ANTHOLOGY_TIDAL_URL` from the core repository's deploy files; verify `podman compose -f deploy/compose.yaml config` succeeds without them

## 3. Generic source service adapter

- [ ] 3.1 Implement the generic service source adapter and the `ANTHOLOGY_SOURCE_SERVICES` configuration with startup detection and version check; verify with tests against a fake service for available, unavailable and incompatible-version cases
- [ ] 3.2 Run the duplicate check on `resolve` results before `download`; verify with a test that an already present track is not requested from the service

## Workflow follow-up

- Archive the change after review and verify `openspec validate --all --strict` passes.
