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

_Last updated: 2026-10-28_

- **Milestone 1 (Foundation)** is implemented: server skeleton, sync protocol with progressive
  loading, users and devices, jobs (core and view), client foundation with sign-in, sync layer and
  virtual list, tagger service and client, runnable pod with multi-arch images and CI smoke tests
  (archived changes in `openspec/changes/archive/`, last merge PR #14 `pod-and-ci`).
- **Open changes** in `openspec/changes/` are mostly spec work from the concept phase; their
  implementation tasks wait for the milestone they belong to. Partially implemented:
  - `signed-media-urls` – signing, revocation and WebSocket token renewal done; protecting the
    media endpoints (2.2), client URL refresh (3.1) and Raumfeld output URLs (3.2) wait until
    those endpoints and the output adapter exist.
  - `media-delivery-wording` – only the audio extraction from videos (2.1) is open (video, milestone 4).
- **Library:** `library-core` is merged (PR #15). Decided with the maintainer: one artist per
  recording and one album artist per release, with the credited text kept as display text.
- **Library views:** `library-views` is merged (PR #16).
- **Archived:** `managed-and-referenced-originals` (PR #17); 2.3 (tag writes into referenced
  files) was done with `tag-editing`. Replacing a managed original by a better acquisition is
  covered by `effective-quality-duplicate-checks` (CD import and sources).
- **Archived:** `metadata-lookup` (PR #18; the refresh 2.4 was done with `tag-editing`). A
  message broker was considered for the limiter and rejected (see its design).
- **Archived:** `recording-identification` (PR #20), `library-import-folders` (PR #21) and
  `quality-based-replacement` (PR #24); their last tasks were done with `review-list`.
- **Open, implemented in part:** `quality-analysis-core` (PR #22 merged). Open: source
  plausibility (`sources`), lossless reduction. The automatic analysis after imports was removed
  again (ADR 0022).
- **System maintenance:** `system-maintenance` is merged (PR #25): job schedules (`job_schedules`,
  scheduler task per process, installation time zone `ANTHOLOGY_TIME_ZONE`) and the library
  maintenance job with grace period and safety limit.
- **Open, implemented in part:** `review-list` (PR #26 merged). Open: producers of
  works/publishers, sources and sheet-music (3.6–3.8).
- **Archived:** `tag-editing` (PR #27, #28; 3.3 with `context-tags-on-delivery`). Decided with
  the maintainer: genres per recording; changing the album of selected tracks moves them.
- **Archived:** `search` (PR #29). Decided with the maintainer: library items only (artists, albums, tracks; album and artist context); works,
  videos, playlists and their filters join with their domains (`docs/roadmap.md`); offline
  search moved to `offline-sync`; the server is the only parser of the syntax.
- **Archived:** `local-playback` (PR #30): listening in the browser. Decided with the maintainer: originals only until transcoding
  (milestone 3), the queue lives on the server (one per user and device), play history and
  counts follow with `personal-data`. `signed-media-urls` 3.1 is done; its 2.2 is done for
  originals only.
- **Archived:** `transcoding-delivery` (PR #31 and the tagged copies): transcodes by device
  bitrate and formats, streamed while written, tagged per context through the tagger. Decided
  with the maintainer: streaming, tagging now, declared quality before the analysis.
  `playable-delivery-format` 3.3 waits for the Raumfeld adapter.
- **Archived:** `source-service-adapter` (PR #33 and the orders pull request) and
  `external-source-services`: interface v1 with the fake service in `tools/fake-source-service/`,
  detection, encrypted logins (shown masked once stored), search and links with duplicate status,
  source status with reasons for every user, orders with a download job, an import that confirms
  itself, outcomes and the source per original. `effective-quality-duplicate-checks` 2.1 (CD
  import) stays open.
- **Archived:** `context-tags-on-delivery` (branch `feat/context-tags-on-delivery`): track
  downloads as cached context-tagged copies of the original, album downloads as streamed zips
  with temporary copies, WAV and AIFF in the tagger (interface 1.1). Decided with the
  maintainer: tagger extended for WAV/AIFF, copies without cover until `covers`, track and album
  downloads, every signed-in user may download.
- **Next:** see `docs/roadmap.md` (milestone 3).
  `effective-quality-duplicate-checks` covers CD import and sources only; it waits for them.

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
- No `session.begin_nested()` (savepoints): with aiosqlite they left a transaction open and
  other writers ran into "database is locked". Validate first, then write.
- `ON CONFLICT … WHERE` for a partial unique index must repeat the index predicate literally
  (`index_where=text(…)`); with bound parameters PostgreSQL finds no matching index.
- A PostgreSQL test database left at an earlier draft of a revision cannot be migrated down
  (the test session starts with a downgrade). Reset it:
  `drop schema public cascade; create schema public;`.
- Link probes and hardlinks need source and target in one mount: Linux refuses `link()` and
  reflinks across mount points (`EXDEV`), even on the same disk. Tests simulate `EXDEV`.
- SQLAlchemy `before_commit` handlers may run synchronous SQL under the asyncio extension
  (the search index uses it); select columns, not entities, there: bulk updates with
  `synchronize_session=False` leave loaded entities stale.
- Search performance at 500,000 tracks depends on narrow document rows and partial GIN indexes
  per item type; check `tests/test_search_performance.py` after changing documents or queries.
- Apps created in server tests get lookups pointed at a closed port (autouse fixture
  `offline_lookups` in `tests/conftest.py`); before, a job in a test could reach the real
  MusicBrainz and time out in CI.
- The local FFmpeg must have the `chromaprint` and `hash` muxers (build the `ffmpeg` stage of
  `server/Containerfile` with `podman build --target ffmpeg` and copy `ffmpeg`/`ffprobe` out).
  That build has no `lavfi` and no MP3/Vorbis/Opus encoders, which the tagger tests need: run
  them in a container, e.g. `python:3.12-slim` with Debian's `ffmpeg`, from a copy of
  `services/tagger` in the scratch directory (SELinux labels of the repository fail with `:Z`).
- `tests/test_health.py` downgrades the schema to base; it needs empty tables (`clean_db`).
