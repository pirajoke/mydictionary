# Mac mini deployment runbook

This runbook covers MY DICTIONARY production releases. It does not authorize a
merge, deploy, service restart, database restore, access-mode change, AI call,
or payment. Each consequential action still requires its own approval.

## Invariants

- Production runs on the Mac mini, not Render.
- Only a tested commit already present in `origin/main` may become `current`.
- Bot and admin must run from the same release SHA.
- The expected access mode defaults to `allowlist` and is checked in the bot
  heartbeat.
- AI and payment flags remain off unless independently approved.
- Health is loopback HTTP plus an exact, fresh Telegram polling heartbeat.
- Secrets, logs, runtime state, database dumps, and absolute production paths
  stay outside Git.

## Installation gate

1. Confirm the draft PR tests and review are complete.
2. Obtain separate approval to merge and deploy the named commit to production.
3. Back up the current deploy, admin, and database-backup wrappers.
4. Install `ops/mydictionary_autodeploy.py` and
   `ops/mydictionary_admin.py` from the merged commit with owner-only write and
   execute permissions. Install `ops/mydictionary_backup.py` for the dedicated
   backup service using the same ownership policy.
5. Configure launchd with the environment listed in `ops/README.md`. Do not put
   the bot token or admin credential in a plist committed to Git.
6. Keep the autodeploy launch agent unloaded while validating the wrappers.
7. Keep the new backup service unloaded until its destination, database target,
   first dump, and monitoring command are explicitly approved for production.

## Pre-deploy checks

Record without exposing secrets:

- `origin/main` commit SHA and fast-forward relationship to `.deployed-sha`
- `current` release SHA
- PostgreSQL `alembic_version`
- free space, backup destination, and a successful
  `mydictionary_backup.py --check`
- `MYDICTIONARY_PGDUMP_DATABASE` is a plain database name; socket or host and
  role are set separately through `PGHOST`, `PGPORT`, and `PGUSER`
- bot/admin launchd state
- heartbeat age, release SHA, and access mode
- local and public health status
- AI/payment feature flags

Do not continue when production is already unhealthy. Contain the incident
first and preserve the last known-good release.

## Code-only release

The unattended command builds an isolated release, installs dependencies,
runs the full deterministic suite and compilation, compares migration and
protected-content state, then activates the candidate.

Success requires consecutive probes proving:

1. every configured service is running
2. heartbeat state is `ready`
3. heartbeat release is the candidate SHA
4. heartbeat access mode equals the configured expected mode
5. heartbeat age is within the configured limit
6. loopback `/health` returns exactly `200 {"status":"ok"}`

If readiness fails and the database revision is unchanged, the deployer
reactivates the previous release and proves its readiness. The candidate SHA is
then quarantined. If the database changed unexpectedly, automatic rollback is
refused and the recovery state is marked `manual_recovery_required`.

## Content or migration release

The default command records an operator hold and exits without activation.
After the content/migration PR and production action are separately approved,
run `--operator-deploy` interactively with the timer still unloaded.

For a schema change the deployer performs this sequence:

1. stop bot and admin launchd services and wait for each registration to be
   removed
2. create a PostgreSQL custom-format backup with mode `0600`
3. validate the backup using `pg_restore --list`
4. record its filename, SHA-256, old revision, and target revision locally
5. activate the candidate release
6. apply the candidate Alembic head
7. bootstrap bot and admin from the reviewed current plist files
8. prove candidate readiness before updating `.deployed-sha`

`launchctl bootout` can return before launchd has removed the service
registration. The deployer therefore waits for the requested registration
state with a bounded timeout. Bootstrap never kickstarts a registration left
over from an earlier release: it unloads that registration, waits for removal,
then loads the current plist and verifies that registration appeared.

### Telegram Stars migration

Migration `0006_telegram_stars_billing` is a protected operator deployment.
Before applying it, back up PostgreSQL and verify that the current bot and admin
remain healthy. Deploy with `TELEGRAM_STARS_ENABLED=false`; this creates no
invoice, charge, refund, or AI request.

After migration, verify the billing admin tab, local reconciliation, and wallet
backfill. Product rows start as draft and no launch price is seeded. Enabling
Stars is a later production action requiring reviewed unit economics, monitored
`/paysupport`, configured terms, a retained HMAC secret, and a separately
approved real low-value payment/refund smoke test.

Migration `0010_launch_readiness` adds versioned billing and voice consent plus
the terms version snapshot on each order. Deploy it with AI, voice, and Stars
disabled. After migration, the diagnostics tab must show revision
`0010_launch_readiness`. Do not enable a feature until the corresponding
versioned document and every required positive cost setting are configured.

Migration `0012_ai_runtime_gates` adds exact AI economics snapshot binding,
provider-attempt telemetry, project/in-flight budgets, and persistent breaker
state. Deploy it only from a reviewed merge SHA with AI and Stars disabled and
with a fresh PostgreSQL backup. After migration, diagnostics must show
`0012_ai_runtime_gates`, a closed breaker, zero in-flight exposure, and zero
fallback-journal rows. A breaker reset is an authenticated, CSRF-protected,
audited operator action and must never be used to bypass unreconciled telemetry.
If the journal is non-empty, keep AI disabled, inspect status and reconcile the
technical records without making a provider call:

```bash
python ops/mydictionary_ai_metering.py status
python ops/mydictionary_ai_metering.py reconcile --actor <operator> --execute
```

Reconciliation leaves the breaker open. Compare the imported model, service
tier, token fields, local cost, and provider dashboard before recording a reset
reason in the admin. Do not delete or truncate the journal manually.

If checkout must be contained, set `TELEGRAM_STARS_ENABLED=false` and restart
bot and admin. Keep `BILLING_PAYLOAD_SECRET` unchanged so a successful payment
for an already-issued order can still be validated and fulfilled. Do not roll
the database back after accepted payments; reconcile orders, charges, ledger,
and refund holds first.

### Backup policy

- Run `mydictionary_backup.py` once per day from a dedicated launchd service.
- The latest recurring backup must be no older than 26 hours. Monitoring and
  every deploy preflight run `--check`, which revalidates metadata, file mode,
  size, SHA-256, and custom archive format without modifying the backup.
- Keep at least 30 days and at least seven recurring backups. Backup creation
  and checks never prune. `--prune` is a separate operator action; it validates
  every candidate before deleting any file and never deletes the latest copy.
- Every schema migration requires a new uniquely named custom-format dump.
- A dump is valid only after `pg_restore --list` succeeds and its SHA-256 is
  recorded in the private recovery state.
- Dump and recovery files stay mode `0600`; they are never committed, logged,
  attached to an issue, or copied to an unencrypted destination.
- No backup is overwritten or automatically deleted. Keep each migration
  backup for at least 30 days and until two later migration backups have been
  validated, whichever is longer.
- Deletion, off-host transfer, or restore is a separate operator action. Before
  a restore, recompute the checksum and compare it with the recovery record.
- Host-local backups do not cover loss or compromise of the Mac mini or its
  storage. This residual risk remains open until immutable encrypted upload is
  scheduled and a separate recovery host has produced a reviewed restore-drill
  receipt with `ops/mydictionary_restore_drill.py`.

## Recovery matrix

| Failure point | Automatic action | Operator action |
| --- | --- | --- |
| Fetch or dependency install | No state change | Correct connectivity and retry |
| Candidate tests/compile | Quarantine SHA | Fix code or explicitly clear reviewed SHA |
| Content/schema gate | Operator hold | Obtain approval and use operator mode |
| Code-only readiness, DB unchanged | Restore and prove old release | Diagnose candidate before clearing SHA |
| Backup creation, before migration | Restart old services | Fix backup path/tooling and retry |
| Migration started or DB changed | Stop candidate; never activate old code | Inspect recovery record; prefer fix-forward |
| Candidate healthy | Record deployed SHA | Continue post-deploy monitoring |

Restoring a PostgreSQL dump is destructive and can discard writes made after
the snapshot. Never restore automatically. Confirm the exact dump, checksum,
target database, expected data-loss window, and service stop before a restore.

### Completing manual recovery

Use `--adopt-current` only after an approved fix-forward recovery has made the
merged `origin/main` release healthy. Adoption verifies the active release,
database head, and readiness. When the recovery record is still
`manual_recovery_required`, it also requires the recorded release and revision
to match, recomputes any recorded backup checksum, and validates that dump with
`pg_restore --list`. Only then does it mark recovery
`ready_after_manual_adopt` and clear the matching hold. A mismatch is
fail-closed and leaves the hold and recovery record unchanged.

## Quarantine handling

The local hold file contains only commit SHA, category, stage, error type,
previous SHA, and timestamp. It contains no exception text, command output,
URL, token, or learner data.

Before clearing a failed SHA:

1. identify the deterministic cause
2. verify the cause is fixed or the failure was environmental
3. confirm the target is still `origin/main`
4. clear only the exact SHA with `--clear-failed`
5. run `--prepare-only` before another activation attempt

Operator holds for content or migrations cannot be cleared with
`--clear-failed`; they are consumed only by a successful operator deploy.

## Post-deploy checks

- `current` and `.deployed-sha` equal the merged commit
- bot/admin PIDs remain stable through multiple long-poll cycles
- heartbeat stays fresh and reports the expected release/access mode
- local and public health stay `200`
- admin login redirects correctly and the login page is reachable
- no polling conflicts, startup failures, or Telegram request URLs appear in
  new logs
- PostgreSQL revision equals the candidate Alembic head
- the recurring backup check remains green after the release
- autodeploy remains unloaded until its enablement is separately approved
