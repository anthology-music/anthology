# ADR 0010: PostgreSQL in production, SQLite for development

- Status: Accepted
- Date: 2026-10-09

## Context

Anthology must handle 500,000 tracks with concurrent background jobs, several clients, full-text and fuzzy search, while staying easy to develop and test.

## Decision

- **PostgreSQL** is the production database (concurrent writes, full-text search, `pg_trgm` fuzzy search).
- **SQLite** is used for development, tests and very small installations.
- Access through SQLAlchemy 2 async; schema changes through Alembic migrations.
- Keyset pagination and maintained counters are mandatory (ADR 0003).

## Consequences

- SQL must stay portable between both engines, or engine-specific code is isolated behind repository functions.
- The pod includes a PostgreSQL container (ADR 0005).
- Performance tests run against PostgreSQL.
