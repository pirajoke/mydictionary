# MY DICTIONARY AI Platform

## Scope

The product remains a Telegram-first language-learning bot. Deterministic study
modes stay independent of AI. Paid AI features are added as application
services around the existing language, topic, block, quiz, flashcard, and
spaced-repetition flows.

Production runs on the Mac mini. Render is not part of the target architecture.

## Components

```text
Telegram updates
    -> bot adapter
    -> learning services
       -> learner repository -> PostgreSQL
       -> vocabulary content -> checked-in JSON
       -> AI tutor -> provider gateway
       -> credit ledger -> PostgreSQL

Admin browser
    -> admin API
    -> the same learning, AI usage, billing, and audit services
```

The bot and future admin server are separate processes. They share application
services and PostgreSQL, but not in-memory user state. Telegram polling remains
the bot transport; Telegram Stars do not require a public payment webhook.

## Data Ownership

- Checked-in dictionary JSON owns target words, Russian meanings,
  transcriptions, examples, and topic classification.
- `users` owns the Telegram identity snapshot required by the application.
- `user_progress` owns aggregate learning state, XP, level, and streak.
- `word_progress` owns spaced-repetition state per user, language, and a
  deterministic vocabulary ID derived from target text plus Russian meaning.
  The current index is metadata and may change when content is reordered.
- `data_imports` makes one-time legacy imports idempotent.
- `ai_allowances` retains pre-Stage-4 pilot history.
- `ai_wallets` owns current paid or granted AI credit balances and reservations.
- `ai_usage` owns privacy-minimized provider usage and request lifecycle data.
- `billing_products`, `payment_orders`, `stars_payments`,
  `billing_credit_ledger`, and `refund_requests` own Stage-4 commerce state.

Private conversation content, production exports, credentials, and personal
learning history must never enter the public repository.

## Runtime Isolation

Every Telegram update creates a learner runtime bound through `ContextVar`.
Legacy helpers resolve `PROGRESS` and `W()` through that runtime, so concurrent
users cannot share the active language or word counters. Telegram's
`context.user_data` continues to own short-lived interaction state such as the
active 10-word block and callback session token.

`BOT_ACCESS_MODE=allowlist` is the fail-closed default. It accepts
`ALLOWED_USER_ID` and comma-separated `ALLOWED_USER_IDS`. `pilot` registers a
new learner as `pending` and allows learning only after an administrator changes
the account to `active`. `blocked` users are denied in every mode, including
`public`. Existing users are backfilled as active by migration `0005`, and
configured administrators are always active. A future public rollout must set
`BOT_ACCESS_MODE=public` explicitly.

The bot publishes a privacy-safe heartbeat after every successful Telegram
long-poll response. The admin health endpoint combines that
freshness signal with a database probe, so an alive web process cannot hide a
stalled or conflicting Telegram poller.

## Storage and Migration

`DATABASE_URL` selects PostgreSQL. Old `postgres://` and `postgresql://` URLs
are normalized to the Psycopg 3 SQLAlchemy driver. Without `DATABASE_URL`, the
application fails closed. Local SQLite requires the explicit
`ALLOW_SQLITE_DEV=true` opt-in and is not a production mode.

Alembic migrations run before the first repository operation. When the legacy
`ALLOWED_USER_ID` first uses the migrated bot, `progress.json` and per-language
word counters under `DATA_DIR` are imported once. The import records a durable
key so restarts cannot duplicate or overwrite the migrated state.

## Next Boundaries

Stage 2 adds a provider-neutral AI gateway, active-block grounding, pilot quota
reservations, and usage records. It remains feature-flagged off by default.
Stage 3 adds the admin server and managed pilot admission. Stage 4 replaces
pilot allowance consumption with a wallet, append-only financial credit ledger,
and idempotent Telegram Stars fulfillment. AI code never writes payment status,
roles, access state, or computed learning scores directly.
