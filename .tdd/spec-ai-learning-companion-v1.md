# AI Learning Companion V1 — locked behavioral specification

Locked: 2026-08-23

## Outcome

Turn the existing Mirror path into the single conversational learning companion
for an onboarded learner. The companion must remain grounded in the learner's
real MY DICTIONARY state, answer compactly in the language of the current
message, remember only bounded consented dialogue, and preserve deterministic
cards, quizzes, writing, pronunciation and review when AI is unavailable.

## Acceptance criteria

- **AC-1 — Message-language reply.** For a supported, confidently detectable
  message language, learner-facing companion content uses that language. When
  the message is empty, too short or ambiguous, it uses the persisted interface
  locale. Script detection covers Russian, Japanese, Arabic and Chinese;
  high-confidence lexical detection covers English, French, German and Spanish.
- **AC-2 — Grounded learner context.** The provider payload includes a bounded
  learner context built only from the product profile, grounded progress and
  active learning block: onboarding state, target language, active pack,
  learning goal, daily word goal, learner level, learning stage and whether an
  active block exists. It contains no Telegram/user identifier, username, name,
  credential or raw analytics event.
- **AC-3 — Stage-aware guidance.** The learning stage is deterministic:
  `starting` before meaningful progress, `review_due` when reviews are due,
  `needs_practice` when weak words exist, and `building_habit` otherwise. The
  provider is instructed to use the stage for at most one relevant next step,
  never to invent progress.
- **AC-4 — Bounded memory and cost.** At most the newest eight dialogue turns
  are sent to the provider. The payload includes an immutable compact reply
  policy: at most two short paragraphs, at most one optional example and at
  most one next step. The total provider payload remains under the existing
  12,000-character fail-closed bound.
- **AC-5 — Free deterministic turns.** Greetings and capability questions use
  no AI provider request and are rendered in the resolved message language.
- **AC-6 — Handler integration.** A normal free-text message after completed
  onboarding passes the resolved reply locale, grounded learner context,
  compact policy and at most eight recent turns through the existing metered
  Mirror request. Persisted memory is read/written only when the existing
  `MIRROR_MEMORY_ENABLED` gate permits it.
- **AC-7 — Versioned prompt contract.** Runtime uses a new immutable Mirror V3
  prompt contract that explicitly consumes learner context and compact reply
  policy while preserving the existing safety envelope and response schema.

## Edge and error criteria

- **EC-1 — Locale fallback.** Unsupported Latin text, emoji-only text, numbers,
  mixed/ambiguous text and unknown interface locales fall back safely through
  the canonical locale normalizer.
- **EC-2 — Context minimization.** Oversized or malformed context values are
  normalized, truncated or rejected; unknown learner-context fields fail
  closed.
- **ERR-1 — Existing gates remain authoritative.** Missing onboarding, access,
  AI consent, credits, quota, provider readiness or provider success follows
  the existing localized deterministic fallback and never bypasses metering.

## Constraints

- No new dependency or external provider call.
- No schema migration in V1; reuse current profile, progress and Mirror memory.
- No raw learner text in analytics, logs or quality records.
- No production flag activation, credential action, merge or deployment.
- Do not reorder onboarding or duplicate its existing image/card flow in V1.
- Deterministic learning remains the primary non-AI path.

## Explicitly out of scope

- Enabling AI, Voice, Stars or durable memory in production.
- Changing credit pricing, grants, subscriptions or payment behavior.
- Long-term semantic/vector memory, embeddings or cross-user retrieval.
- Live production AI evaluation or Telegram messages.
