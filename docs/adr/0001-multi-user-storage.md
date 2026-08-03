# ADR 0001: Normalize Learner State in PostgreSQL

Status: accepted for stage 1

## Context

The original bot stores one learner profile in `progress.json` and spaced-
repetition counters inside shared dictionary JSON. That design cannot isolate
multiple Telegram users and cannot safely support credits or payments.

The Mac mini is the production host. The bot must preserve existing learning
behavior while paid capabilities are implemented through separate draft pull
requests.

## Decision

- Keep dictionary JSON as immutable, version-controlled content.
- Store Telegram users, aggregate progress, and word progress in normalized
  relational tables keyed by `telegram_user_id`.
- Use PostgreSQL in production through SQLAlchemy and Psycopg 3.
- Use SQLite only as a compatible local/test backend.
- Version schema changes with Alembic.
- Import the original JSON state once for the legacy owner ID.
- Bind the current learner with `ContextVar` so existing pure learning helpers
  can be migrated without one large behavioral rewrite.

## Consequences

Positive:

- Learners have isolated language, XP, streak, and spaced-repetition state.
- One answer updates its word and aggregate profile in one transaction.
- Future AI usage, ledger, and admin services can share a durable identity.
- Existing Telegram UX and block callback contracts stay stable.

Costs:

- Database migrations become part of startup and CI.
- Synchronous repository calls briefly occupy the bot event loop. This is
  acceptable for the current traffic; a worker or async repository can replace
  it if measured latency requires it.
- Word identity currently follows the stable dictionary index. Reordering a
  dictionary will require a content migration or explicit immutable word IDs.

## Rejected Options

- One JSON document per user: simple, but weak for atomic credits, reporting,
  querying, and multiple processes.
- One JSONB application snapshot in PostgreSQL: durable but still creates lost-
  update and analytics problems.
- Copy the Node storage layer from Zerkalo: it does not match the Python bot and
  retains the single-document limitation.
