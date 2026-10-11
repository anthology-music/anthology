# Tasks

## 1. Workspace and types

- [x] 1.1 Add the root `package.json` and `pnpm-workspace.yaml`; verify `pnpm install` succeeds at the root
- [x] 1.2 Add `python -m anthology.api.openapi` to the server with a test that it prints a valid OpenAPI document; verify the test passes
- [x] 1.3 Create `packages/api-types` with the `generate` script and commit the generated `openapi.ts` and `sync.ts`; verify the generated types contain `TokenResponse` and the `Hello`/`Delta` messages (completes the TypeScript part of `sync-protocol-details` 2.1)

## 2. Client

- [x] 2.1 Scaffold the Quasar app (Vite, TypeScript, Pinia, Router, vue-i18n) in `client/` with the project structure; verify `pnpm --filter client build` succeeds
- [x] 2.2 Add design tokens and self-hosted Ubuntu fonts; verify the build output contains no external font URLs
- [x] 2.3 Build the app shell (navigation, page headers, connection state and user placeholders) and German/English texts; verify with Vitest that the navigation renders in both languages and that both locales have identical keys

## 3. CI and docs

- [x] 3.1 Add `.github/workflows/client.yml` (lint, test, build; generated types up to date); verify the YAML parses and the jobs run green after push
- [x] 3.2 Update root `AGENTS.md` commands, `client/AGENTS.md` and `THIRD_PARTY_LICENSES.md`; verify the documented commands run as written
- [x] 3.3 Run server and client tests and linters; archive this change before pushing
