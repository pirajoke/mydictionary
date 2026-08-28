# Locked spec: Zerkalo-style AI answer economics

## Source evidence

- The preserved Zerkalo runtime snapshot
  `pirajoke/zerkalo-telegram-bot-recovery@e6c96be478ac22781ef78c0a80c1653067918f1a`
  configures `HINT_CREDIT_COST=1`, charges before a normal/deep AI answer, and
  refunds that charge when generation fails.
- The independently recovered current economics contract in
  `CONTEXT_NEWS@e74c2571747acc233fa914538ee9f1c3cb27ac7f` locks the same rule:
  reserve one credit, keep one credit for a successful non-empty answer, and
  retain provider usage/cost only as operator telemetry.
- A privacy-safe production aggregate probe on 2026-08-28 found one active AI
  user with exactly five `block_tutor` attempts in 24 hours, no open project
  breaker, and no in-flight cost. This reproduces the screenshot as the legacy
  per-user `5/24h` cap rather than a credit or provider failure.

## Acceptance criteria

- **AC-1:** Typed Tutor and Mirror requests have no per-user rolling daily
  request cap. A learner with available credits may continue after five or one
  hundred earlier requests.
- **AC-2:** Each successful non-empty AI answer reserves and settles exactly one
  internal credit, independent of provider token usage or actual provider cost.
- **AC-3:** Provider token usage, latency, model, status, and micro-USD cost
  remain durable operator telemetry and do not change the learner charge.
- **AC-4:** A learner with exactly one available credit can receive one answer;
  a learner with zero available credits is rejected before the provider call.
- **AC-5:** Provider failure, invalid/empty output, or validation failure releases
  the full one-credit reservation and does not consume the learner credit.
- **AC-6:** Idempotent settlement/recovery invariants remain unchanged: one
  request cannot be charged twice and an uncertain provider outcome remains
  fail-closed for reconciliation.
- **AC-7:** The user-visible legacy phrase “Сработал защитный лимит AI” and its
  translations are removed. A genuine project-wide budget/breaker event uses a
  neutral localized temporary-unavailability message that explicitly says no
  credit was charged.

## Edge and error criteria

- **EC-1:** Runtime configuration and the approved economics snapshot express
  the absence of a per-user cap explicitly; missing or malformed values fail
  closed instead of silently restoring `5/24h`.
- **EC-2:** Existing historical `AIUsage` rows remain telemetry and never block
  a new request solely because of their count.
- **ERR-1:** Project-wide preflight, daily/monthly cost, in-flight cost, and
  circuit-breaker limits remain authoritative and are checked before provider
  spend.
- **ERR-2:** A global budget rejection performs no provider call and consumes no
  credit.

## Constraints and out of scope

- No database migration and no mutation of existing wallets, balances, usage
  rows, payments, products, Stars prices, subscriptions, or learner records.
- Voice/STT billing remains a separate reviewed contract; this change covers the
  typed Tutor/Mirror AI path shown in the reported defect.
- Keep one provider attempt, current model, prompt, response limits, consent,
  privacy, project budgets, telemetry journal, and recovery behavior unchanged.
