# Tasks

## 1. Licenses (pull request 1)

- [x] 1.1 Add `tools/licenses/` (generator with `--check`, exceptions file with reasons) and generate sections 1 and 2 of `THIRD_PARTY_LICENSES.md`; replace its placeholders (status, date, version, section 7 and 8); verify the check passes and fails for a stale file and for a GPL dependency without exception
- [x] 1.2 CI job `licenses` (blocking) and license texts in the server image under `/app/licenses`; verify the job runs on lockfile changes and the image contains `LICENSE`, `THIRD_PARTY_LICENSES.md` and the collected texts

## 2. Versions and About (pull request 1)

- [x] 2.1 Build information in the images and `GET /api/v1/about` and `GET /api/v1/about/licenses`; verify with API tests (signed-in only, values from the environment)
- [x] 2.2 Settings page "About Anthology" with server and client versions, commit, pre-release notice, links and third-party licenses; verify with a component test

## 3. Release and packages (pull request 1)

- [x] 3.1 Release job on `v*` tags (version check, GitHub release from the changelog section, pre-release below 1.0) with the installation packages for Compose and Quadlet (`tools/release/package.sh`, pinned image tags); verify the version check and the packages with a test of the scripts and the job with a dry run on a branch
- [x] 3.2 `CHANGELOG.md` with 0.1.0, `docs/releasing.md`, pre-release notice in the README, `docs/install.md` (pinned versions, the packages, updating, ghcr.io packages for Docker and Podman); verify the links and that `docs/install.md` matches `deploy/`

## 4. User manual (pull request 2)

- [x] 4.1 ADR 0023 and the `AGENTS.md` rules (German in `manual/de/`, the definition of done); verify both files
- [x] 4.2 VitePress site `manual/` (English root, German `/de/`, the four parts, version selector, notice for unreleased builds, `Screenshot` component) and `check-pages.mjs`; verify the build has no dead links and the check fails for a page in one language only
- [x] 4.3 Write the pages of all four parts in English and German; the Source service API part includes `docs/architecture/source-service-api.md`; verify every page exists in both languages
- [x] 4.4 Walkthrough tests that take the screenshots in both interface languages against the end-to-end server; verify a publication build fails without a referenced screenshot and passes with the walkthrough's output
- [ ] 4.5 `pages.yml` (walkthrough, build, publication to `gh-pages` with `/next/`, `/vX.Y/`, the root and `versions.json`, least privileges); verify with a run on `main` that the site is published and the selector lists the versions

## Workflow follow-up

- The maintainer makes the ghcr.io packages public and enables GitHub Pages from the branch `gh-pages`, once.
- After both pull requests, the maintainer tags `v0.1.0`; verify the release page with both installation packages, the images `0.1.0` and `latest`, the manual under `/v0.1/` and at the root, and an installation from the Compose package.
- Archive the change after the release and verify `openspec validate --all --strict` passes.
