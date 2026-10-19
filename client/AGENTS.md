# AGENTS.md – client

Rules for the Vue client. The root `AGENTS.md` applies as well.

## Stack

- **Vue 3** with `<script setup lang="ts">` and the Composition API, **TypeScript** strict.
- **Quasar** (UI, PWA, build modes), **Pinia** (state), **Vue Router**, **vue-i18n** (German default, English).
- Desktop: **Tauri 2** (`src-tauri/`). Mobile: **Capacitor** (`src-capacitor/`). Native code in `src-tauri/` uses only permissively licensed crates (CD ripping: ADR 0018).
- Sheet music: **Verovio** (LGPL-3.0) is loaded as a separate, unmodified, lazily loaded asset – never import it into application chunks (ADR 0014).
- Lists: the in-house `src/components/VirtualList.vue` on a subscription – never `QVirtualScroll` or other virtualizers for server lists: browsers cap element heights (Firefox ≈ 17.9 million px), so the list compresses its scroll area. Give its container a bounded height.
- Local cache: **Dexie** (IndexedDB) on web, SQLite on Tauri/Capacitor.
- Tests: **Vitest** + **Vue Test Utils**, E2E with **Playwright**. Lint: **ESLint** + **Prettier**. Package manager: **pnpm**.

## Structure

```
src/
  features/<domain>/   components, composables and stores per domain (same names as the specs)
  sync/                WebSocket connection, subscriptions, delta handling, local cache
  components/          shared UI components
  i18n/                translations
  styles/              design tokens
```

API types come from `@anthology/api-types` (REST: `paths`/`components` from OpenAPI; WebSocket: `ClientMessage`/`ServerMessage` from the sync protocol schema); never hand-write request/response or message types. Regenerate with `pnpm api-types` at the repository root after server changes and commit the result (CI checks it).

## Setup and commands

- pnpm workspace at the repository root: `pnpm install`, `pnpm lint` (ESLint, Prettier, vue-tsc), `pnpm test` (Vitest), `pnpm build`; `pnpm --filter client dev` for the dev server.
- Web/SPA only for now; Tauri (`src-tauri/`) and Capacitor (`src-capacitor/`) follow in milestone 3.
- Colours come from `docs/design/tokens.css`: `src/styles/tokens.css` imports it and `quasar.config.ts` reads the brand colours from it at build time. Never copy hex values.
- Fonts (Ubuntu, Ubuntu Mono) are self-hosted via `@fontsource`; the app makes no requests to third parties.
- i18n: `src/i18n/de.ts` is the reference, `en.ts` must have the same keys (tested). `src/i18n/setup.ts` creates the instance; boot files only call it, so tests can use it without Quasar CLI.
- Tests mount the whole app (`test/mount.ts`: Quasar, i18n, routes); `test/setup.ts` stubs browser APIs missing in jsdom.
- Install scripts of dependencies must be allowed explicitly in `pnpm-workspace.yaml` (`allowBuilds`).
- End-to-end tests (Playwright, `e2e/`): `ANTHOLOGY_E2E_DATABASE_URL=postgresql+asyncpg://…/<test database> pnpm --filter client e2e`. They start the real server (via uv, ports 8490) on a fresh database with the demo list (`ANTHOLOGY_E2E_DEMO_ROWS`, default 500,000) and a generated library (`ANTHOLOGY_E2E_LIBRARY_TRACKS`, default 20,000), and the client dev server (port 9090); the database must be dedicated to tests. Once per machine: `pnpm --filter client exec playwright install --with-deps chromium`.

## UI rules (from the mockups in docs/design)

- Font **Ubuntu**, numbers/bitrates/paths in **Ubuntu Mono**. Dark theme first, light theme supported. Colors only via design tokens.
- Source shown as an icon at the far left of a row; quality as a badge showing the **effective** quality.
- Status colors always come with an icon or label – never color alone. Selected rows use their own selection background, distinct from status colors.
- Edit mode: checkbox per row, highlighted selection, sticky action bar with the **count** of selected items.
- Touch targets ≥ 44 px; real `<button>`, `<a>`, `<input>`/`<label>` elements; text contrast ≥ 4.5:1.

## Data loading

- Every list is a subscription (`useSubscription`) shown with `VirtualList`: counts immediately, skeleton rows for unloaded ranges, only the visible window (+ buffer) requested, rows far outside the window dropped.
- Start from the local cache, then reconcile with deltas. Show a quiet connection state (live / reconnecting / offline).
- Actions are optimistic and roll back on error. "Select all/folder" sends a rule, not thousands of IDs.
- Never block the UI while waiting for the server.
