# Design

## Context

`client/` holds only placeholders; `client/AGENTS.md` fixes the stack (Vue 3, Quasar, Pinia, vue-i18n, Vitest, ESLint, pnpm) and folder structure (`features/<domain>`, `sync/`, `components/`, `i18n/`, `styles/`). `packages/api-types` is meant to be generated from the server. Native shells are deferred to milestone 3 (maintainer decision).

## Goals / Non-Goals

**Goals:**
- One `pnpm install` at the root sets up client and packages.
- Types for REST and WebSocket messages are generated, never hand-written.
- An app shell that already follows the mockups and design tokens.

**Non-Goals:**
- Sign-in, sync layer, lists (steps 4b and 4c).
- PWA service worker and offline storage (milestone 3, with offline sync).
- Tauri and Capacitor (milestone 3).

## Decisions

### Workspace

Root `package.json` (private, `packageManager: pnpm@<version>`), `pnpm-workspace.yaml` with `client` and `packages/*`. Root scripts delegate: `pnpm --filter client …`, `pnpm --filter @anthology/api-types generate`.

### API types

`packages/api-types` (`@anthology/api-types`):

- `generate` runs `uv run --project ../../server python -m anthology.api.openapi > openapi.json` and `… -m anthology.sync.messages > sync-schema.json`, then `openapi-typescript` → `src/openapi.ts` and `json-schema-to-typescript` → `src/sync.ts`; `src/index.ts` re-exports both.
- Generated files are committed so the client builds without Python. CI regenerates them in a job with Python and Node and fails on a diff ("types up to date").

### Quasar app

Created with the official `create-quasar` template (Vite, TypeScript, Pinia, ESLint, vue-i18n) and trimmed to the project structure. SPA mode only. `src/styles/tokens.css` imports the tokens from `docs/design/tokens.css` at build time (single source of truth) and maps them to Quasar brand variables (`$primary` = accent, dark mode on). Fonts via `@fontsource/ubuntu` and `@fontsource/ubuntu-mono`, so no request goes to third parties.

### App shell

`MainLayout.vue`: left navigation like the mockup (logo, Streaming, Local, Works, Settings; connection state and user button at the bottom as placeholders), content area with page header. Routes `/streaming`, `/local`, `/works`, `/settings`; `/` redirects to `/local`. Texts only from `src/i18n/de.ts` and `en.ts`; a test enforces identical keys in both.

### Tests and CI

Vitest with `@vue/test-utils` and jsdom: layout renders the navigation in German and English; i18n key parity. `.github/workflows/client.yml` on `ubuntu-latest`: pnpm install (frozen lockfile), lint, test, build; second job checks generated API types are up to date (uv + pnpm).

## Risks / Trade-offs

- [TypeScript 7 (native compiler) and `vue-tsc` compatibility] → use the TypeScript version the Quasar template supports; upgrade later.
- [Committed generated files can drift] → CI check.
