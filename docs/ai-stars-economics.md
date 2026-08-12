# AI and Telegram Stars Economics

This is a dated, fail-closed commercial launch candidate. It is not an approval to enable
AI, publish terms, activate products, send an invoice, or accept a payment. The
machine-readable source is `config/launch-economics.json`; validate it with:

```bash
python ops/mydictionary_economics.py --check
python ops/mydictionary_economics.py --render-env
```

The snapshot approves only the bounded free AI-pilot assumptions; it does not
activate a runtime. The rendered environment intentionally keeps
`AI_TUTOR_ENABLED=false`, `VOICE_TUTOR_ENABLED=false`,
`TELEGRAM_STARS_ENABLED=false`, and `BILLING_TERMS_APPROVED=false`. It never
renders API keys, payload secrets, safety salts, support contacts, or terms text.

## Reviewed external assumptions

Snapshot date: 2026-08-12. Maximum runtime age: 30 days.

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
- Groq lists `whisper-large-v3` transcription at $0.111/hour and applies a
  10-second minimum billable duration. The candidate requires Zero Data
  Retention before production voice activation. Sources: [Groq pricing](https://groq.com/pricing)
  and [Groq data controls](https://console.groq.com/docs/your-data).

The official reward reference is not guaranteed net income. The snapshot
therefore reserves 3,000 microUSD per XTR for withdrawal friction, taxes, and
value volatility and uses 10,000 microUSD per XTR in package formulas. Runtime
rejects a higher net assumption; if private-chat topics are enabled, the hard
cap falls again to 8,500 microUSD. Economics must be reviewed again if Telegram
changes either rule.

## AI limits

| Control | Draft value | Purpose |
| --- | ---: | --- |
| Initial free allowance | 40 credits once | Bounded pilot access without enabling Stars |
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

## Measured Gate-2 call

The snapshot pins the SHA-256 of
`config/measurements/ai-gate2-2026-08-07.json`. The report contains only
aggregate metering: one provider attempt, returned `gpt-5.6-luna`, default
service tier, 313 input tokens, 340 output tokens, 653 total tokens, 2,353
microUSD local settled cost, 4,674 ms latency, and a passed response validation.
It contains no learner ID, request ID, prompt, response, credential, or provider
charge identifier. The provider-dashboard charge was not captured in durable
telemetry and remains explicitly `not_recorded`.

## Voice cost envelope

Voice stays disabled. The candidate uses Groq `whisper-large-v3`, 1,850
microUSD per minute, a 10-second minimum billable duration, and a 30-second
application limit. Runtime rounds the estimate up: a request billed at the
minimum costs 309 microUSD, while a full 30-second request costs at most 925
microUSD under this reviewed rate. This is a local admission estimate, not a
guaranteed provider invoice.

## Commercial package candidate

The package model uses a conservative $0.006 provider cost envelope per credit,
$0.10 support overhead per purchase, and a 10% refund reserve on estimated net
revenue. The $0.006 value is a pricing hypothesis, not a guaranteed provider
ceiling and not the runtime preflight budget.

| Product | Credits | Price | Net revenue | Estimated cost | Margin |
| --- | ---: | ---: | ---: | ---: | ---: |
| `ai-mini` | 20 | 60 XTR | $0.6000 | $0.2800 | 53.33% |
| `ai-starter` | 50 | 100 XTR | $1.0000 | $0.5000 | 50.00% |
| `ai-value` | 150 | 250 XTR | $2.5000 | $1.2500 | 50.00% |
| `ai-monthly` | 100 / 30 days | 180 XTR | $1.8000 | $0.8800 | 51.11% |

The manifest labels all four packages `candidate`; the seeding CLI stores them
as `draft` and has no activation action. Each package has a 50% nominal margin
floor. The dashboard also applies the reviewed 8,500 microUSD/XTR deterioration
scenario while keeping the nominal cost envelope fixed: 45.09%, 41.17%, 41.17%,
and 42.48%. Each package therefore fails closed under that scenario; an average
margin cannot hide the individual failure. Support time, refund rate, taxes,
withdrawal availability, dashboard charge, and test-environment payment still
need evidence before activation.

## Separate approval gates

1. Complete seller identity, review the candidate legal/privacy text, and set
   `BILLING_TERMS_APPROVED=true` only with its exact version and SHA-256.
2. Under explicit approval, grant one test learner a bounded credit balance and
   perform exactly one real AI call from a separate API project with one worker,
   one credit, daily limit one, `max_retries=0`, and `service_tier="default"`.
   Record returned model/tier, every token category, local cost, dashboard
   charge, latency, validation, and wallet settlement; turn AI off immediately.
3. Validate and seed the exact candidate catalog with
   `ops/mydictionary_commercial_launch.py`; keep every product draft if any
   target or stress margin is missed.
4. Under separate approval, use Telegram's test environment for purchase,
   duplicate-update idempotency, reconciliation, full refund, and subscription
   cancellation. A production payment remains a later decision.
5. Enable checkout only when current economics, approved terms, monitored
   `/paysupport`, verified backups, and clean reconciliation are all present.
