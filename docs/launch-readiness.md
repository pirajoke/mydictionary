# Launch Readiness Gate

Stage 7 converts the existing AI, voice, and Telegram Stars stack into a
fail-closed launch candidate. It does not enable a feature flag, call a paid
provider, issue an invoice, refund a payment, merge a pull request, or deploy a
release.

## Enforced gates

| Surface | Gate |
|---|---|
| Stars checkout | The learner must accept the current `BILLING_TERMS_VERSION` before products, order creation, and pre-checkout. Each order snapshots that version. |
| Voice processing | The learner must accept the current `VOICE_CONSENT_VERSION` before a session and again before Telegram audio is downloaded. The consent can be revoked in `/privacy`. |
| AI cost accounting | Enabling text AI requires an exact approved snapshot, current review, default service tier, positive prices, preflight/day/month/in-flight budgets, zero SDK retries, and durable response metering before validation. |
| Voice cost accounting | Enabling voice requires a positive per-minute estimate, consent version, and processing notice. |
| Stars reconciliation | Refund direction is compared with local state. A bounded, incomplete remote history is reported as truncated and cannot mark old local payments missing. |
| Product analytics | Intent remains a privacy-safe event; orders, payments, completed AI use, repeat purchases, and Stars totals are derived from durable ledgers. |
| Language quality | Deterministic AI and voice contracts run for English, French, German, Japanese, Arabic, Chinese, Russian, and Spanish. |
| Dependencies | CI and the Mac mini release builder install the exact `requirements.lock` resolution. |

Billing acceptance is retained with the mandatory financial record after a
learning-data erasure. Voice consent is learning-product data and is deleted.
Changing a consent version makes the previous acceptance insufficient for new
processing.

## Required runtime review

Keep all feature flags off while deploying migration `0012_ai_runtime_gates`.
Before any later activation, an operator must review and set:

```text
AI_INPUT_USD_PER_MILLION=<positive reviewed rate>
AI_CACHED_INPUT_USD_PER_MILLION=<positive reviewed rate>
AI_CACHE_WRITE_USD_PER_MILLION=<positive conservative rate>
AI_OUTPUT_USD_PER_MILLION=<positive reviewed rate>
AI_PRICING_REVIEWED_ON=<YYYY-MM-DD>
AI_PRICING_MAX_AGE_DAYS=<1-90; default 30>
AI_SERVICE_TIER=default
AI_ECONOMICS_SNAPSHOT_PATH=<approved immutable snapshot copy>
AI_ECONOMICS_SNAPSHOT_ID=<exact snapshot identifier>
AI_ECONOMICS_SNAPSHOT_SHA256=<canonical lowercase SHA-256>
AI_MAX_DAILY_REQUESTS_PER_USER=<1-100; draft 5>
AI_MAX_PREFLIGHT_COST_MICRO_USD_PER_REQUEST=<draft 5000>
AI_RETROSPECTIVE_BREAKER_MICRO_USD_PER_RESPONSE=<draft 5000; not a hard cap>
AI_MAX_PROJECT_COST_MICRO_USD_PER_DAY=<draft 25000>
AI_MAX_PROJECT_COST_MICRO_USD_PER_MONTH=<draft 100000>
AI_MAX_IN_FLIGHT_COST_MICRO_USD=<draft 5000>
AI_MAX_PROVIDER_INPUT_CHARS=<1000-50000; draft 12000>
AI_MAX_OUTPUT_TOKENS=<256-4000; draft 1000>
AI_METERING_JOURNAL_PATH=<private mode-0600 fallback path>

VOICE_COST_MICRO_USD_PER_MINUTE=<positive conservative estimate>
VOICE_CONSENT_VERSION=<immutable version identifier>
VOICE_PROCESSING_NOTICE=<reviewed learner disclosure>

BILLING_TERMS_VERSION=<immutable version identifier>
BILLING_TERMS_TEXT=<reviewed learner terms>
BILLING_SUPPORT_CONTACT=<monitored contact>
BILLING_NET_MICRO_USD_PER_XTR=<conservative net value>
BILLING_TERMS_APPROVED=true
BILLING_ECONOMICS_REVIEWED_ON=<YYYY-MM-DD>
BILLING_ECONOMICS_MAX_AGE_DAYS=<1-90; default 30>
BILLING_PRIVATE_CHAT_TOPICS_ENABLED=<reviewed boolean>
```

Use a conservative positive cache-write rate even when the selected provider
does not currently report that token category. This prevents a future provider
response shape from creating an unpriced cost path.

The dated assumptions, draft packages, and non-secret environment renderer are
documented in [`ai-stars-economics.md`](ai-stars-economics.md). The checked-in
terms file is explicitly a draft and cannot satisfy the approval gate by itself.

## Release sequence

1. Confirm the stacked PR order and green CI.
2. Build from an exact reviewed merge SHA using `requirements.lock`.
3. Create and validate a PostgreSQL custom-format backup.
4. Stop bot and admin, activate the candidate, and apply the reviewed current
   Alembic head.
5. Restart with AI, voice, and Stars still disabled; prove local/public health,
   Telegram heartbeat, admin diagnostics, content checks, and privacy erasure.
6. Admit a bounded pilot through the existing access control.
7. Under separate approval, run one consented test account through all eight
   languages without enabling public access.
8. Under separate approval, run a low-value Stars purchase, reconciliation,
   refund, and subscription-cancel test.
9. Enable paid access only after measured provider cost, support load, refund
   rate, and package margin satisfy the configured product floor.

## Stop conditions

Do not enable paid AI when any of these is true:

- the admin diagnostics show missing/stale pricing, unapproved terms, or
  unversioned consent documents;
- the AI breaker is open, a provider attempt has unknown outcome, the fallback
  metering journal is non-empty, or the runtime differs from its snapshot;
- a reconciliation issue is unresolved, including remote history truncation;
- a product has no positive measured cost or misses its margin floor;
- any launch-language deterministic evaluation fails;
- backup verification, migration, heartbeat, local health, or public health fails;
- payment support is unmonitored or the approved terms text is unavailable.

Turning checkout off prevents new invoices but does not disable fulfillment of
an already accepted successful payment. Never remove the payload secret or roll
the database back after payments without completing reconciliation.
