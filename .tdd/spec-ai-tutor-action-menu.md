# AI Tutor action menu

## Outcome

Replace the credit-consuming default block-tutor request with a short,
deterministic action menu. The actual paid answer uses the existing grounded
Mirror learning-companion path so it can consider the active lesson, product
progress, weak words, recent mistakes and bounded dialogue memory while
remaining compact.

## Acceptance criteria

### AC-1 — Free, concise entry point

- Pressing the active-block `AI tutor` button validates the current block and
  sends one localized explanation of what the tutor can do.
- The explanation is deterministic, no longer than 420 characters, and shows
  four buttons: vocabulary analysis, mistake analysis, progress analysis, and
  ask a question.
- Opening the menu never checks or requests AI consent, calls an AI provider,
  reserves/spends a credit, or writes AI dialogue memory.
- `/ai` without arguments opens the same free menu.

### AC-2 — Grounded compact analyses

- Each of the three analysis buttons validates the active block/session and
  submits exactly one predefined, localized, concise question through the
  existing Mirror learning-companion path.
- The provider payload keeps the active lesson and grounded product progress,
  uses the `brief` communication mode and `compact` answer depth, and remains
  governed by the Mirror policy of at most two short paragraphs, one optional
  example and one next step.
- Vocabulary analysis asks for the most useful known/weak vocabulary pattern;
  mistake analysis asks for the main observed error pattern; progress analysis
  separates measured facts from a single next step. Missing facts must be
  stated rather than invented.

### AC-3 — Natural one-question mode

- The ask button validates the session, records a private in-memory pending
  tutor state for at most ten minutes, and asks the learner to send one text
  question.
- The next ordinary text message consumes that pending state once and is sent
  through the same grounded compact companion path. Exercise-answer routing
  keeps priority over tutor pending state.
- An expired or stale pending state is discarded without a provider call or
  credit use; the ordinary Mirror route remains available.
- `/ai <question>` sends that question through the same compact companion path.

### AC-4 — Consent, metering and failures

- An analysis or typed tutor question with missing current AI consent presents
  the existing versioned consent prompt before any provider or metering call.
- Accepting valid consent resumes exactly the still-valid compact companion
  request. Cancelled, expired, malformed or stale callbacks do nothing paid.
- AI-disabled, missing-block, stale-session, quota, paywall and provider-error
  behavior remains fail-closed and localized.

### AC-5 — Localization and compatibility

- Menu copy, four button labels, typed-question prompt, three predefined
  analysis questions and stale pending-state notice exist for all supported
  interface locales: `en`, `fr`, `de`, `ja`, `ar`, `zh`, `ru`, `es`.
- Learner-facing chrome follows the interface locale; dictionary terms and
  learner content remain unchanged.
- Existing cards, quizzes, written practice, pronunciation, Voice, Stars,
  privacy deletion, Mirror memory retention and billing behavior are unchanged.
- No migration, dependency, public checkout change, or real provider call is
  required for this feature.

## Edge and error cases

- `bai` and action callbacks with malformed or non-current session identifiers
  are rejected before state/provider access.
- Repeated ask-button presses replace the pending state instead of stacking
  requests.
- Empty text never reaches the provider.
- Callback data stays within Telegram's 64-byte limit and no learner identifier
  is included in callback data or logs.

## Verification

- Focused behavioral tests for menu, action callbacks, pending text, consent
  resume, compact payload and all supported locales.
- Existing AI handler, learning block, Mirror companion, localization and
  privacy tests.
- Full unit suite, `compileall`, `git diff --check`, and credential/private-data
  diff scan.
