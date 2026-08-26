# Product metrics and operating focus

This is the single source of truth for product metric definitions, owners,
freshness and the current operating focus. It does not authorize outreach,
feature activation, payment, credential work, merge or deployment.

## North Star Metric

**Durable words** are distinct learner word records with
`correct_count >= 3` and `interval >= 7`. This records repeated successful
recall that schedules the next review at least seven days away. It is a
product-value proxy, not a scientific claim of permanent memory.

Report total durable words, learners with at least one durable word, and durable
words added during the last seven complete UTC days.

## Current one metric that matters

For the six-week cycle **2026-08-22 through 2026-10-03**:

> Public D7 retained learners, always shown as retained / eligible and rate.

Do not make a product decision until at least ten learners are D7-eligible. A
30% D7 rate is a review hypothesis, not an approved commercial threshold.

## Minimal quarterly objective

**Objective (2026 Q3): prove that MY DICTIONARY creates repeat learning value
and can be recovered safely before commercial activation.**

| Key result | Evidence | Status at 2026-08-26 |
|---|---|---|
| KR1: release/schema/heartbeat/public and loopback health and backup stay green | Fresh production probe | Green on OVH code release `af470389`; public route healthy |
| KR2: at least 10 D7-eligible public learners with retained / eligible recorded | Public product retention | Cohort 1; D1 1/1; 0 D7-eligible |
| KR3: one immutable encrypted off-site backup and one isolated restore receipt | Private recovery receipts | Complete: encrypted object/checksum verified; isolated restore at revision `0016` |
| KR4: one bounded current-runtime AI call with settled usage/cost | Private AI receipt + aggregate DB row | Complete: aggregate settled cost 1,341 micro-USD |
| KR5: one isolated Stars purchase/recovery/refund/cancel cycle with zero production transactions | Private `telegram_test` receipt | Not complete; the refunded 10 XTR production canary is separate operational evidence |

## Metric definitions

| Metric | Formula | Included | Excluded | Source |
|---|---|---|---|---|
| Public cohort | Learners whose first-ever `onboarding_started` falls in the selected window | Learner role | Admins and repeat onboarding outside the window | `AdminStore.product_funnel` |
| Activation | Cohort learners with `block_started` after first onboarding | Post-onboarding learning | Earlier activity | `analytics_events` |
| Lesson completion | Cohort learners with `lesson_completed` or `block_completed`, separately reported | Allowlisted events | Message or answer text | `analytics_events` |
| D1 retention | Eligible cohort learners with allowlisted activity in `[24h,48h)` after first onboarding | Complete D1 windows | Activity outside the window | `AdminStore.product_funnel` |
| D7 retention | Eligible cohort learners with allowlisted activity in `[168h,192h)` after first onboarding | Complete D7 windows | Activity outside the window | `AdminStore.product_funnel` |
| Historical pilot cohort | Learners with `pilot_waitlist_joined` in the selected window | Legacy controlled-pilot events | Public onboarding cohort | `AdminStore.pilot_overview` |
| Durable words | Word records with `correct_count >= 3` and `interval >= 7` | Active learner progress | Erased or blocked learner progress | `word_progress` |
| AI completed use | `ai_usage.status = completed` | Settled attempts | Reserved or failed attempts | `ai_usage` |
| Stars paid conversion | Distinct paid learners / eligible product viewers | Confirmed production payments | Draft orders and test environment | Billing ledger + product events |

`0/0` means not measurable, never 0% retention.

## Source ownership and freshness

| Domain | Owner | Freshness SLA | Stale-data rule |
|---|---|---|---|
| Release, schema, heartbeat, flags | Production read-only probe | At decision time | Never reuse a prior deploy receipt |
| Public and loopback health | Health endpoints | At decision time | Stop release on mismatch |
| Public D1/D7 | PostgreSQL aggregate | Daily during observation | Include query date and N |
| Backup verification | Backup monitor | 26 hours maximum | Older evidence is failed |
| AI/Stars economics | `config/launch-economics.json` | 30 days maximum | Runtime fails closed when stale |
| Vocabulary counts | `content/catalog.json` | Per release | Recount after catalog changes |
| Delivery state | GitHub main, PRs and checks | At handoff | Ignore unpublished local branches |
| Product decisions | GitHub issue #6 + this document | Weekly | Label stale after seven days |

When sources conflict: production owns runtime facts, PostgreSQL owns durable
product/financial facts, GitHub owns merged delivery state, and versioned files
own formulas and policy.

## Weekly five-line check-in

```text
Week ending: YYYY-MM-DD
OMTM: D7 retained/eligible/rate; cohort N; delta
Health: release/schema/heartbeat/public/loopback/backup
Gates: route / off-site restore / AI / Stars / token
Decision: continue, change one hypothesis, or stop; remove one item from scope
```

## Privacy-safe history

| Snapshot | Cohort | D1 | D7 | Public health |
|---|---:|---|---|---|
| 2026-08-22 | 1 public onboarding | 0/0 eligible | 0/0 eligible | Cloudflare 1033; loopback 200 |
| 2026-08-26 | 1 public onboarding | 1/1 retained | 0/0 eligible | Public and loopback healthy |

No learner identifiers or message content belong in this history.
