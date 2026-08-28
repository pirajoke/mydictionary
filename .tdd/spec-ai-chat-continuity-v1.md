# AI chat continuity v1

## Outcome

MY DICTIONARY should feel like a compact learning chat: it should answer broad
language-learning questions using recent consented dialogue and the learner's
grounded profile, while keeping simple questions fast and inexpensive. The
temporary Telegram indicator must be readable, varied by request type, and
must never be a standalone large emoji.

## Production reproduction

- A Russian request equivalent to “tell me about language-learning methods”
  was classified as `fast`.
- The provider returned `status=incomplete` at exactly 220 output tokens.
- The request was released with `AIProviderError` and billed zero credits.
- Durable Mirror memory remained enabled and contained recent dialogue.

No learner identifiers, messages, provider identifiers, or credentials belong
in tests, logs, receipts, or documentation.

## Acceptance criteria

### AC-1 — broad learning conversation uses the deep route

- Reviewed open-ended “tell/explain/discuss language-learning methods” requests
  in all eight supported interface languages resolve to `deep`.
- Short translation, meaning, and pronunciation requests remain `fast`.
- Route classification is pure and deterministic.
- `fast` remains reasoning `none`, verbosity `low`; `deep` remains reasoning
  `medium`, verbosity `medium`.

### AC-2 — natural chat continuity uses recent dialogue

- With non-empty recent dialogue, reviewed conversational follow-up prefixes
  such as “thanks, now tell me…”, “and what about…”, and their supported-locale
  equivalents set `is_continuation=true`.
- The provider payload contains the bounded newest dialogue in chronological
  order and the grounded learner context; no user identity is included.
- The active prompt instructs the model to use relevant dialogue naturally,
  answer the current question directly, and avoid claiming that context is
  missing when it is present.
- Empty history never fabricates continuity.

### AC-3 — compact varied thinking indicators

- A real metered request sends Telegram `typing` immediately before provider
  work and one temporary localized status message.
- The status is selected by observable request state:
  - `⚡` for fast standalone questions;
  - `🧠` for deep standalone questions;
  - `💭` for contextual follow-ups.
- Every status includes localized text after the emoji, so Telegram cannot
  render it as a giant standalone emoji.
- The temporary message is deleted in `finally`; concurrent requests delete
  only their own status. Send/delete failures remain non-blocking.
- No indicator is sent before consent, authoritative credit reservation, or
  provider readiness.

### AC-4 — enough structured-output room without changing credit economics

- Fast Mirror requests have a reviewed 320-token output ceiling; deep requests
  retain the 480-token ceiling.
- Preflight cost estimation uses the same route-specific ceiling.
- One successful answer still costs one AI credit; provider/incomplete/parse/
  validation failures bill zero and release the reservation.
- No provider retry is added.

### AC-5 — friendly no-charge failure copy

- A released provider/validation failure returns a concise localized retry
  message that explicitly says no AI credit was charged.
- The message exists in all eight supported locales and does not expose an
  exception, provider identifier, raw output, or internal policy.

### AC-6 — versioned prompt contract

- `prompts/mirror-v6.txt` is the active immutable runtime contract.
- `mirror-v5.txt` remains as historical evidence.
- Prompt README and prompt-contract tests identify v6 as active.

## Edge and error criteria

- EC-1: greeting/capability/progress deterministic routes remain free and do
  not create a thinking status or AI usage row.
- EC-2: recent dialogue remains bounded by the existing provider payload size
  ceiling; oldest turns may be removed only by the existing deterministic
  trimming rule.
- ERR-1: provider `incomplete` is never rendered, persisted as a dialogue turn,
  or billed.
- ERR-2: indicator callback cancellation occurs before provider-attempt marking
  and cannot open the breaker.

## Out of scope

- No new model, provider, dependency, migration, credential, price, Stars,
  Voice, consent, retention, or public-access change.
- No provider call or Telegram message is required for local verification.
