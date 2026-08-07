# AI and Telegram Stars Economics

This is a dated, fail-closed launch hypothesis. It is not an approval to enable
AI, publish terms, activate products, send an invoice, or accept a payment. The
machine-readable source is `config/launch-economics.json`; validate it with:

```bash
python ops/mydictionary_economics.py --check
python ops/mydictionary_economics.py --render-env
```

The rendered environment intentionally keeps `AI_TUTOR_ENABLED=false`,
`TELEGRAM_STARS_ENABLED=false`, and `BILLING_TERMS_APPROVED=false`. It never
renders API keys, payload secrets, safety salts, support contacts, or terms
text.

## Reviewed external assumptions

Snapshot date: 2026-08-06. Maximum runtime age: 30 days.

- OpenAI Standard short-context pricing for `gpt-5.6-luna` is $0.20 input,
  $0.02 cached input, $0.25 cache writes, and $1.20 output per one million
  tokens. Requests above 272,000 input tokens use the documented long-context
  multipliers. Sources: [pricing](https://developers.openai.com/api/docs/pricing)
  and [model contract](https://developers.openai.com/api/docs/models/gpt-5.6-luna).
- Digital goods inside Telegram use `XTR`; fulfillment follows a confirmed
  `successful_payment`, payment support must be available, and full refunds use
  Telegram's official refund path. Source: [Telegram Stars payments](https://core.telegram.org/bots/payments-stars).
- The reviewed developer reward is $0.013 per Star, can change, may remain
  unavailable for up to 21 days, and earned Stars expire after three years.
  Enabling topics in private chats currently adds a 15% fee to subsequent Stars
  purchases. Source: [Bot Platform Developer Terms](https://telegram.org/tos/bot-developers?setln=en).

The official reward reference is not guaranteed net income. The snapshot
therefore reserves 3,000 microUSD per XTR for withdrawal friction, taxes, and
value volatility and uses 10,000 microUSD per XTR in package formulas. Runtime
rejects a higher net assumption; if private-chat topics are enabled, the hard
cap falls again to 8,500 microUSD. Economics must be reviewed again if Telegram
changes either rule.

## AI limits

| Control | Draft value | Purpose |
| --- | ---: | --- |
| Credit cost | 1 credit/request | Stable learner-facing unit |
| Daily limit | 5 attempts/user/rolling 24h | Bounded pilot exposure, including failed attempts |
| Preflight request budget | 5,000 microUSD | Rejects a request before reservation from a conservative token upper bound |
| Retrospective response breaker | 5,000 microUSD | Opens the breaker after a billable response exceeds the threshold |
| Project daily budget | 25,000 microUSD | Bounds actual plus currently reserved exposure |
| Project monthly budget | 100,000 microUSD | Bounds actual plus currently reserved exposure |
| Concurrent in-flight budget | 5,000 microUSD | Serializes cross-user provider exposure in PostgreSQL |
| Provider input | 12,000 characters | Prevents unexpected context expansion before API call |
| Provider output | 1,000 tokens | Bounds response cost and latency |

The preflight estimate includes system instructions, serialized learner input,
the strict JSON schema, protocol overhead, and the full configured output
limit. It intentionally treats every UTF-8 byte as a possible token and prices
input at the more expensive input/cache-write rate. It is a local conservative
admission estimate, not the provider invoice.

Cross-user reservations lock one PostgreSQL budget row and count actual spend
plus all in-flight estimates. The provider client uses `max_retries=0` and
requests `service_tier="default"`, so one application attempt permits one SDK
provider attempt. Every returned response is metered before parsing, schema, or
grounding validation. An unknown attempted outcome, model/tier mismatch,
storage failure, or response-cost outlier opens the breaker. The authenticated
admin shows the state; reset requires a reason, no in-flight attempts, an empty
fallback journal, CSRF protection, and an audit entry.

The 5,000 microUSD response threshold is not a guaranteed per-request hard
cap. It is retrospective. Provider-side project limits and alerts remain
mandatory before any real call.

Runtime activation is bound to the exact approved snapshot ID and canonical
SHA-256. Model, tier, rates, limits, and review age are reloaded and checked on
every request, so a process running across the review-expiry boundary fails
closed without a restart. The returned model and tier must match the snapshot.

## Draft package hypotheses

The package model uses a modelled $0.005 provider cost per credit, $0.10 support
overhead per purchase, and a 10% refund reserve on estimated net revenue. The
$0.005 value is a pricing hypothesis, not a guaranteed provider ceiling.

| Product | Credits | Price | Net revenue | Estimated cost | Margin |
| --- | ---: | ---: | ---: | ---: | ---: |
| `ai-starter` | 50 | 60 XTR | $0.6000 | $0.4100 | 31.66% |
| `ai-value` | 150 | 160 XTR | $1.6000 | $1.0100 | 36.87% |
| `ai-monthly` | 100 / 30 days | 110 XTR | $1.1000 | $0.7100 | 35.45% |

All three products remain `draft`. Real measured token cost, response quality,
support time, refund rate, applicable taxes, withdrawal availability, and one
test-environment payment must replace these hypotheses before activation.

## Separate approval gates

1. Review and approve a final legal/privacy text; replace the draft terms
   version and set `BILLING_TERMS_APPROVED=true` only for that exact text.
2. Under explicit approval, grant one test learner a bounded credit balance and
   perform exactly one real AI call from a separate API project with one worker,
   one credit, daily limit one, `max_retries=0`, and `service_tier="default"`.
   Record returned model/tier, every token category, local cost, dashboard
   charge, latency, validation, and wallet settlement; turn AI off immediately.
3. Recalculate package cost from the measured call and keep products draft if
   any target margin is missed.
4. Under separate approval, use Telegram's test environment for purchase,
   duplicate-update idempotency, reconciliation, full refund, and subscription
   cancellation. A production payment remains a later decision.
5. Enable checkout only when current economics, approved terms, monitored
   `/paysupport`, verified backups, and clean reconciliation are all present.
