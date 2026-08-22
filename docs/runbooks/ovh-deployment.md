# OVH deployment and rollback runbook

This is the canonical release contract for the current MY DICTIONARY Docker
runtime on OVH. It does not grant SSH, merge, deploy, migration, credential,
payment or external-message authority.

## Invariants

- Only a reviewed commit already merged into `origin/main` may be released.
- Bot and admin run the same exact SHA; PostgreSQL persists outside the release.
- The application origin binds to loopback; Cloudflare is a separate connector.
- A pre-deploy custom-format PostgreSQL dump is checksummed and verified with
  `pg_restore --list` before activation.
- AI, Voice, Stars and autodeploy flags are never changed implicitly by a code
  release.
- No secret value, environment dump, database URL, raw log or learner data is
  printed into a release receipt.

The owner-controlled compose source lives under `/srv/main-manager`; the
MY DICTIONARY overlay is `deploy/mydictionary/compose.mydictionary.yaml` and
the compose project is `main-manager-emergency`. These paths identify deployment
structure only and contain no credential values.

## Read-only preflight

Record privacy-safe evidence only:

1. `origin/main` and requested 40-character SHA;
2. active bot/admin release labels and equality;
3. PostgreSQL container health and `alembic_version`;
4. bot heartbeat state, age, release and access mode;
5. loopback `/health` and public `/health` independently;
6. bot/admin restart counts and exactly one bot polling process;
7. backup timer state, latest verified dump age/checksum status;
8. AI, Voice, Stars, Mirror voice and autodeploy flags by boolean only;
9. recent traceback, polling-conflict and token-pattern counts without log text.

Stop before mutation on any release/schema mismatch, stale backup, unhealthy
loopback origin, duplicate bot, unexpected flag delta or non-empty secret scan.
A Cloudflare 1033 with healthy loopback is a route incident, not a reason to
change the application or database.

## Release sequence

1. Confirm the named SHA is merged and CI is green.
2. Review source/compose diff and classify code-only, content or migration.
3. Create and verify a uniquely named mode-`0600` PostgreSQL custom dump.
4. Build the candidate image from the exact SHA with locked dependencies.
5. For migrations, stop bot/admin, apply only the candidate Alembic head and
   refuse automatic downgrade after any database change.
6. Activate bot/admin together while preserving reviewed private environment
   and feature flags.
7. Require multiple consecutive heartbeat and loopback-health probes before
   accepting the release.
8. Record active SHA, revision, backup receipt, restart counts and flags.

## Acceptance

- bot and admin report the candidate SHA;
- heartbeat remains `ready` and fresh in the expected access mode;
- loopback health is exactly 200/ok;
- public health/login are checked separately and any route incident is explicit;
- PostgreSQL is healthy at the candidate Alembic head;
- one bot polls; bot/admin restart counts remain zero;
- backup verification remains green;
- no new traceback, polling conflict or token-pattern count appears;
- Stars/autodeploy and every unrelated feature flag remain unchanged.

## Rollback boundary

If readiness fails and the database revision is unchanged, reactivate the
previous reviewed image and prove the same acceptance checks. If a migration
started or the revision changed, never start older code automatically: keep
services contained, preserve the backup/receipt and use reviewed fix-forward or
an explicitly approved restore with an exact data-loss window.

Cloudflare connector recovery follows
[`ovh-cloudflare-tunnel.md`](ovh-cloudflare-tunnel.md). Off-site upload and
isolated restore follow [`../product-safety.md`](../product-safety.md).
