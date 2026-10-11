# Design

## Context

`sync-protocol-core` provides streams, windows and anchors; the library (milestone 2) does not exist yet. See proposal.md for the motivation.

## Goals / Non-Goals

**Goals:**
- A realistic large list for manual client tests and an automated performance test.
- No trace of the demo in production installations.

**Non-Goals:**
- The 500,000-track library generator in `tools/` (milestone 2).

## Decisions

### Demo table outside the migrations

`demo_items(id UUID PK, artist, title, year, sort_artist)` in a separate `MetaData`, created by `anthology dev seed-demo --rows N [--reset]`. Rows are generated deterministically (seeded random from word lists), inserted in batches of 10,000. Index `(sort_artist, title, id)` for keyset pagination. The model comparison test ignores it because it is not part of `Base.metadata`.

### Stream registration

`create_app()` registers `demo.items` only if `settings.dev_demo` is true. The stream is readable by every signed-in user; counts come from `count(*)` once per subscription (acceptable for a demo; production streams use maintained counters).

### Command line

`[project.scripts] anthology = "anthology.cli:main"`, built with argparse (no new dependency). `seed-demo` refuses to run unless `ANTHOLOGY_DEV_DEMO=true` is set, so it cannot be run against a production database by accident.

### Performance test

Marked `@pytest.mark.performance`, runs only with `ANTHOLOGY_TEST_DATABASE_URL` (PostgreSQL) and is skipped on SQLite. It seeds 500,000 rows once per session, then measures over the WebSocket: subscribe → `snapshot_meta` and first window; `window` at 250,000 → chunk. Budget: 2 seconds each.

## Risks / Trade-offs

- [Seeding 500,000 rows slows the PostgreSQL test job] → batched inserts (a few seconds); seeding only when the table is not already filled with the expected count.
- [Timing tests are noisy on shared CI runners] → generous budget equal to the specified 2 seconds, measured on the 95th percentile of 5 runs.
