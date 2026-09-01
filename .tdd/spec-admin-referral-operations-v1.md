# Admin Referral Operations v1 — locked specification

Date: 2026-09-01

## Objective

Bring the operationally relevant parts of the recently added Mini App Settings
Hub and Telegram `/invite` referral flow into the protected admin console. The
console must answer whether the flow is ready, whether learners enter and
activate, and whether rewards reconcile, without exposing the referral graph.

## Acceptance criteria

- **AC-1 — protected navigation.** The authenticated admin console exposes a
  `referrals` tab labelled `Рефералы` inside the users area. Unknown tabs still
  fall back to the dashboard and anonymous access still redirects to login.
- **AC-2 — all-time funnel.** The referral tab shows privacy-safe all-time
  aggregates for issued codes, invite attributions, pending and activated
  referrals, rewarded activations, awarded credits, and activation conversion.
  Empty data produces numeric zeroes rather than an error.
- **AC-3 — bounded trend.** The tab supports exactly 7, 30, and 90 day ranges,
  defaults invalid input to 30, and renders one row per UTC day with invited,
  activated, and awarded-credit aggregates, including zero-value days.
- **AC-4 — honest economics.** The tab shows the canonical reward of 5 credits
  and the maximum of 10 rewarded activations per inviter, sourced from the same
  constants as the bot/store rather than copied business values.
- **AC-5 — accounting reconciliation.** The overview compares attributed reward
  credits with referral credit-ledger grants and exposes only a boolean/status
  plus aggregate totals. A mismatch is visible and never silently marked ready.
- **AC-6 — runtime readiness parity.** The tab reports whether Mini App, Settings
  Hub, bot username, and `/invite` sharing are ready using the same validated
  Mini App configuration used by the runtime. It must not render the public URL,
  bot username, bot token, referral code, Telegram identity, or message text.
- **AC-7 — current diagnostics.** The diagnostics tab compares the database
  revision with the current Alembic head discovered from the repository rather
  than a stale hard-coded revision, and reports Mini App/Settings Hub, `/invite`,
  Mirror memory retention, and Mirror voice-output readiness without secrets.
- **AC-8 — product adaptation map.** The referral page explains which recent bot
  capabilities already have admin coverage (Stars, Mirror, languages/content)
  and identifies the Settings Hub as a learner navigation surface, so operators
  do not mistake UI-only settings for separately configurable server features.

## Edge cases and failures

- **EC-1 — privacy after erasure.** Aggregate queries remain valid when referral
  rows are absent or cascaded; no attempt is made to reconstruct deleted pairs.
- **EC-2 — cap behavior.** Activated referrals beyond an inviter's reward cap
  remain activations but do not inflate rewarded-activation or credit totals.
- **ERR-1 — invalid runtime configuration.** Invalid Mirror flags or retention
  values render a not-ready diagnostic state instead of crashing the admin page.
- **ERR-2 — invalid range.** Non-integer or unsupported `days` values never reach
  an unbounded query and resolve to the 30-day view.

## Constraints

- Read-only feature: no mutation endpoint, CSV export, manual credit adjustment,
  invite generation, or feature-flag toggle.
- No new dependency and no database migration.
- Aggregate-only output: no inviter/invitee pairs, Telegram IDs, usernames,
  names, referral codes, deep links, raw audit details, or learner content.
- Existing Stars, Mirror, content, learning, safety, and authentication behavior
  remains unchanged.

## Out of scope

- Public leaderboard, referral fraud scoring, cohort messaging, manual rewards,
  code revocation, or per-user referral inspection.
- Moving Mini App learner preferences into server-side admin controls when those
  preferences already belong to the learner.
