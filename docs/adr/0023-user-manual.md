# ADR 0023: A bilingual user manual with VitePress on GitHub Pages

- Status: Accepted
- Date: 2026-10-29

## Context

Anthology is installed and run by people who do not read the source: a household admin and the people who listen. The documentation in `docs/` is written for contributors (concept, ADRs, architecture) and is English only. Users need a manual that explains installation, administration and daily use with pictures of the app, in their language, and that matches the version they run. The maintainer's main audience speaks German; the project language is English. The OEA project publishes such a manual with VitePress on GitHub Pages.

## Decision

- **Tool:** a VitePress site in `manual/`, a package of the pnpm workspace. VitePress (MIT) uses Vue and Vite like the client, renders Markdown and has local search and locales built in.
- **Parts:** General, Installation and administration, User guide, Source service API. The part and page list lives in `manual/.vitepress/config.mts`.
- **Languages:** English at the root, German under `manual/de/`. Every page exists in both languages or in neither; `manual/scripts/check-pages.mjs` fails otherwise. This is the one place in the repository where German content is committed (`AGENTS.md`).
- **Source service API:** the interface stays defined once, in `docs/architecture/source-service-api.md`; the manual includes it in both languages (English text, with a German introduction).
- **Screenshots:** a Playwright walkthrough (`manual/walkthrough/`) drives the end-to-end server with generated data only and saves each screenshot under a stable name per interface language. Screenshots are not committed: pull-request builds show placeholders; publication builds run the walkthrough and fail if a screenshot is missing.
- **Publication:** `.github/workflows/pages.yml` publishes to the branch `gh-pages`, which GitHub Pages serves: `main` under `/next/`, a tag `vX.Y.Z` under `/vX.Y/` (a patch release replaces its minor version). The site root leads to the newest release (or to `/next/` before the first one), and `versions.json` feeds the version selector at runtime. Builds of `main` show a notice that they describe an unreleased state.
- **Definition of done:** a change with user-visible behavior updates the affected pages in both languages and, where the interface changed, the walkthrough, in the same pull request.

## Consequences

- Users get a manual for the version they run, with up-to-date pictures of the real app.
- Every user-visible change costs a second text; the page check and reviews keep the languages aligned.
- Publishing needs the full end-to-end stack (about the run time of the end-to-end tests); pull requests only build the site.
- The interface language of the client can be switched per device, which the walkthrough uses for the English screenshots.
