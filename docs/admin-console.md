# MY DICTIONARY admin console

The Stage 3 admin console is a separate server-rendered process. It reads the
same PostgreSQL database as the Telegram bot and does not start Telegram
polling. The default binding is loopback-only on the Mac mini.

## Scope

- dashboard for users, learning, languages, AI usage, costs, and pilot credits
- searchable learner table and CSV exports
- managed pending, active, and blocked pilot access with an audit trail
- dictionary and topic coverage
- privacy-minimized AI request diagnostics without prompt or response storage
- audited pilot credit grants and withdrawals
- editable Telegram profile, `/start`, and `/help` text
- database, migration, feature-flag, release, asset, and Telegram polling readiness
- append-only administration audit log

Payments, subscriptions, refunds, and Telegram Stars are intentionally outside
this stage.

## Required environment

```text
DATABASE_URL=postgresql+psycopg://pirajoke@/mydictionary?host=/tmp
ADMIN_USERNAME=<admin username>
ADMIN_PASSWORD_HASH=<Werkzeug password hash>
ADMIN_SESSION_SECRET=<at least 32 random characters>
ADMIN_HOST=127.0.0.1
ADMIN_PORT=8787
DATA_DIR=<shared runtime directory>
BOT_HEARTBEAT_MAX_AGE_SECONDS=45
```

The bot and admin processes must resolve the same heartbeat path. By default it
is `DATA_DIR/bot-heartbeat.json`. `BOT_HEARTBEAT_PATH` can override the complete
path when the processes use different working directories. The file contains
only process state, timestamps, PID, release identifier, and access mode; it is
atomically replaced with mode `0600`.

Generate the password hash interactively:

```bash
.venv/bin/python -m mydictionary.admin hash-password
```

The first admin startup writes only the password hash to PostgreSQL. Later
credential changes are performed in the Security section and invalidate older
sessions. Do not commit any of these values.

## Local production command

Apply migrations before starting the web process, then use Gunicorn:

```bash
.venv/bin/alembic upgrade head
.venv/bin/gunicorn --workers 1 --threads 4 --bind 127.0.0.1:8787 \
  "mydictionary.admin:create_app()"
```

Health check:

```bash
curl --fail --silent http://127.0.0.1:8787/health
```

`/health` returns `200` only when PostgreSQL is reachable and the bot has
reported a fresh successful Telegram polling cycle. Missing, malformed, stale,
starting, or stopped heartbeat state returns `503`. The public response does
not expose database, path, release, or process details; authenticated operators
can inspect the reason on the Diagnostics tab.

For access from another computer, keep the service on loopback and use an SSH
tunnel:

```bash
ssh -L 8787:127.0.0.1:8787 <mac-mini-host>
```

Then open `http://127.0.0.1:8787/admin`. A reverse proxy or remote binding must
add HTTPS and an explicit network access policy before use.

## Security properties

- fail-closed setup when no admin credential or session secret exists
- scrypt-backed Werkzeug password hash by default
- signed `HttpOnly`, `SameSite=Strict` session cookie
- CSRF token on every state-changing request
- login attempt throttling per source address
- restrictive CSP, frame denial, MIME sniffing protection, and no-store caching
- transactional credit changes with a separate ledger and audit entry
- transactional learner access changes with an administration audit entry
- administrator accounts cannot be suspended through learner access controls
- no destructive reset endpoint
- no stored AI prompts, answers, vocabulary history exports, or secrets
