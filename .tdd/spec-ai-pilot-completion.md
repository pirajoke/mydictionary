# AI Pilot Completion — Locked TDD Spec

## Outcome

Make the existing free, allowlisted MY DICTIONARY AI tutor independently
launchable without enabling Voice or Telegram Stars. Preserve all existing
metering, breaker, budget, privacy and deployment controls.

## Acceptance criteria

### AI processing consent

- **AC-01** — When `AI_TUTOR_ENABLED=true`, runtime configuration requires a
  safe immutable `AI_CONSENT_VERSION` and a reviewed
  `AI_PROCESSING_NOTICE` of 40–1000 characters. Disabled AI remains
  fail-closed without these values.
- **AC-02** — `ai_processing` is a supported versioned consent type in both
  application validation and the PostgreSQL schema. Migration `0013` upgrades
  and downgrades the consent check constraint without changing existing rows.
- **AC-03** — `/ai` and the active-block AI button never reserve credit or call
  the provider until the learner accepts the current AI consent version.
  Acceptance resumes only the still-valid pending request; cancel, expiry,
  malformed callbacks and stale block sessions perform no AI call.
- **AC-04** — `/privacy` shows AI consent state, allows revocation, clears any
  pending AI request, and learning-data erasure removes `ai_processing`
  consent while retaining billing consent according to the existing policy.

### Approved AI-only pilot contract

- **AC-05** — The checked-in economics snapshot is reviewed on `2026-08-09`,
  uses a 30-day maximum age, marks only the AI section `approved`, grants five
  initial pilot credits, charges one credit per request, and retains Voice and
  Stars as disabled/candidate surfaces.
- **AC-06** — The approved short-context prices are exactly USD `0.20` input,
  `0.02` cached input, conservative `0.25` cache-write and `1.20` output per
  million tokens. Snapshot validation and rendered non-secret environment
  preserve the existing day/month/in-flight budgets, default tier and zero SDK
  retries.
- **AC-07** — AI pilot readiness is evaluated only against AI-specific gates:
  approved/current exact snapshot, model/tier/rates, consent version/notice,
  migration `0013`, eight-language deterministic contract, closed breaker,
  zero in-flight exposure and empty fallback journal. Disabled Voice and Stars
  do not block the free AI pilot; enabling them remains independently gated.

### Synthetic live-provider smoke

- **AC-08** — A dedicated operator command has a read-only preview by default
  and makes no provider call unless `--execute` and the exact synthetic-smoke
  approval environment gate are both present.
- **AC-09** — Execution performs at most one provider attempt using a fixed
  repository-owned eight-language evaluation fixture, no Telegram identity,
  no learner prompt/history and no production credit mutation. It validates
  returned model/tier, structured output, grounding and configured cost limit.
- **AC-10** — The smoke writes an owner-only (`0600`) atomic JSON receipt with
  only aggregate date, model/tier, token categories, cost, latency and
  pass/fail fields. It never stores prompt, response, API key, provider request
  ID, Telegram ID or local absolute paths.

## Edge and error criteria

- **EC-01** — A new consent version invalidates earlier acceptance.
- **EC-02** — Existing billing and voice consent rows survive migration and
  remain independently revocable.
- **EC-03** — The synthetic smoke refuses a second provider attempt for the
  same run identifier or an existing receipt.
- **ERR-01** — Missing/unsafe AI consent configuration fails startup before any
  provider attempt.
- **ERR-02** — Stale/tampered/unapproved economics, open breaker, non-zero
  in-flight exposure, non-empty fallback journal or wrong migration fails
  readiness without changing feature flags.
- **ERR-03** — Provider timeout, wrong model/tier, invalid output, storage
  failure or cost above the configured threshold produces a sanitized failed
  receipt and leaves activation fail-closed.

## Constraints

- No Telegram Stars product activation, invoice, payment, refund or credential
  change.
- No Voice activation or public-access change.
- No prompt, response, secret, learner identity or absolute production path in
  Git, logs, receipts, PR text or manager summaries.
- No merge, production restart, live provider call or deploy in this TDD stage.
- Existing deterministic dictionary learning remains available independently
  of AI.

## Canonical verification

- Targeted `python -m unittest` files for AI settings, handlers, storage,
  privacy, economics, rollout readiness and synthetic smoke.
- Full `python -m unittest discover -s tests -v` against the repository's
  configured PostgreSQL environment.
- `python -m compileall`, JSON validation and `git diff --check`.
