# Proposal

## Why

Lists of up to 500,000 rows must scroll smoothly, show skeleton rows for unloaded ranges, and jump when the scroll bar is dragged (spec `sync-protocol`: "Jump to a position", "Interaction budget"). Third of three client steps.

## What Changes

- Reusable `VirtualList` component on top of `useSubscription`: fixed row height, visible window plus buffer, debounced window requests, skeleton rows, jumps by scroll position.
- Developer page for the `demo.items` stream (only when the server offers it).
- End-to-end tests with Playwright against the real server (sign-in, devices, demo list jump) in CI, including the interaction budget measured in the browser.

## Capabilities

### New Capabilities

_None._

### Modified Capabilities

_None._ Client side of existing requirements. `skip_specs: true`.

## Impact

- **Dependencies:** @tanstack/vue-virtual (MIT); @playwright/test (Apache-2.0, development only).
- **CI:** E2E job with PostgreSQL, server and client.
- **Non-functional requirements:** measured end to end: counts and first rows ≤ 2 s, cached rows ≤ 300 ms, jump ≤ 2 s on 500,000 rows.
