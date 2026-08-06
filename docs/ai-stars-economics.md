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
| Cost circuit breaker | 5,000 microUSD/request | Blocks later requests after a completed outlier |
| Provider input | 12,000 characters | Prevents unexpected context expansion before API call |
| Provider output | 1,000 tokens | Bounds response cost and latency |

The rolling limit is serialized by the learner wallet lock. The global cost
breaker reads completed usage for the same action/provider, including provider
aliases that return a different snapshot model name. A small
cross-user race remains possible before the first outlier is completed; public
activation therefore still requires provider budget alerts and a bounded pilot.

## Draft package hypotheses

The cost model uses the worst-case $0.005 provider ceiling per credit, $0.10
support overhead per purchase, and a 10% refund reserve on estimated net
revenue.

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
   perform one real AI call. Record tokens, cache categories, latency, output
   validation, cost, and wallet settlement; turn AI off immediately afterward.
3. Recalculate package cost from the measured call and keep products draft if
   any target margin is missed.
4. Under separate approval, use Telegram's test environment for purchase,
   duplicate-update idempotency, reconciliation, full refund, and subscription
   cancellation. A production payment remains a later decision.
5. Enable checkout only when current economics, approved terms, monitored
   `/paysupport`, verified backups, and clean reconciliation are all present.
