# Telegram Stars Billing

## User flow

1. `/buy` lists only active products when `TELEGRAM_STARS_ENABLED=true`.
2. The product callback creates a single-user signed order and sends an `XTR`
   invoice. `provider_token` is omitted.
3. Pre-checkout validates the signed snapshot and answers within ten seconds.
4. Only `successful_payment` creates the Stars payment row and grants credits.
5. A repeated successful-payment update returns the existing fulfillment and
   cannot grant credits twice.
6. `/terms` and `/paysupport` remain available independently of learner access.

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
| `BILLING_ORDER_TTL_SECONDS` | 300-86400; default 1800 |
| `BILLING_TERMS_TEXT` | learner-visible terms, at most 3500 characters |

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
amount, currency, and user mismatches must be resolved before enabling AI spend
or completing a refund.

`ops/mydictionary_billing.py reconcile` fetches bounded pages through
`getStarTransactions` and compares both directions without changing local
state. Refund and subscription writes require a named local record and an
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
