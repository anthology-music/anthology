# Proposal

## Why

The server side of milestone 1's protocol is done; the client does not exist yet. Before sign-in, the sync layer and virtual lists can be built, the client needs a workspace, generated API types, the Quasar app shell following the mockups, design tokens, i18n, and lint/test/build in CI. This is the first of three client steps (followed by `client-auth-sync` and `client-virtual-list`).

## What Changes

- pnpm workspace at the repository root (`client`, `packages/*`).
- `packages/api-types`: TypeScript types generated from the server's OpenAPI document and from the JSON Schema of the sync protocol messages; generated files are committed and CI checks that they are up to date.
- Server: `python -m anthology.api.openapi` prints the OpenAPI document without starting the app.
- Quasar app (Vite, TypeScript, Vue 3, Pinia, Vue Router, vue-i18n with German first and English second), web/SPA only; native shells follow in milestone 3.
- App shell after `docs/design/mockups/Main.html`: navigation (Streaming, Local, Works, Settings), connection state and user button placeholders, empty pages; dark theme from `docs/design/tokens.css`; Ubuntu and Ubuntu Mono self-hosted.
- ESLint, Vitest, build; CI workflow `client.yml`.

## Capabilities

### New Capabilities

_None._

### Modified Capabilities

_None._ Infrastructure only. `skip_specs: true`.

## Impact

- **Changes completed in part:** `sync-protocol-details` task 2.1 (TypeScript types).
- **Dependencies (client, all permissive):** quasar, @quasar/app-vite, @quasar/extras, vue, vue-router, pinia, vue-i18n (MIT); @fontsource/ubuntu and @fontsource/ubuntu-mono (Ubuntu Font Licence 1.0, fonts only); vitest, @vue/test-utils, eslint and plugins (MIT); typescript (Apache-2.0); openapi-typescript, json-schema-to-typescript (MIT).
- **Docs:** root AGENTS.md commands, `client/AGENTS.md`, THIRD_PARTY_LICENSES.md.
- **Non-functional requirements (2 s, 500,000 tracks):** none yet; the client is an empty shell.
