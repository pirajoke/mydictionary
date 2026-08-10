# Mirror Quality v2 and 40-credit pilot

## Scope

Improve free-text Mirror answers using the quality mechanisms proven in the
local Zerkalo reference while keeping MY DICTIONARY language-focused,
privacy-minimized, metered, and fail-closed. Raise the approved pilot initial
credit entitlement from 5 to 40 without changing the model, price rates,
request cost, daily request limit, Voice, Stars, access mode, or production.

## Acceptance criteria

- AC-01: Mirror uses a dedicated structured response contract that starts with
  a direct Russian answer and can add target-language text, Latin
  transcription, Russian meaning, examples, and one next step only when useful.
- AC-02: A provider request includes the learner's active language, active pack
  or block vocabulary, grounded progress, and at most 12 recent Mirror turns.
- AC-03: Recent Mirror turns are bounded in Telegram in-memory `user_data` and
  are never written to PostgreSQL usage, audit, event, or metering records.
- AC-04: Mirror provider calls use the dedicated schema with medium reasoning
  and medium verbosity while preserving the exact approved model, default
  service tier, zero SDK retries, cost preflight, durable telemetry, breaker,
  and one-credit settlement.
- AC-05: The approved AI economics contract and rollout readiness require 40
  initial credits and continue to require 1 credit per request and the existing
  spend/rate limits.
- AC-06: A preview-first operator utility calculates the one-time delta needed
  to bring each active pilot learner's original free entitlement to 40. Execute
  mode uses a per-user idempotency key, emits aggregates only, and does not
  expose Telegram identities.
- AC-07: Deterministic quality cases cover all eight launch languages and
  translation variants such as `bonjour` -> `здравствуйте; добрый день`.

## Edge and error criteria

- EC-01: Dialogue history keeps only `user` and `assistant` text turns, trims
  each turn, rejects empty content, and retains at most 12 turns.
- EC-02: Without an active block, Mirror supplies a bounded context from the
  active public pack instead of the full 100-word pack.
- ERR-01: Invalid Mirror JSON or schema output fails the metered request and
  refunds the reserved credit under the existing recovery path.
- ERR-02: Mutated safety envelopes are rejected before metering.
- ERR-03: Re-running the 40-credit rollout with the same rollout ID cannot add
  credits twice, including after a learner spends credits.

## Constraints

- No real AI calls, payment operations, production credit grants, merge, or
  production deployment in this change.
- No model or price-rate change.
- Voice and Telegram Stars remain disabled.
- Zerkalo private prompts, context files, and user conversations are reference
  material only and are not copied into this repository.
