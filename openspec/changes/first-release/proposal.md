# Proposal

## Why

Milestones 1 to 3 (without the desktop and mobile apps) are implemented, and the Raumfeld output needs a check against real speakers, which needs an installable version. There is none yet:
- the published images are tagged `latest` only on a version tag, while `deploy/` installs `:latest`, so the documented installation cannot be followed today;
- `THIRD_PARTY_LICENSES.md` is a placeholder, and no tool or CI job keeps it current;
- the images carry no license texts, and the app shows neither its version nor its licenses;
- there is no changelog and no release page.

ADR 0004 plans a review of the license separation by an open-source license expert before the first public release; it has not happened yet.

## What Changes

- **Version 0.1.0 as a pre-release:** GitHub release marked "pre-release", with a notice in the README and the release notes (not for production use, license review pending). The first regular release follows the review.
- **One version, checked:** server (`pyproject.toml`), client (`package.json`) and tag must agree; a version tag whose version differs fails the release. Images carry the version and the commit; the app shows both.
- **Third-party licenses from the lockfiles:**
  - `tools/licenses/` generates sections 1 (server) and 2 (client) of `THIRD_PARTY_LICENSES.md` from `server/uv.lock` and `pnpm-lock.yaml` (production dependencies).
  - A CI job fails when the file is out of date or when a server or client dependency has a GPL, AGPL or unknown license that is not on a reviewed exception list.
- **License texts in the images:** `LICENSE`, `THIRD_PARTY_LICENSES.md` and the license texts of the server's and the client's production dependencies are under `/app/licenses` in the server image; the tagger image carries its own.
- **"About Anthology" in Settings:** versions of server and client, the commit, the license (MIT), the source link, and the third-party licenses.
- **Release workflow:** a version tag creates the GitHub release (pre-release while the version is below 1.0 or marked so) with the section of `CHANGELOG.md` for that version; images are published as today.
- **Packages for Docker and Podman:**
  - The images are GitHub Packages of the repository (ghcr.io, public, linked through the `source` label).
  - Each release also carries two installation packages as release assets, with the image tags pinned to the release: `anthology-<version>-compose.tar.gz` (Docker or Podman Compose) and `anthology-<version>-quadlet.tar.gz` (Podman Quadlet).
- **User manual on GitHub Pages** (new ADR 0023), modelled on the manual of the OEA project:
  - VitePress (Vue) in `manual/`, English as the default and German under `/de/`.
  - Four parts: General (introduction), Installation and administration, User guide, and the Source service API.
  - Screenshots of the app are taken by Playwright walkthrough tests against the real server with generated data, in both interface languages.
  - CI publishes one manual per release under `/vX.Y/`, the newest at the root, and the state of `main` under `/next/`; a version selector lists the releases.
- **Docs:** `CHANGELOG.md` (Keep a Changelog) with 0.1.0; `docs/releasing.md` (checklist); `docs/install.md` names pinned versions and how to update, and points to the manual.

## Capabilities

### New Capabilities

_None._

### Modified Capabilities

_None._ Release process, license documentation and an informational page; no specified behavior changes. `skip_specs: true`.

## Impact

- **Code:** `server/anthology/api/about.py` (version, build, license texts), client settings page "About", `tools/licenses/`, `manual/` (VitePress site, walkthrough tests).
- **CI:**
  - a `licenses` job (in the `server.yml` and `client.yml` path filters);
  - a release job in `images.yml` (release page and installation packages);
  - `pages.yml` (walkthrough screenshots, manual build, publication to the branch `gh-pages`).
- **Dependencies:**
  - none for the license tool: it uses the standard library, and `pnpm licenses` is built in;
  - `vitepress` (MIT) as a development dependency of the manual; Playwright is already used for the end-to-end tests.
- **Docs:** README, `CHANGELOG.md`, `docs/releasing.md`, `docs/install.md`, `THIRD_PARTY_LICENSES.md`, roadmap, ADR 0023, and `AGENTS.md` (German content allowed in `manual/de/`).
