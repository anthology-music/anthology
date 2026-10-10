# ADR 0001: Monorepo for server and all clients

- Status: Accepted
- Date: 2026-10-09

## Context

Anthology has a Python server and clients for web/PWA, desktop and mobile. All clients share the same Vue/Quasar code and the same API types.

## Decision

Server, client, shared packages, specs and docs live in one repository. Publisher adapters are the exception and live in a separate optional repository (`anthology-publishers`), so they can be removed without affecting the core if a publisher objects.

## Consequences

- API and client changes go into one pull request; API types are generated, not duplicated.
- One release produces all build targets with the same version.
- CI must build and test several targets; build times grow with the project.
