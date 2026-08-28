# AI response experience v1

## Outcome

Make the MY DICTIONARY Tutor feel immediate, friendly, and easy to scan in
Telegram. Simple greetings, capability questions, and grounded progress
questions should answer locally without AI spend. Provider-backed answers
should use short emoji-led paragraphs, adaptive reasoning on the already
approved GPT-5.6 Luna model, and a temporary thinking indicator that is always
cleaned up.

This change preserves the approved Zerkalo economics: one successful
provider-backed answer costs one AI credit, deterministic answers cost zero,
and all project cost gates and telemetry remain fail closed. A second provider
model is not activated because the current approved economics snapshot covers
GPT-5.6 Luna only.

## Acceptance criteria

### AC-1 — Friendly, scannable replies

- Provider-backed Tutor replies contain one to three short paragraphs separated
  by a blank line.
- The first paragraph starts with `💡`, an optional supporting paragraph starts
  with `📌`, and an optional next step starts with `👉`.
- Exact facts are not repeated, internal schema labels are never rendered, and
  ordinary greetings never contain dictionary transcription or a report about
  the request.
- The existing 900-character hard ceiling, sentence-safe truncation, one-example
  limit, Unicode safety, and no-credit-footer rules remain enforced.
- Prompt v5 explicitly asks for direct, friendly, non-report-like answers and
  forbids exposing internal analysis.

### AC-2 — Free instant simple answers

- Narrow, explicit greeting-plus-capability phrases such as
  `привет, ты знаешь что делать?` and supported-locale equivalents route to a
  localized two-paragraph capability greeting with emoji.
- Narrow, explicit completed-progress phrases such as `что я уже прошел?` and
  supported-locale equivalents route to the deterministic grounded progress
  surface.
- These routes work with AI disabled or no credits and never require consent,
  call a provider, reserve metering, or create AI dialogue memory.
- Broad substring matching must not divert ordinary learning questions to a
  free route. Learner IDs, raw pack IDs, answers, and private records never
  appear.

### AC-3 — Adaptive latency on the approved model

- A pure application-owned classifier assigns every provider-bound request to
  `fast` or `deep`; the route is included in the immutable provider payload and
  validated before metering.
- `fast` covers short vocabulary, translation, pronunciation, greeting-like,
  and simple factual learning questions. It uses GPT-5.6 Luna with reasoning
  effort `none`, low verbosity, and at most 220 output tokens.
- `deep` covers grammar explanation, correction, comparison, multi-step
  exercises, analysis, or a long/complex request. It uses the same approved
  GPT-5.6 Luna model with reasoning effort `medium`, medium verbosity, and the
  existing 480-token ceiling.
- The provider model, service tier, pricing, telemetry, preflight budget,
  breaker, and one-credit settlement remain exactly the approved economics
  contract. The user cannot choose or tamper with the route.

### AC-4 — Temporary thinking experience

- Only a request that is about to call the AI provider sends Telegram's native
  `typing` chat action and one temporary standalone `🤔` message.
- The temporary message is deleted in `finally` after success, provider error,
  cancellation, quota/paywall rejection after preflight, or settlement error.
- Failure to send the action/emoji never blocks the provider. Failure to delete
  the emoji never hides the real answer or error.
- Deterministic greetings, capabilities, progress/focus, menus, consent prompts,
  AI-disabled responses, and no-credit responses do not create a thinking
  message.
- No GIF, sticker, external asset, file ID, or new dependency is introduced;
  Telegram clients may animate a standalone supported emoji themselves.

### AC-5 — Localization and compatibility

- New learner-facing copy is complete for `en`, `fr`, `de`, `ja`, `ar`, `zh`,
  `ru`, and `es`; learner vocabulary and examples remain unchanged.
- Voice-transcribed questions reuse the same response formatting and adaptive
  route, without duplicating the thinking indicator.
- Consent resume, Tutor action callbacks, Mirror memory, privacy revocation,
  feedback callbacks, deterministic learning blocks, Voice, Stars, and admin
  surfaces keep their existing contracts.
- Runtime loads new reviewed `prompts/mirror-v5.txt`; v4 remains an immutable
  historical artifact and the prompt README identifies v5 as active.

## Edge and error cases

- Empty or unsupported text keeps the existing localized fail-closed response.
- A malformed/tampered complexity route is rejected before provider or credit
  reservation.
- Provider failure, invalid JSON, invalid schema, zero credits, breaker-open,
  and budget failures retain their current localized response and refund rules.
- Concurrent requests own independent temporary emoji messages and delete only
  their own message.
- Telegram objects without chat-action or deletion support remain compatible
  with the test/mocked runtime.

## Verification

- Behavioral tests for eight-locale free phrases, paragraph/emoji rendering,
  fast/deep classification and exact provider parameters, route validation,
  thinking-message lifecycle, and v5 prompt loading.
- Existing Tutor menu, Zerkalo communication, Mirror assistant/control-plane,
  AI economics/metering, localization, privacy, Voice, Stars, admin, and
  deployment suites.
- Full unit suite, `compileall`, localization completeness, `git diff --check`,
  complete diff review, and credential/private-data scan.
