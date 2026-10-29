# Design

## Context

- **Images:** `images.yml` already builds both images for amd64 and arm64, smoke-tests them with Compose and Quadlet, and publishes them on `main` (`edge`, `sha-*`) and on `v*` tags (`{{version}}`, `latest`).
- **Versions:** `server/pyproject.toml` and `client/package.json` say 0.1.0; the server reports `anthology.__version__` in `/api/v1/health`.
- **Licenses:** `THIRD_PARTY_LICENSES.md` has hand-written sections 5 and 5a (services, FFmpeg, Chromaprint, fonts) and placeholders for the generated sections.

Decided with the maintainer:
- 0.1.0 is a pre-release; the regular release follows the license review;
- the license check blocks pull requests;
- the app gets an "About Anthology" page;
- the images are offered as packages for Docker and Podman;
- a user manual on GitHub Pages, published per release: VitePress, English by default and German as the second language, four parts (General, Installation and administration, User guide, Source service API), with screenshots of the app. The model is the manual of the OEA project.

## Goals / Non-Goals

**Goals:**
- An installation that follows `docs/install.md` works from published images.
- Every release states exactly which third-party code it contains, and the CI keeps that true.
- Users of the web app can see the version and the licenses.

**Non-Goals:**
- Desktop and mobile packages (they come with change `offline-sync` and the apps).
- Docker Hub: publishing there needs account credentials in CI. The images on ghcr.io work with Docker and Podman alike; Docker Hub can follow when wanted.
- A coverage check that every function is described (OEA has one against its screen list; Anthology has no such list yet). The manual's completeness is reviewed per change instead (see Definition of done).
- The legal review itself (done by an expert, outside the repository).
- Automated release-note generation from commits: the changelog is written by hand.

## Decisions

### Versions

- **One version:** `server/pyproject.toml`, `client/package.json` and the root `package.json` carry the same version.
- **Release check:** the release job fails when the tag (`v0.1.0`) differs from them.
- **Build information:** images get the build arguments `ANTHOLOGY_BUILD_COMMIT` and `ANTHOLOGY_BUILD_VERSION` (from the tag, or `edge`). The server reports them in `/api/v1/about`.
- **Client version:** Vite injects the client's version at build time (`__APP_VERSION__`), so a cached client that is older than the server is visible.

### Third-party licenses

- **Generator** (`tools/licenses/generate.py`, standard library only):
  - server: walks the production dependencies of `server/uv.lock` (`tomllib`) and reads their metadata and license files with `importlib.metadata` in the server environment, so no extra tool is needed;
  - client: runs `pnpm licenses list --prod --json` for the client;
  - writes sections 1 and 2 of `THIRD_PARTY_LICENSES.md` between markers, sorted, with SPDX identifiers where the package declares them.
- **Check** (`--check`): fails if the file would change, or if a license matches GPL, AGPL, SSPL or "UNKNOWN" and the package is not in `tools/licenses/exceptions.toml`. LGPL is allowed for dynamically used libraries (each such package is listed in the exceptions with a reason).
  - Each exception names the package, its license, the reason and the date it was reviewed.
- **CI job `licenses`:** runs the check on changes to lockfiles, the tool or the file.
- **License texts:** the generator also collects the license files of all listed packages into `licenses/` (git-ignored). The server image build runs it and copies `licenses/`, `LICENSE` and `THIRD_PARTY_LICENSES.md` to `/app/licenses`.
- **Tagger image:** it keeps its own `LICENSE`, and its third-party list stays in section 5.

### About page

- `GET /api/v1/about` (signed-in users) returns: the version, build commit and build version, `license: MIT`, the source URL, and whether this is a pre-release.
- `GET /api/v1/about/licenses` returns `THIRD_PARTY_LICENSES.md` from `/app/licenses` (the repository file when run from source).
- The settings page "About Anthology" shows the server and client versions and the commit, the pre-release notice, links to the source and to `LICENSE`, and the third-party licenses (rendered as text, loaded on demand).

### Release

- **Pre-release flag:** a version below 1.0.0, or a tag with a suffix (`-rc.1`), is a pre-release.
- **Notes:** the release notes are the section of `CHANGELOG.md` for the version, followed by the pre-release notice.
- **Images:** they keep their tags. `latest` points to the newest release, including this pre-release, because the documented installation needs it; `docs/install.md` also shows a pinned version (`:0.1.0`).
- **Job `release`:** runs in `images.yml` after the manifests on `v*` tags, with `contents: write`. It checks the versions and creates the release with `gh release create`.

### Packages for Docker and Podman

- **Images:** the images are OCI images on ghcr.io, used unchanged by Docker and Podman. They appear as packages of the repository through the label `org.opencontainers.image.source`, and are public; the maintainer sets the visibility once in the organisation's package settings.
- **Installation packages:** the release job attaches two archives to the release, built by `tools/release/package.sh`.
  - `anthology-<version>-compose.tar.gz` holds `compose.yaml` with the image tags set to the version, and a `README` with the three commands of `docs/install.md`.
  - `anthology-<version>-quadlet.tar.gz` holds the files of `deploy/quadlet/` with pinned tags.
  - The smoke tests already install from these files, so the packages are the tested installation.

### User manual

- **Decision (ADR 0023):** VitePress on GitHub Pages, as in the OEA project.
  - Location: a VitePress project in `manual/`, in the pnpm workspace; VitePress is MIT and uses Vue and Vite like the client.
  - Languages: English at the root, German under `/de/`. A page exists in both languages or in neither; a check (`manual/scripts/check-pages.mjs`) fails otherwise.
  - Contributor documentation stays in `docs/`. `AGENTS.md` allows German content in `manual/de/` (like `*.local.md`).
- **Parts** (navigation and sidebar in `manual/.vitepress/config.mts`):
  - **General:** what Anthology is, concepts (originals and contexts, effective quality, jobs, outputs), roles.
  - **Installation and administration:** requirements, Podman Quadlet and Compose, configuration (environment variables), first admin, users and roles, importing a collection, source services, metadata lookups, Raumfeld speakers, maintenance, backups and updates.
  - **User guide:** signing in, browsing the library, listening and the player, editing tags and the conflict list, the review list, covers and the gallery, playlists, favorites and history, downloads, playing on speakers, settings.
  - **Source service API:** for authors of source services. It includes `docs/architecture/source-service-api.md` (the interface, English, the single source) through a VitePress include, with an introduction per language. The German part has a German introduction and the English reference, so that the interface is defined in one place.
- **Tone:** the reader is addressed directly: "you" in English, the informal "du" in German. Interface labels are quoted as the interface shows them in that language.
- **Screenshots:**
  - Playwright walkthrough tests (`manual/walkthrough/`) drive the end-to-end server (`client/e2e/start-server.sh`: fresh database, generated library and import folder, fake source service, fake Raumfeld host) and the client.
  - They save each screenshot under a stable name in `manual/public/screenshots/<language>/<name>.png`, once with the German and once with the English interface. The images use generated data only, and covers are generated images.
  - Pages show them with `<Screenshot name="…" alt="…" />`. Screenshots are not committed: builds without them (pull requests, local preview) show a placeholder, and publication builds fail if one is missing.
- **Versions and publication** (`.github/workflows/pages.yml`, branch `gh-pages`):
  - a push to `main` publishes the manual under `/next/`, and at the root while no release exists, with a notice "unreleased";
  - a tag `vX.Y.Z` publishes under `/vX.Y/` (a patch release replaces its minor version) and, for the newest version, at the root;
  - `versions.json` at the root lists the releases, and a version selector reads it at runtime, so older manuals offer newer releases;
  - only the publishing job may write the branch, and only the deploy job may write to Pages; the build runs with a read-only token.
- **Definition of done:** a change with user-visible behavior updates the manual in both languages and its walkthrough screenshots in the same pull request (`AGENTS.md`).

## Risks / Trade-offs

- **`latest` on a pre-release:** installations that follow `latest` get pre-releases. That is accepted for 0.x, and the README says it.
- **License metadata is imperfect:** some packages declare licenses loosely (e.g. "BSD"). The check uses the declared text, and unknown ones go to the exception list after a manual look.
- **Reading metadata needs the installed environment:** the CI job runs `uv sync --frozen` before the check.
- **Two languages:** every user-visible change costs a second text. This is accepted; the check finds missing pages.
- **Walkthrough run time:** the walkthrough needs the full end-to-end stack and runs only for publication (main and tags), not on every pull request.

## Migration Plan

None (no schema change).
