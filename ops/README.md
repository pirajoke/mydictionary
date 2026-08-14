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
- `mydictionary_restore_drill.py` retrieves one exact encrypted off-site object,
  restores it into a generated disposable PostgreSQL database, verifies the
  Alembic revision, removes the database, and writes a private drill receipt.

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
tool never activates older code automatically. Service shutdown waits for
launchd registration removal, and bootstrap reloads every service from its
current reviewed plist instead of kickstarting stale registration state.

```bash
python ops/mydictionary_autodeploy.py --operator-deploy
```

After a separately approved fix-forward recovery, adopt an already-running
healthy `origin/main` release with:

```bash
python ops/mydictionary_autodeploy.py --adopt-current
```

If manual recovery metadata exists, adoption verifies its release, migration
revision, backup digest, and dump readability before completing the recovery
record and clearing the hold.

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

The admin launcher can expose the authenticated one-time OpenAI key enrollment
form without receiving `OPENAI_API_KEY` in its environment. Set
`AI_KEY_ENROLLMENT_ENABLED`, `AI_KEY_ENROLLMENT_PATH`, and
`AI_KEY_ENROLLMENT_EXPIRES_AT` together. The target must be directly under the
owner-only `local-config` directory and the window cannot exceed one hour. See
`docs/admin-console.md` for the lifecycle and cleanup procedure.

Groq Voice uses the separate `GROQ_KEY_ENROLLMENT_ENABLED`,
`GROQ_KEY_ENROLLMENT_PATH`, and `GROQ_KEY_ENROLLMENT_EXPIRES_AT` window. Set
`GROQ_API_KEY_FILE` to the same absolute target under owner-only
`local-config`. The launcher validates the file without forwarding its contents
and rejects simultaneous `GROQ_API_KEY` and `GROQ_API_KEY_FILE` sources.

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
`BILLING_SUPPORT_CONTACT`, `BILLING_SELLER_LEGAL_NAME`,
`BILLING_SELLER_ADDRESS`, `BILLING_SELLER_EMAIL`,
`BILLING_SELLER_PHONE`, `BILLING_TERMS_TEXT`, `BILLING_TERMS_VERSION`,
`BILLING_TERMS_SHA256`, `BILLING_TERMS_APPROVED`,
`BILLING_ORDER_TTL_SECONDS`, `BILLING_NET_MICRO_USD_PER_XTR`, and the dated
economics settings to both bot and admin processes. Keep the payload secret out
of plist files readable by other users and retain it while an issued invoice
may still be paid.

Voice tutor settings remain optional and default off. The admin launcher passes
the reviewed voice model, limits, consent metadata, `GROQ_API_KEY_FILE`, and a
derived provider-configured boolean for diagnostics. It does not receive either
provider's key value and cannot initiate transcription requests. The bot runtime
settings and activation checklist are documented in `docs/voice-tutor.md`.

Candidate environments are installed from `requirements.lock`. Update the lock
only as a reviewed dependency change and validate it on Linux CI and the Mac
mini before activating a release.

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

Keep the production Telegram token out of launchd environment values. Create an
owner-only regular token file with mode `0600`, set `BOT_TOKEN_FILE` to its
absolute path, and remove `BOT_TOKEN` from the plist. The bot refuses relative,
symlinked, group/world-readable, malformed, or conflicting token sources.

Before rotating a historically exposed token, audit the private log without
printing its contents. The execution form creates a separate verified mode-
`0600` copy and never replaces or deletes the source:

```bash
python ops/mydictionary_telegram_security.py --log /absolute/private/bot.log
python ops/mydictionary_telegram_security.py \
  --log /absolute/private/bot.log \
  --sanitize-to /absolute/private/bot.sanitized.log --execute
```

See [the production runbook](../docs/runbooks/mac-mini-deployment.md) before
installing, enabling, clearing quarantine, or recovering a failed release.

## Billing operations

Validate the checked-in candidate AI/Stars assumptions and render only non-secret,
disabled environment values with:

```bash
python ops/mydictionary_economics.py --check
python ops/mydictionary_economics.py --render-env
```

The renderer never includes provider keys, payload secrets, safety salts,
support contacts, or terms text. Its output is a review aid, not an activation
command. The snapshot approves only the bounded free AI-pilot economics; all
feature flags, Stars, and billing terms remain disabled.

Preview the fixed eight-language synthetic smoke without a provider call:

```bash
python ops/mydictionary_ai_smoke.py
```

The `--execute` form is a separate owner-approved operation. It requires the
exact `AI_SYNTHETIC_SMOKE_APPROVAL=synthetic-ai-pilot-v1` gate, the reviewed
model/rates, a non-production key and safety salt, a private runs directory,
an unused run ID, and an explicit receipt path. It performs at most one
anonymous provider attempt, never mutates production feature flags or learner
credits, and writes a mode-`0600` aggregate receipt with no prompt, response,
provider ID, Telegram ID, credential, or local path.

Validate Commercial Launch v3 and idempotently seed only the four reviewed
database drafts with:

```bash
python ops/mydictionary_commercial_launch.py check
python ops/mydictionary_commercial_launch.py seed-products --execute
```

The second command requires `DATABASE_URL`, refuses writes without `--execute`,
never activates a product, and refuses to overwrite a non-draft catalog row.

AI provider telemetry that could not reach PostgreSQL is written to a private
fallback journal. Inspect it without revealing contents and reconcile it only
after reviewing the storage incident:

```bash
python ops/mydictionary_ai_metering.py status
python ops/mydictionary_ai_metering.py reconcile --actor <operator> --execute
```

Reconciliation is idempotent, writes an audit entry, and leaves the persistent
breaker open. Verify the imported model, tier, token fields, and cost in the
admin before using the separate audited breaker reset. Never edit or truncate
the journal by hand.

`mydictionary_billing.py reconcile` is read-only and compares bounded Bot API
transaction pages with the local Stars ledger. Refund and subscription changes
require the exact local UUID plus `--execute`; the wrapper never prints tokens,
invoice payloads, Telegram charge IDs, or learner identities. Keep it on the
loopback production host and run it only after the corresponding admin record
and support decision have been reviewed.

Before a Telegram Stars test, validate the separate test-bot, test-user,
database, data-directory, and test-terms binding without making a Bot API call:

```bash
python ops/mydictionary_stars_test.py --check
```

Store the dedicated test token and test user ID in an owner-only mode-`0600`
JSON file instead of a plist or shell history:

```json
{"bot_token":"<test-server-token>","test_user_id":123456789}
```

Set only `TELEGRAM_TEST_CREDENTIALS_FILE` to its absolute path. The preflight
refuses inline `BOT_TOKEN` or `TELEGRAM_TEST_USER_ID` when the bundle is used.

The complete test-only environment contract is documented in
`docs/telegram-stars-billing.md`. Production launchd configuration must keep
`TELEGRAM_API_ENVIRONMENT=production` (or omit it) and must never receive the
test bot token.

## Product safety operations

The safety wrappers are preview-only unless `--execute` is supplied:

```bash
python ops/mydictionary_retention.py retention
python ops/mydictionary_retention.py retention --execute
python ops/mydictionary_monitor.py
python ops/mydictionary_monitor.py --execute
python ops/mydictionary_offsite_backup.py
python ops/mydictionary_offsite_backup.py --check
python ops/mydictionary_offsite_backup.py --execute
python ops/mydictionary_restore_drill.py --encrypted-name <exact.dump.age>
python ops/mydictionary_restore_drill.py --encrypted-name <exact.dump.age> \
  --execute --confirm-isolated-database
```

Retention previews candidate row counts. Monitoring sends no alert and writes
no state in preview mode. Off-site backup verifies the local dump in preview
mode and invokes `age` and `rclone` only with `--execute`. See
`docs/product-safety.md` for required settings, retention boundaries, the
recovery-host separation, and the exact restore-drill contract. Never copy the
private age identity to the production host.
