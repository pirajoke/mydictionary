# Zerkalo-style Tutor communication v1

## Outcome

Make the MY DICTIONARY Tutor feel like the proven Zerkalo assistant: a short,
continuous conversation that uses recent context, answers directly, avoids
report-like duplication, and gives at most one useful next step. Keep MY
DICTIONARY's grounded learning context, consent, metering, privacy, languages,
and deterministic non-AI learning flows.

The canonical behavioral reference is the private `pirajoke/closeness-mirror`
assistant pipeline and `pirajoke/zerkalo-telegram-bot-recovery` chat pipeline:
bounded recent history, explicit short-continuation handling, compact
sentence-boundary output, one practical next step, and feedback collected at a
separate outcome surface instead of after every ordinary chat reply.

## Acceptance criteria

### AC-1 — Continuous short follow-ups

- A short follow-up such as `давай`, `дальше`, `что там`, `и что дальше`,
  `на чем фокус`, or an equivalent supported-locale phrase is recognized as a
  continuation when bounded recent dialogue exists.
- The provider payload contains an immutable application-owned continuation
  flag. Mirror v4 instructs the provider to use recent dialogue and answer the
  implied question instead of claiming that the message is incomplete or
  asking a generic clarification.
- The latest eight bounded dialogue turns remain the only provider-visible
  chat history. Empty history never fabricates continuity.
- Exact direct progress/focus requests are the intentional exception to paid
  continuation routing: AC-3 handles them locally from the current grounded
  snapshot even when recent dialogue exists. All other short continuations use
  the provider flag from this criterion.

### AC-2 — Human, compact rendering

- A normal Tutor response is at most 900 Unicode characters and ends at a
  sentence or paragraph boundary whenever possible.
- The response contains no more than three short paragraphs, one optional
  example, and one next step.
- Exact repeated facts across `answer`, evidence, interpretation, examples,
  and next step are rendered once. Internal schema labels and AI-credit
  footers are never shown.
- Mirror v4 answers the question directly, uses one thought per sentence,
  avoids generic praise and report-style restatement, and asks at most one
  concrete follow-up question.
- Provider output for Mirror is capped at 480 tokens; the deterministic cards,
  quizzes, written practice, pronunciation and ordinary Tutor menu remain
  unchanged.

### AC-3 — Free compact progress and focus

- Direct progress/focus requests in supported locales use the grounded product
  snapshot and do not call the AI provider, reserve a request, spend a credit,
  or require AI consent.
- Free routing uses a narrow explicit progress/focus classifier. Requests to
  continue a phrase, explain an error, resume an example, or discuss the word
  `weak` remain ordinary learning questions and never get diverted to the
  progress surface.
- The reply is localized and contains one compact facts line (accuracy,
  tracked words, due reviews, streak when available) plus one focus line.
- Weak/due words determine the focus when grounded data exists; otherwise the
  focus is one short five-word lesson. Missing history is stated plainly.
- Raw pack IDs, learner identifiers, database fields and private answers never
  appear.

### AC-4 — Uncluttered conversation feedback

- Ordinary Tutor/Mirror answers no longer append a second `Was this helpful?`
  message after every provider response.
- Existing feedback callbacks and previously rendered feedback buttons remain
  valid and owner-checked; this change removes only automatic per-turn
  prompting.
- No extra Telegram message is sent for a successful compact answer.

### AC-5 — Prompt and language compatibility

- Runtime loads a new reviewed `prompts/mirror-v4.txt`; v3 remains an immutable
  historical artifact.
- Prompt README and prompt-contract tests identify v4 as the active Mirror
  contract.
- Progress/focus copy and continuation recognition cover `en`, `fr`, `de`,
  `ja`, `ar`, `zh`, `ru`, and `es`. Learner words/examples remain unmodified.
- Typed questions still answer in the confident message language, falling back
  to the interface locale exactly as before.

## Edge and error cases

- A short standalone greeting is still handled by the existing free greeting
  path, not treated as a paid continuation.
- Malformed dialogue or an unknown task remains fail-closed.
- AI-disabled, missing consent, quota, paywall and provider failures remain
  localized for requests that genuinely require AI.
- A progress/focus request still works when AI is disabled or the daily AI
  quota is exhausted because it is deterministic and grounded.
- Truncation never splits a Unicode code point, emits an unfinished markdown
  fence, or exposes internal JSON.

## Verification

- New behavioral tests for continuation classification/payload, compact
  deduplicating rendering, token cap, deterministic progress/focus, no
  automatic feedback, prompt v4 loading, and all eight locales.
- Existing Tutor action menu, Mirror assistant/control-plane/quality,
  localization, metering, privacy, Voice and Stars regression suites.
- Full unit suite, `compileall`, `git diff --check`, complete diff review, and
  credential/private-data scan.
