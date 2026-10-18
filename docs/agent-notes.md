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
- **In review:** change `library-views` is implemented and archived on branch
  `feat/library-views` (PR #16, CI green): Local view with the sections Albums, Artists and
  Tracks, artist and album pages, entry streams `library.artist` and `library.release`. The
  format label (`FLAC 24/96`) is deliberately not a quality badge until effective quality exists.
- **Next:** `managed-and-referenced-originals` (builds on `audio_files`: replaces its unique
  `recording_id` index with the partial index), `metadata-lookup`,
  `effective-quality-duplicate-checks`, `review-list`, `tag-editing` and `search`
  (see `docs/roadmap.md`).

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
- Foreign keys with `ON DELETE SET NULL`/`CASCADE` need an index on the referencing column;
  without it, deleting many rows scans the referencing table once per row.
- Right after a bulk load PostgreSQL has no statistics; avoid correlated `UPDATE`s over large
  fresh tables (compute values while loading instead).
- `pkill -f <pattern>` also matches the shell running it when the pattern is in the command.
