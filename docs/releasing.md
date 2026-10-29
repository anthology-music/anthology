# Releasing

How a version of Anthology is released (change `first-release`). Versions follow
[Semantic Versioning](https://semver.org/); below 1.0.0, and with a suffix (`1.2.0-rc.1`), a
version is a pre-release. Until the review of the license separation (ADR 0004) is done, every
release is a pre-release.

## Checklist

1. **Changelog:** move the entries of `## [Unreleased]` in `CHANGELOG.md` into a section
   `## [X.Y.Z] - YYYY-MM-DD` and add its link at the end.
2. **Version:** set `X.Y.Z` in `server/pyproject.toml`, `client/package.json`,
   `packages/api-types/package.json` and the root `package.json`; run `uv lock` in `server/` and
   `pnpm install`. Check: `python3 tools/release/release.py check vX.Y.Z`.
3. **Third-party licenses:** `cd server && uv run python ../tools/licenses/generate.py --check`
   (CI runs it too) and review the hand-written sections 3 to 6 of `THIRD_PARTY_LICENSES.md`.
4. **Manual:** the user manual describes the release in English and German (it is published with
   the tag; see `manual/`).
5. **Pull request:** merge the changes above into `main` with green CI.
6. **Tag:** on the merged `main`: `git tag vX.Y.Z && git push origin vX.Y.Z`.

## What the tag does

The workflow `images` (`.github/workflows/images.yml`):

1. checks that the tag equals the four versions (`version`), and stops otherwise;
2. builds the server and tagger images for amd64 and arm64, smoke-tests them with Compose and
   Quadlet, and publishes them as `X.Y.Z`, `X.Y` and `latest`;
3. creates the GitHub release (`release`): the notes are the changelog section, with the
   pre-release notice for pre-releases, and the assets are the installation packages
   `anthology-X.Y.Z-compose.tar.gz` and `anthology-X.Y.Z-quadlet.tar.gz`
   (`tools/release/release.py package`, images pinned to the release).

## After the release

- Check the release page, the images (`docker pull ghcr.io/anthology-music/anthology-server:X.Y.Z`)
  and an installation from the Compose package (`deploy/smoke-test.sh http://localhost:8400`).
- Settings › About Anthology of the installation shows `X.Y.Z` and the commit.

## Once per repository

- The packages `anthology-server` and `anthology-tagger` on ghcr.io are public (organisation ›
  Packages › package settings › visibility) and linked to this repository.
- GitHub Pages serves the branch `gh-pages` (Settings › Pages), for the user manual.
