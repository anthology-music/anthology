# Agent notes

Shared working memory for AI coding agents (Claude Code, opencode and others).
Agents do not use a tool-specific memory for this repository; anything worth remembering
across sessions goes here, so every agent and every maintainer sees the same state.

## How to use this file

- Read it at the start of a session, after `AGENTS.md`.
- Update it when a session ends with a new state: finished or started work, a decision
  the maintainer made in conversation, a working convention, a pitfall.
- Keep entries short and current. Delete what is no longer true instead of appending corrections.
- Do not duplicate what the repository already records: behavior belongs in `openspec/specs/`,
  decisions in `docs/adr/`, plans in `docs/roadmap.md`, history in git.
  Link to those instead.
- English only, like everything else in the repository. No credentials, no personal data.

## Current state

_Last updated: 2026-10-18_

- **Milestone 1 (Foundation)** is implemented: server skeleton, sync protocol with progressive
  loading, users and devices, jobs (core and view), client foundation with sign-in, sync layer and
  virtual list, tagger service and client, runnable pod with multi-arch images and CI smoke tests
  (archived changes in `openspec/changes/archive/`, last merge PR #14 `pod-and-ci`).
- **Open changes** in `openspec/changes/` are mostly spec work from the concept phase; their
  implementation tasks wait for the milestone they belong to. Partially implemented:
  - `signed-media-urls` – signing, revocation and WebSocket token renewal done; protecting the
    media endpoints (2.2), client URL refresh (3.1) and Raumfeld output URLs (3.2) wait until
    those endpoints and the output adapter exist.
  - `external-source-services` – documentation done; the generic service source adapter (3.1)
    and the duplicate check before download (3.2) belong to milestone 3.
  - `media-delivery-wording` – only the audio extraction from videos (2.1) is open (video, milestone 4).
- **Library:** `library-core` is merged (PR #15). Decided with the maintainer: one artist per
  recording and one album artist per release, with the credited text kept as display text.
- **Library views:** `library-views` is merged (PR #16).
- **Open, implemented in part:** `managed-and-referenced-originals` (PR #17 merged): storage
  mode and original status, file operation guard, replacement of a referenced original,
  active-original resolver and the `library.superseded` report are done. Open until their
  features exist: 2.3 (tag writes, with `tag-editing`), 4.1, 4.2 and 5.1 (import modes and
  adoption, with `library-import`). Replacing a managed original is refused until acquisition
  has checksum-verified file handling (`effective-quality-duplicate-checks`).
- **Open, implemented in part:** `metadata-lookup` (PR #18 merged): license check, lookup clients
  with cache, cross-process rate limit, priorities, mirror with fallback and the status/estimate
  endpoint are done. Open: 2.4 (the refresh job applies changes through tagging, so it waits for
  `tag-editing`). A message broker was considered for the limiter and rejected (see its design).
- **In progress:** change `recording-identification` on branch `feat/recording-identification`:
  identification job (ISRC, then fingerprint at AcoustID), outcome per recording with counters,
  `external_refs`, admin view in the settings, own LGPL FFmpeg with Chromaprint/KissFFT in the
  server image (ADR 0020); PR #20, CI green. Open: 5.1 (fuzzy suggestions) waits for
  `review-list`, so the change stays open after merging.
- **Next:** `library-import`, `effective-quality-duplicate-checks`, `review-list`,
  `tag-editing` and `search` (see `docs/roadmap.md`).

## Working conventions

- One OpenSpec change per branch and pull request; branch name `feat/<change-name>`.
- Implementation commit (`feat(<domain>): …`), then a separate archive commit
  (`chore(specs): archive <change-name>`) on the same branch before merging.
- Fixes found during CI go into the same branch as `fix(<scope>): …` commits.

## Notes and pitfalls

- `.claude/CLAUDE.md` and `*.local.md` are git-ignored and private; never reference them.
- If `openspec` is not on the `PATH`, run it as `npx -y @fission-ai/openspec@latest …`.
- On PostgreSQL a change committed just before a subscription is numbered after it, so the
  first delta may repeat the snapshot state. Protocol tests must wait for the delta with the
  expected content, not take the first one.
- Playwright's Chromium needs system libraries that a dev container may lack. Without
  installing them, run the browser in a container and connect to it:
  `podman run -d --rm --network host --init mcr.microsoft.com/playwright:v<version>-noble
  npx -y playwright@<version> run-server --port 3333 --host 127.0.0.1`, then run the E2E tests
  with `PW_TEST_CONNECT_WS_ENDPOINT=ws://127.0.0.1:3333/` (version = `@playwright/test`).
- The E2E demo-list test jumps to row 250,000; keep `ANTHOLOGY_E2E_DEMO_ROWS` at its default.
- SQLite "database is locked" in tests: a task cancelled during a write leaves its connection
  checked out with an open transaction until it is garbage-collected. `clean_db` runs
  `gc.collect()` first; tests that shut down an app and then write must do the same.
- Killing a PostgreSQL test run leaves its backend running (e.g. a `COPY` of the 500,000-track
  seed); the next run then blocks or crawls. Terminate leftover sessions first:
  `select pg_terminate_backend(pid) from pg_stat_activity where datname='anthology-test'`.
- Bulk loads on PostgreSQL after a small load: the planner keeps sequential-scan plans for the
  foreign key checks from the small tables' statistics, so the load becomes quadratic (the
  500,000-track seed took over 16 minutes in CI). `seed_library` runs ANALYZE after its first
  batch; do the same in any other bulk load.
- Foreign keys with `ON DELETE SET NULL`/`CASCADE` need an index on the referencing column;
  without it, deleting many rows scans the referencing table once per row.
- Right after a bulk load PostgreSQL has no statistics; avoid correlated `UPDATE`s over large
  fresh tables (compute values while loading instead).
- `pkill -f <pattern>` also matches the shell running it when the pattern is in the command.
