# MY DICTIONARY admin console

The Stage 3-4 admin console is a separate server-rendered process. It reads the
same PostgreSQL database as the Telegram bot and does not start Telegram
polling. The default binding is loopback-only on the Mac mini.

## Scope

- dashboard for users, learning, languages, AI usage, costs, and AI wallets
- searchable learner table and CSV exports
- managed pending, active, and blocked pilot access with an audit trail
- dictionary and topic coverage
- privacy-minimized AI request diagnostics without prompt or response storage
- voice-session metrics and text-match diagnostics without transcript or audio exposure
- audited wallet grants and withdrawals
- draft and active Stars products with measured cost and margin floors
- payment orders, Stars payments, refund holds, and local reconciliation
- editable Telegram profile, `/start`, and `/help` text
- database, migration, feature-flag, release, asset, and Telegram polling readiness
- AI snapshot/tier/budget diagnostics plus audited breaker reset, blocked while
  provider telemetry remains in the fallback journal
- separate opt-in, time-limited, one-time enrollment windows for isolated
  OpenAI and Groq project keys
- append-only administration audit log

The admin can request a refund hold but cannot call Telegram's refund API. Live
refund processing remains an explicit operator action through an injected
gateway.

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
TELEGRAM_STARS_ENABLED=false
```

Remote key enrollment is disabled unless all three settings are present:

```text
AI_KEY_ENROLLMENT_ENABLED=true
AI_KEY_ENROLLMENT_PATH=/absolute/app-root/local-config/openai-gate2.key
AI_KEY_ENROLLMENT_EXPIRES_AT=2026-08-07T12:30:00Z
```

Groq Voice uses an independent window and destination:

```text
GROQ_API_KEY_FILE=/absolute/app-root/local-config/groq-voice.key
GROQ_KEY_ENROLLMENT_ENABLED=true
GROQ_KEY_ENROLLMENT_PATH=/absolute/app-root/local-config/groq-voice.key
GROQ_KEY_ENROLLMENT_EXPIRES_AT=2026-08-13T12:30:00Z
```

The target file must not exist before enrollment. `GROQ_API_KEY_FILE` tells the
bot where to read the enrolled value; it does not expose the value to the admin
process. Do not set `GROQ_API_KEY` at the same time.

The production launcher accepts a destination only directly under
`MYDICTIONARY_APP_ROOT/local-config`. That directory must already exist and
must not be group or world writable. The expiry must include a timezone and
cannot be more than one hour in the future.

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

## One-time remote key enrollment

Use this only for an isolated, short-lived provider key while AI remains
disabled. Configure a window of at most one hour, restart only the admin
service, authenticate normally, and open `/admin/ai-key` over the existing
HTTPS admin endpoint. Use `/admin/groq-key` for Groq. Each provider has its own
window, target, status, and audit actions. Both forms require the signed admin
session and CSRF token.

The server creates the destination with `O_EXCL`, `O_NOFOLLOW` where available,
and mode `0600`. It never stores the key in PostgreSQL, session data, audit
details, command arguments, or a response. The audit log records only a
12-character SHA-256 fingerprint. A successful write or a pre-existing target
permanently consumes the window. Invalid, expired, duplicate, symlink, and
unsafe-directory cases fail closed.

After enrollment, close the corresponding window by setting its
`*_KEY_ENROLLMENT_ENABLED` flag to `false`. Keep the owner-only file only while
the bot needs the provider. On revocation, disable Voice first, remove the file,
and revoke the project key in the provider console. Never forward direct
`OPENAI_API_KEY` or `GROQ_API_KEY` values to the admin process.

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
- no stored AI prompts, answers, vocabulary history exports, or database secrets
