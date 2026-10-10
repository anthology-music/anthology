# ADR 0001: Monorepo for server and all clients

- Status: Accepted
- Date: 2026-10-09

## Context

Anthology has a Python server and clients for web/PWA, desktop and mobile. All clients share the same Vue/Quasar code and the same API types.

## Decision

Server, client, shared packages, specs and docs live in one repository. Two exceptions live outside, so they can be removed without affecting the core: publisher-specific code plugins and publisher profiles in a separate optional repository (`anthology-publishers`), in case a publisher objects – the publisher registry and the generic adapters (structured data, HTML selectors, CSV/Excel import, LLM extractor) stay in the core – and source services for commercial streaming services, each in its own repository (ADR 0017).

## Consequences

- API and client changes go into one pull request; API types are generated, not duplicated.
- One release produces all build targets with the same version.
- CI must build and test several targets; build times grow with the project.
