# AGENTS.md – Anthology

Instructions for AI coding agents (Claude Code, opencode and others) working in this repository.
`CLAUDE.md` files only import this file; keep all shared rules here.

## Project

Anthology is an open-source, self-hosted music application built as one integrated product:

- **Streaming** view: acquire music (CD, library import, upload; Tidal, Spotify, YouTube through optional source services in separate repositories) – audio only or video.
- **Local** view: listen to and edit the shared library (tags, works, sheet music).
- Server–client architecture: clients only send orders; the server does the work in the background.
- Multi-room playback (Teufel Raumfeld first) through exchangeable output adapters.
- Works, arrangements and medleys for wind bands, with publishers and sheet music.

Background and rationale: `docs/concept/anthology-six-pager.md`. Decisions: `docs/adr/`. Data model: `docs/architecture/data-model.puml`. UI reference: `docs/design/`. Use cases and user stories: `docs/requirements/`. Order of work and deferred topics: `docs/roadmap.md`. Current state and next steps: `docs/agent-notes.md`.

## Language

- **Conversation:** reply in the language the user writes in.
- **Everything in the repository is English:** code, identifiers, comments, commit messages, specs, ADRs and documentation.
- **Exception:** files named `*.local.md` (e.g. a maintainer's German concept notes in `docs/concept/`) are private, git-ignored working notes. They may be in any language, are never the source of truth and must not be referenced from committed files.
- **Exception:** the German pages of the user manual in `manual/de/` (ADR 0023).
- UI texts: via i18n only; German is the first UI language, English second.

## User manual

The user manual in `manual/` (VitePress, ADR 0023) has the same pages in English (root) and German (`manual/de/`).

- A change with user-visible behavior updates the affected pages in both languages in the same pull request, and the walkthrough (`manual/walkthrough/`) when screens change.
- Address the reader directly ("you", the informal "du"); quote interface labels as the interface shows them in that language.
- Screenshots come only from the walkthrough (generated data) and are not committed; pages show them with `<Screenshot name="…" alt="…" />`.
- `docs/` stays the contributor documentation; the Source service API part includes `docs/architecture/source-service-api.md`.

## Spec-driven workflow (OpenSpec)

The source of truth for behavior is `openspec/specs/<domain>/spec.md`.

1. Before implementing anything that changes behavior, read the affected specs.
2. New or changed behavior needs an OpenSpec change in `openspec/changes/<change-name>/`
   (proposal, design if needed, tasks, delta specs). Use the `opsx` commands
   (`/opsx:propose`, `/opsx:apply`, `/opsx:archive`; in opencode `/opsx-propose` etc.).
3. Implement only what the change's tasks describe; tick tasks off as you go.
4. Archive the change when done so the specs reflect the new state.
5. Pure refactorings and bug fixes that restore specified behavior need no change proposal.

Requirements use **SHALL/MUST**; every requirement has at least one `#### Scenario:` with **WHEN/THEN**.

## Shared agent notes

`docs/agent-notes.md` is the shared working memory for all agents (Claude Code, opencode and others):
current state, next steps, working conventions and pitfalls. Read it at the start of a session and
update it when the state changes. Do not use a tool-specific memory for this repository.

## Domains – one name everywhere

| Spec (`openspec/specs/`) | Server module (`server/anthology/`) |
|---|---|
| `library` | `library` |
| `sources` | `sources` |
| `jobs` | `jobs` |
| `sync-protocol` | `sync` |
| `transcoding` | `transcoding` |
| `playback` | `playback` |
| `users` | `users` |
| `works` | `works` |
| `publishers` | `publishers` |
| `sheet-music` | `sheet_music` |
| `video` | `video` |
| `library-import` | `library_import` |
| `quality-analysis` | `quality_analysis` |
| `cd-import` | `cd_import` |
| `review` | `review` |
| `tagging` | `tagging` |
| `search` | `search` |
| `personal-data` | `personal_data` |
| `covers` | `covers` |
| `metadata-lookup` | `metadata_lookup` |
| `offline` | `offline` |

Client feature folders use the same names (kebab-case) under `client/src/features/`.

## Architecture principles (do not break)

- **One original per recording.** Album folders reference it (symlink/hardlink/reflink). Never store a second copy of the same recording.
- **Metadata comes from the database, by context.** Tags shown or delivered depend on the album/context; managed originals only carry neutral base tags, referenced (imported, unmanaged) files are written only if the user enabled it.
- **Effective quality, not declared quality,** drives ranking, replacement and transcoding. Never upscale.
- **Everything is an adapter:** sources, outputs (playback), publishers. New integrations implement the adapter interface; no special cases in core code.
- **Progressive loading through all layers:** keyset pagination in the DB (never `OFFSET`), async generators on the server, chunked WebSocket subscriptions with deltas, virtual scrolling in the client. The UI must never wait for a full list.
- **Long work runs as a job** (download, import, tagging, OMR, analysis) and reports progress live. Clients may disconnect at any time.
- **Media is served over HTTP, never over the WebSocket:** audio with range requests, video adaptively over HLS.
- **Library is shared, settings are personal** (per user and per device).

## Non-functional requirements

- Current view interactive in **≤ 2 s** (95th percentile); first data from local cache in < 300 ms.
- Must handle **500,000 tracks**. Test with the generator in `tools/`.
- Performance budgets are enforced in CI; a pull request that breaks them fails.

## Repository layout

```
openspec/        specs (truth) and changes
server/          Python, FastAPI – see server/AGENTS.md
client/          Vue 3 + Quasar (web/PWA, Tauri desktop, Capacitor mobile) – see client/AGENTS.md
packages/        shared packages, e.g. api-types generated from the server's OpenAPI
services/        separate containers with their own licenses:
                 tagger (GPL-2.0+, mutagen), audiveris (AGPL-3.0)
                 (source services for streaming services live in separate repositories, ADR 0017)
deploy/          Podman Quadlet files (primary) and compose.yaml (Podman/Docker)
docs/            concept, architecture, ADRs, design
manual/          user manual (VitePress, English and German), published on GitHub Pages
tools/           test data generator, scripts
```

## Commands

```
# server
cd server && uv sync && uv run pytest && uv run ruff check . && uv run ruff format --check .

# client (pnpm workspace at the repository root)
pnpm install && pnpm lint && pnpm test && pnpm build

# tagger service (needs ffmpeg for the generated test media)
cd services/tagger && uv sync && uv run pytest && uv run ruff check . && uv run ruff format --check .

# user manual (the walkthrough needs the end-to-end setup, see manual/README.md)
pnpm --filter @anthology/manual test && pnpm --filter @anthology/manual build

# api types (after changing the server API or the sync messages; commit the result)
pnpm api-types

# specs
openspec list && openspec validate --strict

# containers (Podman)
podman build -t anthology-server -f server/Containerfile .
podman compose -f deploy/compose.yaml up
```

Run the relevant tests and linters before finishing a task.

## Git

- Conventional Commits (`feat(library): …`, `fix(sync): …`, `docs(specs): …`).
- One OpenSpec change per pull request where possible; reference the change name in the PR.
- When the tasks of a change (or of its pull request) are implemented and all checks pass (tests, linters, `openspec validate --all --strict`), commit, push and open the pull request without asking first; then watch CI and fix failures. Merging stays with the maintainer.

## License

Anthology is MIT-licensed. Do not add GPL/AGPL code or import such libraries in `server/` or `client/`.
Copyleft components run in their own container under `services/`, each with its own `LICENSE`,
and are called only through their narrow, versioned interface:

- **mutagen** → `services/tagger` (GPL-2.0-or-later). The core reads tags quickly with **tinytag** (MIT) and writes/reads full tags via the tagger.
- **streamrip** → `anthology-source-streamrip` (GPL-3.0-only), optional, separate repository (ADR 0017).
- Download tools for commercial streaming services (streamrip, spotDL, yt-dlp) are never part of this repository; they run in source services behind `docs/architecture/source-service-api.md`.
- **Audiveris** → `services/audiveris` (AGPL-3.0), optional.
- **PyMuPDF is not used** – use **pypdfium2** (BSD-3/Apache-2.0) for PDFs.
- **FFmpeg**: LGPL build, called as a separate process; no non-free encoders.

The core must keep working when optional services are absent and hide the affected features.
Check the license of every new dependency (see `docs/adr/0004-license.md`, `docs/adr/0005-containers-podman.md`).

## Containers

- Podman is the primary platform (rootless, Quadlet in `deploy/quadlet/`); Docker is supported via `deploy/compose.yaml`.
- Images are built from `Containerfile`s and are plain OCI images. Use fully qualified image names (`ghcr.io/…`, `docker.io/…`).
- All services of one installation run in one pod; only `anthology-server` publishes a port.

## Never

- Commit credentials, tokens or `.env` files.
- Add copyrighted audio, video, sheet music or cover art to the repository – tests use generated data only.
- Bypass a source's or publisher's terms of service, rate limits or robots.txt.
- Write tags into referenced (imported, not managed) files unless the user enabled it.
- Delete originals without verification (checksums) and an explicit rule or confirmation.

## CI

- Use only GitHub-hosted **standard** runners (`ubuntu-latest`, `ubuntu-24.04-arm` for arm64 images, `windows-latest`, `macos-latest`/`macos-14`); they are free for this public repository. Never use larger runners (`*-large`, `*-xlarge`).
- Never run pull-request-triggered workflows on self-hosted runners.
