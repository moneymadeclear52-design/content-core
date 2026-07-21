# ADR-0001: SQLAlchemy + Alembic with SQLite default (Postgres-ready)

**Status:** Accepted · July 2026

## Context
Run history, LLM usage, and content records were stored in JSON files —
unqueryable and easy to corrupt. The platform is single-operator,
single-machine, single-writer.

## Decision
Adopt SQLAlchemy ORM + Alembic migrations with **SQLite as the default
engine** (`DATABASE_URL` env override). Schema uses only portable column
types; the same code and migrations run on Postgres via
`DATABASE_URL=postgresql+psycopg://...`.

## Why not run PostgreSQL now
A database server adds an always-on process, credentials, and backup burden —
for a workload with no concurrent writers. SQLite handles this scale with
zero infrastructure. Dialect portability is preserved by SQLAlchemy, so
"switching to Postgres" is a config change, not a migration project.

## Adopt-Postgres triggers
- Multiple concurrent writers (e.g., parallel pipeline workers)
- A second machine needing shared state
- Row counts where SQLite write contention appears in practice
