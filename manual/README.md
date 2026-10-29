# Anthology user manual

The user manual of Anthology, built with [VitePress](https://vitepress.dev) and published on GitHub Pages by `.github/workflows/pages.yml` (ADR 0023). English pages live at the root of this folder, German pages under `de/`; both languages have the same pages.

## Structure

| Path | Content |
|---|---|
| `.vitepress/config.mts` | the four parts and their pages, navigation, locales |
| `.vitepress/theme/` | `Screenshot`, the version selector and the notice for unreleased builds |
| `general/`, `administration/`, `guide/`, `source-api/` | the English pages |
| `de/` | the German pages |
| `walkthrough/` | the Playwright walkthrough that takes the screenshots |
| `scripts/` | page and screenshot checks, and the publication into `gh-pages` |

A new page is added to the part list in `.vitepress/config.mts` and written in both languages; `pnpm check` fails otherwise.

## Working on the manual

```sh
pnpm --filter @anthology/manual dev      # preview with hot reload
pnpm --filter @anthology/manual test     # tests of the scripts
pnpm --filter @anthology/manual build    # page check and build (no dead links)
```

Without screenshots, pages show a placeholder.

## Screenshots

The walkthrough runs the end-to-end server (`client/e2e/start-server.sh`: fresh database, generated library, fake source service and fake Raumfeld host) and the client, prepares some data and takes every screenshot in English and German into `public/screenshots/<language>/<name>.png` (git-ignored). It needs the same setup as the end-to-end tests: uv, FFmpeg and an empty PostgreSQL database.

```sh
ANTHOLOGY_E2E_DATABASE_URL=postgresql+asyncpg://anthology:anthology@localhost:5432/anthology-e2e \
  pnpm --filter @anthology/manual walkthrough
pnpm --filter @anthology/manual check:screenshots
```

A page shows a screenshot with `<Screenshot name="player" alt="The player at the bottom of the page" />`. A new screenshot needs a step in `walkthrough/walkthrough.spec.ts`; publication builds fail when one is missing.

## Publication

- a push to `main` publishes under `/next/` (with a notice that it describes an unreleased state);
- a tag `vX.Y.Z` publishes under `/vX.Y/`;
- the site root leads to the newest release, and `versions.json` lists the releases for the version selector.
