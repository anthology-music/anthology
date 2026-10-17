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

_Last updated: 2026-10-17_

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
- **Next:** milestone 2 (Core library), starting with `managed-and-referenced-originals`,
  then `metadata-lookup`, `effective-quality-duplicate-checks`, `review-list`, `tag-editing`
  and `search` (see `docs/roadmap.md`).

## Working conventions

- One OpenSpec change per branch and pull request; branch name `feat/<change-name>`.
- Implementation commit (`feat(<domain>): …`), then a separate archive commit
  (`chore(specs): archive <change-name>`) on the same branch before merging.
- Fixes found during CI go into the same branch as `fix(<scope>): …` commits.

## Notes and pitfalls

- `.claude/CLAUDE.md` and `*.local.md` are git-ignored and private; never reference them.
