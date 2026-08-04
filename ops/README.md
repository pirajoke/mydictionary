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

Both scripts are standalone entrypoints. The deployer uses only the standard
library in its bootstrap environment; each candidate release installs its own
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

The PostgreSQL target is passed to `pg_dump` through `PGDATABASE`, not the
process argument list. Credentials, admin secrets, local paths, logs, backup
files, heartbeat files, and release state never belong in the repository.

See [the production runbook](../docs/runbooks/mac-mini-deployment.md) before
installing, enabling, clearing quarantine, or recovering a failed release.
