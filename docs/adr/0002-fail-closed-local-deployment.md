# ADR-0002: Fail-closed local release deployment

**Status:** Proposed

**Date:** 2026-08-04

## Context

MY DICTIONARY runs a Telegram poller and an administration service from one
versioned release on a Mac mini. PostgreSQL schema changes are applied with
Alembic. The previous local deployer treated a running launchd process as
healthy and could reactivate old code after a newer schema revision had been
applied. A failed release could then be retried on every timer interval.

Process liveness is not sufficient: Telegram polling can be blocked while the
process remains alive. A database migration also changes the rollback boundary.
Restoring code is reversible; restoring a database can discard writes and
requires an explicit operator decision.

## Decision

Use one version-controlled release state machine with two paths:

1. **Unattended code-only deploy.** Accept only fast-forward `origin/main`
   revisions with no protected vocabulary changes and with a candidate Alembic
   head equal to the live database revision. Prove launchd state, exact release
   heartbeat, expected access mode, heartbeat freshness, and loopback HTTP
   health before recording success.
2. **Explicit operator deploy.** Permit reviewed content and migrations only
   through `--operator-deploy`. Stop application services and create a validated
   PostgreSQL custom-format backup before applying a migration. After migration
   execution starts, never reactivate older code automatically. Record enough
   local recovery metadata to support a separately approved fix-forward or
   database restore.

Deterministic candidate failures and runtime readiness failures are quarantined
by commit SHA. A quarantined revision is not retried until an operator clears
that exact SHA. Network fetch and database availability failures are not
classified as candidate failures and therefore do not permanently quarantine
otherwise valid code.

The admin launcher is versioned with the deployer. It derives `RELEASE_SHA`
from the active symlink, shares `DATA_DIR` with the bot, binds only to loopback,
refuses to enable AI, and passes secrets only through the child environment.

## Options considered

### Restore old code after every failure

Low implementation complexity, but unsafe when the database revision changes.
This option caused the original compatibility failure and is rejected.

### Require a manual deploy for every commit

Safe but operationally expensive. It also leaves code-only observability fixes
waiting on routine host access. This remains available by leaving the timer
disabled, but it is not the target steady state.

### Split unattended and operator paths

More state and tests are required, but the rollback policy matches the actual
reversibility boundary. This option is selected.

## Consequences

- A green GitHub check is necessary but not sufficient; the host repeats tests
  in the isolated candidate release.
- Content and schema releases pause for a separately approved operator deploy.
- Code-only readiness failures automatically return to old code only after the
  database revision is proven unchanged.
- A migration failure may leave services stopped or the candidate unhealthy.
  This is intentional fail-closed behavior; the recovery record and backup are
  used for an explicit fix-forward or restore decision.
- Autodeploy remains disabled until the versioned wrappers are installed and a
  separately approved production acceptance test succeeds.
