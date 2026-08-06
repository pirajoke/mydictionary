# Pilot access and Telegram readiness

This release prepares a controlled learner pilot without enabling it in
production. It does not merge, deploy, call AI providers, charge credits, or
process payments.

## Access model

Every learner has one durable access state:

- `pending`: registered for the pilot, but learning commands are unavailable
- `active`: admitted to learning flows
- `blocked`: denied in allowlist, pilot, and public modes

Configured Telegram administrators are always active and cannot be restricted
from the admin console. Migration `0005_pilot_access` backfills every existing
account as active so deployment cannot accidentally remove prior access. New
learner rows default to pending.

Runtime admission is fail closed:

- `allowlist` admits only configured IDs
- `pilot` records `/start`, creates one waitlist event, and waits for admin
  approval
- `public` activates new learners automatically unless they are blocked

Access changes use a row lock and transaction. Each actual change adds a
`user_access_updated` admin audit record containing only the previous and new
state.

## Readiness model

Process liveness alone does not prove that the bot is receiving Telegram
updates. The poller writes a ready heartbeat only after a successful
`getUpdates` response. Conflict and polling errors immediately move the state
back to `starting`; graceful shutdown writes `stopped`.

The admin `/health` endpoint is ready only when both conditions hold:

1. the database probe succeeds
2. the heartbeat is valid, in `ready` state, and no older than the configured
   threshold

The heartbeat must not be published through the tunnel. Only the aggregate
health status is public; detailed reason, age, release, and access mode require
an authenticated admin session.

## Rollout sequence

1. Back up PostgreSQL and record the current release.
2. Deploy migration and code while retaining `BOT_ACCESS_MODE=allowlist`.
3. Verify bot logs, heartbeat freshness, local health, and public health.
4. Confirm existing administrator and learner access.
5. In a separately approved change, set `BOT_ACCESS_MODE=pilot` and restart the
   bot and admin service.
6. Admit a small cohort from the Users tab and monitor onboarding completion,
   block completion, polling freshness, and support reports.
7. Roll back the access mode to `allowlist` if Telegram readiness degrades or
   admission behavior is unexpected. Do not downgrade the database while the
   new code is running.

Moving to `public`, enabling AI, or accepting payment requires independent
review and production confirmation.

Release automation and schema-aware recovery are defined in
[`ADR-0002`](adr/0002-fail-closed-local-deployment.md) and the
[Mac mini deployment runbook](runbooks/mac-mini-deployment.md).
