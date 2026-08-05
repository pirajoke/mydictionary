# Product safety and data lifecycle

Stage 5 adds controls required before broad public access. These controls do
not enable public mode, AI, Telegram Stars, alerts, or off-site uploads.

## Abuse controls

The bot uses persistent fixed-window rate limits. Limits are scoped to regular
commands, learning actions, AI actions, and billing actions. The AI and billing
limits are intentionally tighter. Administrators are exempt so an abuse event
cannot lock operators out of recovery commands.

An abuse event contains only:

- Telegram user ID;
- action scope and rule name;
- configured limit and observed counter;
- timestamp.

Message text, prompts, answers, voice, payment identifiers, IP addresses, and
tokens are never stored in the abuse tables.

Runtime defaults:

| Setting | Default |
|---|---:|
| `SAFETY_RATE_LIMITS_ENABLED` | `true` |
| `SAFETY_RATE_LIMIT_WINDOW_SECONDS` | `60` |
| `SAFETY_RATE_LIMIT_BLOCK_SECONDS` | `120` |
| `SAFETY_DEFAULT_REQUESTS_PER_WINDOW` | `90` |
| `SAFETY_LEARNING_REQUESTS_PER_WINDOW` | `60` |
| `SAFETY_AI_REQUESTS_PER_WINDOW` | `8` |
| `SAFETY_BILLING_REQUESTS_PER_WINDOW` | `6` |

## Retention

`ops/mydictionary_retention.py retention` previews expired rows. Add
`--execute` only from a scheduled operator job after reviewing the output.
Reserved AI requests are never deleted by retention because their credit hold
must first be recovered by the normal AI reservation recovery path.

| Data | Default retention |
|---|---:|
| product analytics | 180 days |
| completed and failed AI usage | 365 days |
| abuse events | 180 days |
| inactive rate-limit buckets | 7 days |

The corresponding environment variables are `RETENTION_ANALYTICS_DAYS`,
`RETENTION_AI_USAGE_DAYS`, `RETENTION_ABUSE_DAYS`, and
`RETENTION_RATE_LIMIT_DAYS`.

The `/privacy` flow erases learning progress, product analytics, detailed AI
usage, imports, rate-limit state, and Telegram profile fields. It blocks the
account and records a pseudonymous operation reference. Billing, credit ledger,
refund, subscription, and administrator audit records remain available for
financial reconciliation, refunds, and fraud review. This behavior is a product
contract, not a claim of legal compliance; jurisdiction-specific retention must
be reviewed before launch.

## Monitoring

`ops/mydictionary_monitor.py` verifies the bot heartbeat, the local admin health
endpoint, and the newest database backup. The first failed run is silent by
default. A second identical failure creates one alert; subsequent identical
failures are deduplicated, and recovery creates one recovery notification.

The command is read-only unless `--execute` is supplied. Telegram alert delivery
also requires all of:

- `MYDICTIONARY_MONITOR_ALERTS_ENABLED=true`;
- `MYDICTIONARY_MONITOR_BOT_TOKEN`;
- `MYDICTIONARY_MONITOR_CHAT_ID`.

The monitor state contains only counters and a failure fingerprint and is
written with mode `0600`.

## Encrypted off-site backups

`ops/mydictionary_offsite_backup.py` first runs the existing local backup
verification. In preview mode it performs no upload. With `--execute`, it:

1. encrypts the verified PostgreSQL dump into a private temporary directory
   using the public `age` recipient;
2. calculates a checksum of the encrypted object;
3. uploads only the `.age` object and its checksum using immutable `rclone`
   writes;
4. removes temporary files automatically.

Required settings are `MYDICTIONARY_BACKUP_AGE_RECIPIENT` and
`MYDICTIONARY_BACKUP_RCLONE_REMOTE`. The age private identity is deliberately
not present on the production host contract. Restore drills must retrieve the
encrypted object, verify the checksum, decrypt on an approved recovery host,
and then use the existing restore verification procedure.
