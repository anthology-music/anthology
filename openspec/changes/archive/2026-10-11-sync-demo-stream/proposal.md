# Proposal

## Why

The interaction budget (2 seconds at 500,000 rows) and jumps to arbitrary positions must be verified before the library exists, and the maintainer wants a large list to test virtual scrolling in the client by hand. This is the third of three steps of the sync protocol (after `change-feed-sequencer` and `sync-protocol-core`).

## What Changes

- Command line `anthology` with `dev seed-demo --rows N` that creates and fills a demo table outside the migrations.
- Demo stream `demo.items`, registered only with `ANTHOLOGY_DEV_DEMO=true`.
- Performance test on PostgreSQL with 500,000 rows: counts and first window within 2 seconds, jump to row 250,000 within 2 seconds.

## Capabilities

### New Capabilities

_None._

### Modified Capabilities

_None._ No behavior of a production installation changes; the requirement "Jump to a position" (from `sync-protocol-core`) is verified at full scale. `skip_specs: true`.

## Impact

- **Code:** `anthology/cli.py`, `anthology/sync/demo.py`; `[project.scripts]` entry `anthology`.
- **Docs:** `server/AGENTS.md` (how to seed and enable the demo).
- **CI:** the performance test runs in the PostgreSQL job.
- **Non-functional requirements (2 s, 500,000 tracks):** verified for the protocol layer.
