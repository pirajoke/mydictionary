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

This is a host-local recovery control. It does not protect against loss of the
Mac mini or its storage; encrypted off-host replication requires a separate
design and approval.

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
MYDICTIONARY_PGDUMP_DATABASE=<local libpq database target>
MYDICTIONARY_BACKUP_DIR=<private local backup directory>
```

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

The PostgreSQL target is passed to `pg_dump` through `PGDATABASE`, not the
process argument list. Credentials, admin secrets, local paths, logs, backup
files, heartbeat files, and release state never belong in the repository.

See [the production runbook](../docs/runbooks/mac-mini-deployment.md) before
installing, enabling, clearing quarantine, or recovering a failed release.
