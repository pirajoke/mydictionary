# Local release tooling

The files in this directory are the version-controlled source for the Mac mini
deployment wrappers. Production copies are installed only during a separately
approved production change. Render is not part of this deployment model.

## Components

- `mydictionary_autodeploy.py` builds and validates `origin/main`, enforces the
  database/content policy, switches the `current` symlink, and proves runtime
  readiness.
- `mydictionary_admin.py` starts Gunicorn from the active release with a shared
  runtime directory and a release SHA derived from the `current` symlink.
- `mydictionary_backup.py` creates and verifies private PostgreSQL
  custom-format backups independently of a deployment.

All scripts are standalone entrypoints and use only the standard library in
their bootstrap environment. Each candidate release installs its own
application dependencies before tests run.

## Deployment modes

The default command is unattended and accepts only a fast-forward, code-only
release whose single Alembic head already equals the production database
revision. Readiness requires all configured launchd services, a fresh Telegram
heartbeat for the candidate SHA and expected access mode, and loopback HTTP
health for three consecutive checks.

```bash
python ops/mydictionary_autodeploy.py
```

Build and test without activation:

```bash
python ops/mydictionary_autodeploy.py --prepare-only
```

Reviewed content or schema changes require an operator invocation. If the
schema differs, this mode stops application services, creates and validates a
private PostgreSQL custom-format backup, activates the candidate, applies the
migration, and then proves readiness. Once migration execution begins, the
tool never activates older code automatically.

```bash
python ops/mydictionary_autodeploy.py --operator-deploy
```

A deterministic candidate or readiness failure is quarantined by commit SHA.
After the cause has been reviewed and corrected, clear exactly one failed SHA:

```bash
python ops/mydictionary_autodeploy.py --clear-failed <40-character-sha>
```

## Database backups

Run the backup wrapper daily from a dedicated launchd service. The default
action creates a private custom-format dump, validates it with `pg_restore
--list`, and atomically records its SHA-256, size, timestamp, and Alembic
revision in owner-only local metadata.

```bash
python ops/mydictionary_backup.py
```

The independent check is suitable for monitoring and pre-deploy gates. By
default, a verified backup is stale after 26 hours.

```bash
python ops/mydictionary_backup.py --check
```

Creation and checking never delete a backup. Retention cleanup is an explicit
operator action that first validates every deletion candidate, preserves at
least 30 days and seven backups by default, and never deletes the latest backup.

```bash
python ops/mydictionary_backup.py --prune
```

This host-local recovery control can be followed by the separately gated,
encrypted off-site replication described in `docs/product-safety.md`.

## Required environment

```text
MYDICTIONARY_APP_ROOT=<local application root>
MYDICTIONARY_REPOSITORY_URL=https://github.com/pirajoke/mydictionary.git
MYDICTIONARY_SERVICE_LABELS=<bot label>,<admin label>
MYDICTIONARY_SERVICE_PLISTS=<bot plist>,<admin plist>
MYDICTIONARY_BOOTSTRAP_PYTHON=<trusted Python executable>
DATABASE_URL=<SQLAlchemy PostgreSQL URL>
MYDICTIONARY_EXPECTED_ACCESS_MODE=allowlist
MYDICTIONARY_HEALTH_URL=http://127.0.0.1:8791/health
```

The admin launcher additionally reads an owner-only JSON file from
`MYDICTIONARY_ADMIN_SECRETS` (or `admin-secrets.json` under the application
root). It must contain `username`, `password_hash`, and `session_secret` string
values. `ADMIN_COOKIE_SECURE` defaults to `true` for the public HTTPS tunnel;
the service itself still binds only to loopback.

Operator migration deploys also require:

```text
MYDICTIONARY_PGDUMP_DATABASE=mydictionary
MYDICTIONARY_BACKUP_DIR=<private local backup directory>
PGHOST=/tmp
PGUSER=<local PostgreSQL role>
```

`MYDICTIONARY_PGDUMP_DATABASE` must be a plain database name, not a PostgreSQL
URI or libpq keyword connection string. Configure the socket or host, optional
port, user, and authentication through `PGHOST`, `PGPORT`, `PGUSER`, and the
other standard libpq environment variables. Both wrappers reject a combined
connection string before stopping services or starting a backup.

Telegram Stars settings are optional and default off. A reviewed billing rollout
passes `TELEGRAM_STARS_ENABLED`, `BILLING_PAYLOAD_SECRET`,
`BILLING_SUPPORT_CONTACT`, `BILLING_TERMS_TEXT`,
`BILLING_ORDER_TTL_SECONDS`, and `BILLING_NET_MICRO_USD_PER_XTR` to both bot and
admin processes. Keep the payload secret out of plist files readable by other
users and retain it while an issued invoice may still be paid.

The scheduled backup wrapper uses the same two settings plus:

```text
MYDICTIONARY_APP_ROOT=<local application root>
MYDICTIONARY_BACKUP_RETENTION_DAYS=30
MYDICTIONARY_BACKUP_MINIMUM_COUNT=7
MYDICTIONARY_BACKUP_MAX_AGE_SECONDS=93600
MYDICTIONARY_BACKUP_MIN_FREE_BYTES=1073741824
MYDICTIONARY_BACKUP_COMMAND_TIMEOUT_SECONDS=1800
```

The retention settings are bounded in code. `MYDICTIONARY_PG_DUMP`,
`MYDICTIONARY_PG_RESTORE`, and `MYDICTIONARY_PSQL` may identify trusted local
executables when they are not available through `PATH`.

The plain PostgreSQL database name is passed to `pg_dump` through `PGDATABASE`,
not the process argument list. Credentials, admin secrets, local paths, logs,
backup files, heartbeat files, and release state never belong in the repository.

See [the production runbook](../docs/runbooks/mac-mini-deployment.md) before
installing, enabling, clearing quarantine, or recovering a failed release.

## Billing operations

`mydictionary_billing.py reconcile` is read-only and compares bounded Bot API
transaction pages with the local Stars ledger. Refund and subscription changes
require the exact local UUID plus `--execute`; the wrapper never prints tokens,
invoice payloads, Telegram charge IDs, or learner identities. Keep it on the
loopback production host and run it only after the corresponding admin record
and support decision have been reviewed.

## Product safety operations

The safety wrappers are preview-only unless `--execute` is supplied:

```bash
python ops/mydictionary_retention.py retention
python ops/mydictionary_retention.py retention --execute
python ops/mydictionary_monitor.py
python ops/mydictionary_monitor.py --execute
python ops/mydictionary_offsite_backup.py
python ops/mydictionary_offsite_backup.py --execute
```

Retention previews candidate row counts. Monitoring sends no alert and writes
no state in preview mode. Off-site backup verifies the local dump in preview
mode and invokes `age` and `rclone` only with `--execute`. See
`docs/product-safety.md` for required settings, retention boundaries, and the
restore contract.
