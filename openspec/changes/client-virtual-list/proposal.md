# Proposal

## Why

Lists of up to 500,000 rows must scroll smoothly, show skeleton rows for unloaded ranges, and jump when the scroll bar is dragged (spec `sync-protocol`: "Jump to a position", "Interaction budget"). Third of three client steps.

## What Changes

- Reusable `VirtualList` component on top of `useSubscription`: fixed row height, visible window plus buffer, debounced window requests, skeleton rows, jumps by scroll position, `aria-setsize`/`aria-posinset` per row. Built in-house instead of @tanstack/vue-virtual, because browsers cap element heights (Firefox ≈ 17.9 million px) and 500,000 rows × 52 px exceed it; the list compresses the scroll area and maps scroll position to row positions.
- Subscriptions expose server errors (e.g. `unknown_stream`) and drop rows far outside the window to bound memory.
- Developer page for the `demo.items` stream (only when the server offers it).
- End-to-end tests with Playwright against the real server (sign-in, devices, demo list jump) in CI, including the interaction budget measured in the browser.

## Capabilities

### New Capabilities

_None._

### Modified Capabilities

_None._ Client side of existing requirements. `skip_specs: true`.

## Impact

- **Dependencies:** @playwright/test (Apache-2.0, development only); no runtime dependency.
- **CI:** E2E job with PostgreSQL, server and client.
- **Non-functional requirements:** measured end to end: counts and first rows ≤ 2 s, cached rows ≤ 300 ms, jump ≤ 2 s on 500,000 rows.
