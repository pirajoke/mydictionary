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
- a reauthenticated Stars Launch Wizard for a private seller/terms profile and
  separate Telegram test-environment credentials
- optional email password recovery for the singleton administrator
- optional owner-only Google OpenID Connect sign-in without provider-token storage
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

Password recovery and Google sign-in are optional complete feature sets. With
no auth-provider settings they stay hidden and the corresponding routes return
404. A partial, contradictory, non-HTTPS, or unsafe secret-file configuration
stops admin startup instead of degrading to a weaker mode.

Email password recovery requires authenticated SMTP with verified STARTTLS:

```text
ADMIN_EMAIL=<one normalized owner email>
ADMIN_PUBLIC_URL=https://mydictionary.meshly.fr
ADMIN_SMTP_HOST=<SMTP host>
ADMIN_SMTP_PORT=587
ADMIN_SMTP_USERNAME=<SMTP account>
ADMIN_SMTP_PASSWORD_FILE=<absolute private mode-0600 file>
ADMIN_SMTP_FROM=<sender mailbox or display name and mailbox>
ADMIN_RESET_TOKEN_TTL_SECONDS=900
ADMIN_RESET_RATE_LIMIT_ATTEMPTS=5
```

Only an HMAC-SHA256 digest and lifecycle metadata enter PostgreSQL. A new row
stays inactive until SMTP returns successfully; delivery, activation, or
revocation failure therefore cannot leave a usable reset link. The response
never confirms whether an email matches. A new request, a normal admin
credential change, expiry, or successful use revokes the older link, and a
successful password reset increments the session version. Reset tokens and
email addresses are excluded from audit details and application access-log
targets.

Google sign-in requires the same `ADMIN_EMAIL` and `ADMIN_PUBLIC_URL`, plus:

```text
ADMIN_GOOGLE_CLIENT_ID=<Google web OAuth client ID>
ADMIN_GOOGLE_CLIENT_SECRET_FILE=<absolute private mode-0600 file>
```

Register exactly
`https://mydictionary.meshly.fr/admin/google/callback` as the authorized
redirect URI. The server uses Authorization Code + OpenID Connect with
`openid email`, one-time state and nonce, and exact issuer, audience, expiry,
verified-email, and owner-email checks. OAuth codes and provider tokens are not
persisted; production token validation is sent to Google in a POST body, never
in the URL. No refresh scope is requested.

Both secret files must be absolute regular non-symlink files owned by the
runtime user, no larger than 1024 bytes, and not readable by group or world.
Do not place either secret value directly in environment variables, compose
files, command arguments, logs, commits, or admin audit records.

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

Stars launch setup uses one bounded window with separate destinations:

```text
STARS_LAUNCH_ENROLLMENT_ENABLED=true
STARS_LAUNCH_PROFILE_PATH=<app-root>/local-config/billing-launch-profile.json
STARS_TEST_CREDENTIALS_PATH=<app-root>/local-config/telegram-test-credentials.json
STARS_TEST_RECEIPT_PATH=<app-root>/local-config/telegram-test-receipt.json
STARS_LAUNCH_ENROLLMENT_EXPIRES_AT=<timezone-aware timestamp within one hour>
```

Open `/admin/stars-launch` after the admin-only restart that creates the window.
Each form requires the current admin password in addition to the authenticated
session and CSRF token. The profile form generates the invoice payload secret
server-side; neither form redisplays submitted data. Successful destinations
are mode `0600`, independently consumed, and represented in audit only by a
short SHA-256 fingerprint.

Close the window after both entries are consumed. Runtime processes load the
seller/terms profile through `BILLING_LAUNCH_PROFILE_FILE`; do not configure
that variable together with any inline seller, support, terms, approval, or
payload-secret variable. The dedicated test credential file is used only by an
isolated Telegram test process through `TELEGRAM_TEST_CREDENTIALS_FILE`.

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

## Stars launch gates

The billing tab keeps the existing commercial metrics and adds a compact setup
and test-evidence checklist. It does not activate checkout. After a separately
approved Telegram test-environment run has produced a privacy-safe mode-`0600`
receipt, the read-only operator gate is:

```bash
python ops/mydictionary_stars_launch.py check
```

The check requires the private profile, dedicated test credentials, current
economics, exact Commercial Launch v3 catalog, disabled checkout, and passing
purchase, duplicate-delivery, restart-recovery, reconciliation, and refund
evidence. Its JSON output contains only gate booleans and blocker codes.

Product activation remains a separate explicit database write:

```bash
python ops/mydictionary_stars_launch.py activate-products --execute
```

It can activate only `ai-mini`, `ai-starter`, and `ai-value`, is idempotent,
and leaves `ai-monthly` draft. It never changes `TELEGRAM_STARS_ENABLED`; the
checkout flag and service restart still require a separately approved
production rollout.

## Security properties

- fail-closed setup when no admin credential or session secret exists
- scrypt-backed Werkzeug password hash by default
- signed `HttpOnly`, `SameSite=Lax` session cookie; production cookies remain `Secure`
- CSRF token on every state-changing request
- login attempt throttling per source address
- reset throttling uses an opaque keyed source fingerprint and trusts
  `CF-Connecting-IP` only from the loopback tunnel peer
- one-time password-reset digests with transactional revocation and session invalidation
- Google OIDC state/nonce and exact singleton-owner identity validation without token storage
- restrictive CSP, frame denial, MIME sniffing protection, and no-store caching
- transactional credit changes with a separate ledger and audit entry
- transactional learner access changes with an administration audit entry
- administrator accounts cannot be suspended through learner access controls
- no destructive reset endpoint
- no stored AI prompts, answers, vocabulary history exports, or database secrets
