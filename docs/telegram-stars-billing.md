# Telegram Stars Billing

## User flow

1. `/buy` presents the current versioned terms until the learner explicitly
   accepts them; no product list or order is available before acceptance.
2. `/buy` lists only active products when `TELEGRAM_STARS_ENABLED=true`.
3. The product callback creates a single-user signed order, snapshots the terms
   version, and sends an `XTR`
   invoice. `provider_token` is omitted.
4. Pre-checkout revalidates the current terms acceptance, order version, signed
   snapshot, owner, currency, and amount within ten seconds.
5. Only `successful_payment` creates the Stars payment row and grants credits.
6. A repeated successful-payment update returns the existing fulfillment and
   cannot grant credits twice.
7. `/terms` and `/paysupport` remain available independently of learner access.

## Recurring products

Products explicitly marked `subscription` create a recurring Stars invoice
with the only period currently supported by the Bot API: 2,592,000 seconds (30
days). The first payment creates one durable subscription. Every renewal has a
new charge ID, payment row, and idempotent credit-ledger grant; replaying a
Telegram update cannot grant the period twice. `/subscriptions` lets the
learner disable or restore renewal without ending the already paid period.

One-time and subscription products use separate immutable order snapshots.
Changing a catalog product never changes an issued invoice or existing
subscription. Subscription products are rejected above the Bot API maximum of
10,000 XTR. See the official [Bot API subscription contract](https://core.telegram.org/bots/api#sendinvoice).

## Runtime settings

All settings are disabled by default. Enabling checkout requires:

| Variable | Constraint |
| --- | --- |
| `TELEGRAM_STARS_ENABLED` | `true` only after rollout approval |
| `BILLING_PAYLOAD_SECRET` | random value of at least 32 characters |
| `BILLING_SUPPORT_CONTACT` | monitored payment-support contact |
| `BILLING_NET_MICRO_USD_PER_XTR` | conservative net value after platform reserves |
| `BILLING_ECONOMICS_REVIEWED_ON` | current `YYYY-MM-DD` review date |
| `BILLING_ECONOMICS_MAX_AGE_DAYS` | 1-90; default 30 |
| `BILLING_PRIVATE_CHAT_TOPICS_ENABLED` | must match the BotFather topics setting; topics currently reduce Stars proceeds by 15% |
| `BILLING_ORDER_TTL_SECONDS` | 300-86400; default 1800 |
| `BILLING_TERMS_TEXT` | learner-visible terms, at most 3500 characters |
| `BILLING_TERMS_VERSION` | immutable safe identifier for the reviewed text |
| `BILLING_TERMS_APPROVED` | explicit `true` only after legal/privacy review of the exact text |

Disabling checkout stops new orders. Do not remove or rotate the payload secret
until every issued order is expired and payment reconciliation is complete.

## Unit economics

Products are created as `draft`. Estimated package margin is:

```text
net revenue = price_xtr * BILLING_NET_MICRO_USD_PER_XTR
margin bps = (net revenue - estimated package cost) / net revenue * 10000
```

Activation is rejected unless estimated cost and the target margin floor are
positive, net XTR economics are configured, and estimated margin meets the
floor. Public package prices therefore remain an operator decision based on
closed-alpha usage, speech, infrastructure, support, and refund data.

The current draft formulas and official-source snapshot live in
[`ai-stars-economics.md`](ai-stars-economics.md). The renderer keeps checkout
disabled and cannot activate the draft products.

## Refunds

The admin billing tab can request a refund only while the purchased credits are
still available. The request reserves those credits and records an audit row.
The web process cannot call Telegram's refund API.

`BillingService.process_refund()` requires an injected gateway. Production use
must be a separately approved operator action. A successful gateway response
removes the held credits, marks payment and order refunded, and appends an
idempotent reversal. A timeout or ambiguous error leaves the hold in place for
manual reconciliation.

## Reconciliation

The admin tab continuously checks local order-payment-ledger relationships.
`BillingService.reconcile_transactions()` compares an explicitly supplied page
of Telegram Stars transactions without changing local state. Unknown charges or
amount, currency, user, and refund-state mismatches must be resolved before
enabling AI spend or completing a refund.

`ops/mydictionary_billing.py reconcile` fetches bounded pages through
`getStarTransactions` and compares both directions without changing local
state. If the configured history cap is reached, reconciliation reports
`remote_history_truncated` and does not claim older local payments are absent.
Refund and subscription writes require a named local record and an
explicit `--execute`:

```text
mydictionary_billing.py process-refund --refund-id <uuid> --execute
mydictionary_billing.py cancel-subscription --subscription-id <uuid> --user-id <id> --execute
mydictionary_billing.py restore-subscription --subscription-id <uuid> --user-id <id> --execute
```

The gateway uses only official Bot API methods:
[`getStarTransactions`](https://core.telegram.org/bots/api#getstartransactions),
[`refundStarPayment`](https://core.telegram.org/bots/api#refundstarpayment), and
[`editUserStarSubscription`](https://core.telegram.org/bots/api#edituserstarsubscription).
No charge ID, bot token, invoice payload, or learner identity is printed by the
operator wrapper.

## Dedicated Telegram test environment

Stars tests must run through Telegram's separate test Bot API. Create a test
account and a separate bot with `@BotFather` while logged into Telegram's test
server. Never reuse the production bot token. The application selects the
official test route only when all isolation checks pass:

```text
TELEGRAM_API_ENVIRONMENT=test
TELEGRAM_TEST_RUN_ID=stars-gate4-YYYYMMDD
TELEGRAM_TEST_CREDENTIALS_FILE=<absolute owner-only credentials JSON>
TELEGRAM_TEST_DATABASE_NAME=mydictionary_stars_test
TELEGRAM_TEST_DATA_DIR=<absolute private test data directory>
BOT_ACCESS_MODE=allowlist
ALLOWED_USER_ID=<same single test-server user ID>
DATABASE_URL=<URL whose database is exactly mydictionary_stars_test>
DATA_DIR=<same path as TELEGRAM_TEST_DATA_DIR>
AI_TUTOR_ENABLED=false
VOICE_TUTOR_ENABLED=false
TELEGRAM_STARS_ENABLED=true
BILLING_PAYLOAD_SECRET=<test-only random secret, at least 32 characters>
BILLING_SUPPORT_CONTACT=<monitored test contact>
BILLING_TERMS_TEXT=<exact text from the approved test-only terms>
BILLING_TERMS_VERSION=stars-test-YYYY-MM-DD
BILLING_TERMS_APPROVED=true
BILLING_NET_MICRO_USD_PER_XTR=<reviewed test assumption>
BILLING_ECONOMICS_REVIEWED_ON=<YYYY-MM-DD>
```

The mode-`0600` credential file contains exactly two fields and is loaded by
both the bot runtime and the no-network preflight:

```json
{"bot_token":"<test-server-token>","test_user_id":123456789}
```

Do not also set inline `BOT_TOKEN` or `TELEGRAM_TEST_USER_ID`; conflicting
sources fail closed.

The test runtime refuses production or pilot access modes, extra allowlisted
users, the production database, a shared data directory, production terms, a
token inherited from `config.yaml`, or enabled AI/voice providers. It builds
Bot API requests under `https://api.telegram.org/bot<token>/test/METHOD_NAME`.

Validate the environment without contacting Telegram or creating an invoice:

```bash
python ops/mydictionary_stars_test.py --check
```

The checked-in test terms are
[`legal/telegram-stars-terms-ru-test.md`](legal/telegram-stars-terms-ru-test.md).
Use a dedicated test process and database; do not add these variables to the
production launchd service. A real test-environment purchase, refund, or
subscription mutation remains separately gated by `APPROVE_TELEGRAM_TEST_ENV`.
