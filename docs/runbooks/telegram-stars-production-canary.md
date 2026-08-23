# Telegram Stars production owner canary

This runbook describes one explicitly approved owner-only production purchase
and refund. It does not authorize a deploy, restart, credential change, invoice,
payment or refund.

## Exact runtime mapping

Public checkout must remain off. Store the owner ID and existing billing secret
only in the protected production environment; never paste them into commands,
logs, receipts or project notes.

```dotenv
TELEGRAM_STARS_ENABLED=false
STARS_PRODUCTION_CANARY_ENABLED=true
STARS_PRODUCTION_CANARY_OWNER_ID=<one-positive-owner-telegram-id>
STARS_PRODUCTION_CANARY_PRODUCT_ID=ai-mini
STARS_PRODUCTION_CANARY_AMOUNT_XTR=10
```

The existing billing profile must also have current approved terms, complete
seller details, a valid payload secret, current economics review and an active
one-time public `ai-mini` product with exactly 20 credits at 69 XTR. The 10 XTR
amount applies only to the owner canary invoice; it never reprices that public
product. Aliases such as `STARS_CANARY_ENABLED` are intentionally ignored.
The 10 XTR attempt uses the versioned v2 claim. Preserve any unpaid 69 XTR v1
marker and order unchanged; v2 status and receipts deliberately ignore them.

## Reviewed operator entrypoint

Run these commands from the OVH host. They execute inside the reviewed bot
container, where the protected production environment and the mode-`0600`
`BOT_TOKEN_FILE` are already mounted. These are the only supported command
forms.

```console
docker compose --project-name main-manager-emergency -f /srv/main-manager/compose.yaml -f /srv/main-manager/deploy/mydictionary/compose.mydictionary.yaml --profile production-gated exec -T mydictionary-bot python ops/mydictionary_stars_production_canary.py status
docker compose --project-name main-manager-emergency -f /srv/main-manager/compose.yaml -f /srv/main-manager/deploy/mydictionary/compose.mydictionary.yaml --profile production-gated exec -T mydictionary-bot python ops/mydictionary_stars_production_canary.py recover --execute
docker compose --project-name main-manager-emergency -f /srv/main-manager/compose.yaml -f /srv/main-manager/deploy/mydictionary/compose.mydictionary.yaml --profile production-gated exec -T mydictionary-bot python ops/mydictionary_stars_production_canary.py receipt --output /app/state/telegram-stars-production-canary-receipt.json --execute
```

`status` is read-only and prints only aggregate fields. `recover` is blocked
without `--execute`, scans Telegram history in 100-row pages up to a fixed
1,000-row cap, and refuses to refund when the capped history is uncertain.
`receipt` is blocked without `--execute`, refuses to overwrite an existing
path, and creates the aggregate receipt with mode `0600` only after the canary
is disabled and refunded. None of the commands prints private identifiers.

## Exact read-only pre/post probe

Run this same block immediately before arming the canary and again after it is
disabled. It follows the canonical
[`OVH deployment runbook`](ovh-deployment.md) and contains no `--execute`,
credential output, database rows or raw logs.

```console
docker compose --project-name main-manager-emergency -f /srv/main-manager/compose.yaml -f /srv/main-manager/deploy/mydictionary/compose.mydictionary.yaml --profile production-gated exec -T mydictionary-bot sh -c 'printf "bot_release_sha=%s\n" "$RELEASE_SHA"'
docker compose --project-name main-manager-emergency -f /srv/main-manager/compose.yaml -f /srv/main-manager/deploy/mydictionary/compose.mydictionary.yaml --profile production-gated exec -T mydictionary-admin sh -c 'printf "admin_release_sha=%s\n" "$RELEASE_SHA"'
docker compose --project-name main-manager-emergency -f /srv/main-manager/compose.yaml -f /srv/main-manager/deploy/mydictionary/compose.mydictionary.yaml --profile production-gated exec -T mydictionary-admin python -c 'from sqlalchemy import text; from mydictionary.admin import database_url_from_env; from mydictionary.storage import DatabaseStore; store=DatabaseStore(database_url_from_env(), migrate=False); connection=store.engine.connect(); print("db_revision=" + str(connection.execute(text("select version_num from alembic_version")).scalar_one())); connection.close(); store.close()'
docker compose --project-name main-manager-emergency -f /srv/main-manager/compose.yaml -f /srv/main-manager/deploy/mydictionary/compose.mydictionary.yaml --profile production-gated exec -T mydictionary-admin env MYDICTIONARY_APP_ROOT=/app/state MYDICTIONARY_HEALTH_URL=http://127.0.0.1:8787/health MYDICTIONARY_PGDUMP_DATABASE=mydictionary MYDICTIONARY_BACKUP_DIR=/app/state/backups python ops/mydictionary_monitor.py
docker compose --project-name main-manager-emergency -f /srv/main-manager/compose.yaml -f /srv/main-manager/deploy/mydictionary/compose.mydictionary.yaml --profile production-gated exec -T mydictionary-admin env MYDICTIONARY_APP_ROOT=/app/state MYDICTIONARY_PGDUMP_DATABASE=mydictionary MYDICTIONARY_BACKUP_DIR=/app/state/backups python ops/mydictionary_backup.py --check
curl --fail --silent --show-error --output /dev/null --write-out 'loopback_health_http=%{http_code}\n' http://127.0.0.1:8787/health
curl --fail --silent --show-error --output /dev/null --write-out 'public_health_http=%{http_code}\n' https://mydictionary.meshly.fr/health
docker compose --project-name main-manager-emergency -f /srv/main-manager/compose.yaml -f /srv/main-manager/deploy/mydictionary/compose.mydictionary.yaml --profile production-gated exec -T mydictionary-bot python ops/mydictionary_stars_production_canary.py status
```

The SHA lines must be equal; `db_revision` must report the reviewed revision. The
monitor stays in preview mode and must report the bot heartbeat, loopback admin
health and latest backup as healthy. The explicit backup check must succeed;
both health requests must return `200`; canary status must show public checkout
off and the expected armed/refunded phase. Stop on any mismatch and apply the
rollback boundary from the canonical OVH runbook—do not arm or recover.

## Approved execution sequence

1. Freshly verify release, schema, heartbeat, public/admin health, backup state,
   `TELEGRAM_STARS_ENABLED=false` and AI/Voice/Stars public gates.
2. Obtain exact owner approval for the canary configuration and production
   restart. Enable only the five values above; public checkout stays off.
3. Confirm a non-owner cannot open terms, products or checkout. The owner may
   create exactly one 10 XTR `ai-mini` invoice for 20 credits. The durable v2
   database claim prevents a second invoice even under concurrent taps.
4. On successful payment, verify one credit grant, one refund request and one
   immediate gateway refund attempt. Do not repeat a failed automatic attempt.
5. For a failed or uncertain refund, obtain a new explicit owner recovery
   approval. Recovery must first reconcile Telegram transaction history; it
   finalizes an already-remote refund or performs at most one explicit retry.
6. After refund completion, set `STARS_PRODUCTION_CANARY_ENABLED=false` and
   perform the separately approved restart. Recheck public checkout off,
   canary off, heartbeat ready and admin health ok.
7. Build final aggregate evidence only when status is disabled and refunded.
   The receipt environment is `telegram_production_canary`; it cannot satisfy
   the separate `telegram_test` launch gate.

Never include Telegram IDs, charge/order/payment/refund IDs, tokens, database
URLs, user messages or raw logs in receipts or durable project writebacks.
