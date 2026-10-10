# AGENTS.md – client

Rules for the Vue client. The root `AGENTS.md` applies as well.

## Stack

- **Vue 3** with `<script setup lang="ts">` and the Composition API, **TypeScript** strict.
- **Quasar** (UI, PWA, build modes), **Pinia** (state), **Vue Router**, **vue-i18n** (German default, English).
- Desktop: **Tauri 2** (`src-tauri/`). Mobile: **Capacitor** (`src-capacitor/`).
- Lists: **@tanstack/vue-virtual** (or Quasar `QVirtualScroll`). WebSocket helpers: **@vueuse/core**.
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

API types come from `packages/api-types`; never hand-write request/response types.

## UI rules (from the mockups in docs/design)

- Font **Ubuntu**, numbers/bitrates/paths in **Ubuntu Mono**. Dark theme first, light theme supported. Colors only via design tokens.
- Source shown as an icon at the far left of a row; quality as a badge showing the **effective** quality.
- Status colors always come with an icon or label – never color alone. Selected rows use their own selection background, distinct from status colors.
- Edit mode: checkbox per row, highlighted selection, sticky action bar with the **count** of selected items.
- Touch targets ≥ 44 px; real `<button>`, `<a>`, `<input>`/`<label>` elements; text contrast ≥ 4.5:1.

## Data loading

- Every list is a subscription: show `snapshot_meta` counts immediately, render skeleton rows for unloaded ranges, request only the visible window (+ buffer).
- Start from the local cache, then reconcile with deltas. Show a quiet connection state (live / reconnecting / offline).
- Actions are optimistic and roll back on error. "Select all/folder" sends a rule, not thousands of IDs.
- Never block the UI while waiting for the server.
