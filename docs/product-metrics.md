# Product metrics and operating focus

This document is the single source of truth for product metric definitions,
their owners, freshness, and the current operating focus. It does not authorize
pilot admission, messaging, feature activation, payment, merge, or deployment.

## North Star Metric

**NSM: durable words.** A durable word is a distinct learner vocabulary record
with `correct_count >= 3` and `interval >= 7`. Reaching this state means the
learner has repeatedly recalled the word well enough for the deterministic
spaced-repetition schedule to place the next review at least seven days away.

Report:

- total durable words among active learners;
- active learners with at least one durable word;
- durable words added during the last seven complete UTC days.

This is a product-value proxy, not a scientific claim that every word is
permanently remembered. A future delayed-recall evaluation may replace it.

## Current OMTM

For the six-week cycle **2026-08-08 through 2026-09-19**, the one metric that
matters is:

> D7 retained learners, always shown as retained / eligible and percentage.

The working target is at least **10 D7-eligible pilot learners** before making a
product decision. A **30% D7 rate** is a hypothesis for review, not an approved
commercial threshold. No feature should be enabled or disabled solely because
of a percentage calculated from fewer than ten eligible learners.

## Minimal quarterly OKR

**Objective (2026 Q3): prove that MY DICTIONARY is safe to operate and creates
repeat learning value before commercial activation.**

| Key result | Evidence | Status at 2026-08-08 |
| --- | --- | --- |
| KR1: active release, heartbeat, public/local health, and backup monitor remain green | Production health checks | Green on `d7bca5b` |
| KR2: reach at least 10 D7-eligible pilot learners and record retained / eligible | `pilot_overview(days=30)` | 0 D7-eligible |
| KR3: complete protected token-file cutover, rotation, and zero-residue sanitized-copy verification | Rotation receipt | Not complete |
| KR4: produce one encrypted off-site upload receipt and one isolated recovery-host restore receipt | Private recovery receipts | Not complete |
| KR5: complete one isolated Telegram test-environment purchase/refund/reconciliation/cancel cycle with zero production transactions | Stars test receipt | Not complete |

KR3-KR5 contain separate owner gates. Their presence here is not approval to
execute them.

## Metric definitions

| Metric | Formula | Included | Excluded | Source |
| --- | --- | --- | --- | --- |
| Pilot cohort | Distinct learners with `pilot_waitlist_joined` in the selected window | Learner role | Admin accounts | `AdminStore.pilot_overview` |
| Pilot approval | Distinct cohort learners with `pilot_access_approved` | Durable event | Current access state without event | `analytics_events` |
| Activation | Distinct cohort learners with `block_started` after joining pilot | Post-join learning | Historical sessions | `docs/pilot-operations.md` |
| Lesson completion | Distinct learners with `lesson_completed` or `block_completed`, reported separately | Allowlisted structured events | Message/answer text | `analytics_events` |
| D1 retention | Eligible learners with allowlisted activity from hour 24 inclusive to hour 48 exclusive after first join | Complete D1 windows | Activity outside window | `AdminStore.pilot_overview` |
| D7 retention | Eligible learners with allowlisted activity from hour 168 inclusive to hour 192 exclusive after first join | Complete D7 windows | Activity outside window | `AdminStore.pilot_overview` |
| Durable words | Distinct word records with `correct_count >= 3` and `interval >= 7` | Active learner progress | Erased/blocked learner progress | `word_progress` |
| AI completed use | Rows with `ai_usage.status = completed` | Settled completed attempts | Reserved/failed attempts | `ai_usage` |
| Stars paid conversion | Distinct paid learners / distinct eligible product viewers | Confirmed successful payments | Draft orders and test environment | Billing ledger + product events |

Retention rates must display the absolute numerator and denominator. `0/0` is
"not measurable", never "0% retention".

## Source ownership and freshness

| Domain | Owner | Freshness SLA | Stale-data rule |
| --- | --- | --- | --- |
| Runtime release, schema, heartbeat, flags | Production read-only probe | At decision time | Do not reuse an earlier deploy report |
| Public/local health | Health endpoints | At decision time | Stop launch action on any mismatch |
| Pilot funnel and D1/D7 | PostgreSQL aggregate | Daily during pilot | Label with query date and cohort N |
| Backup verification | Backup monitor | Maximum 26 hours | Treat older evidence as failed |
| AI/Stars economics | `config/launch-economics.json` | Maximum 30 days | Runtime fails closed when stale |
| Vocabulary counts | `content/catalog.json` | Per release | Recount after catalog change |
| Delivery status | GitHub main/PRs/checks | At handoff | Do not infer from local branches |
| Product decisions | GitHub issue #6 + this document | Weekly | Mark stale when older than seven days |

When sources conflict, production owns runtime facts, PostgreSQL owns durable
product/financial facts, GitHub owns merged delivery state, and versioned files
own formulas and policy. Historical comments never override a fresher canonical
source.

## Weekly check-in

Run once each week during the pilot. Keep it privacy-safe and five lines long:

```text
Week ending: YYYY-MM-DD
OMTM: D7 retained/eligible/rate; cohort N; delta from prior week
Health: release/schema/heartbeat/public/local/backup
Gates: token / off-site restore / Stars test / AI / Voice
Decision: continue, change one hypothesis, or stop
Removed from scope: one item intentionally not pursued
```

Do not auto-approve users, send reminders, or change features from this report.

## Privacy-safe history

| Snapshot | Cohort | Funnel summary | D1 | D7 | Public health |
| --- | ---: | --- | --- | --- | --- |
| 2026-08-06 | 1 | active 1; onboarding 1; block started/completed 1/1 | 0 eligible | 0 eligible | 200/ok |
| 2026-08-07 | 2 | active 2; approved 1; onboarding 2; block started/completed 1/1 | 0/2 (0%) | 0 eligible | 200/ok |
| 2026-08-08 | 2 | active 2; approved 1; onboarding 2; block started/completed 1/1 | 0/2 (0%) | 0 eligible | 200/ok |

No learner identifiers or message content belong in this history.
