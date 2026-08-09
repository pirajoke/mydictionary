# MY DICTIONARY Mirror Assistant v1 — locked behavioral spec

Status: **LOCKED for RED**
Base: `origin/main@356dcd4110625157e6078c126bd2875740bf2da2`
Source of truth: GitHub Issue #6 plus the approved Mirror Assistant v1 contract.

## Acceptance criteria

- **AC-01 — default free-text route and exercise precedence.** After the existing access and onboarding gates admit a learner, ordinary free-form text is handled by Mirror without requiring `/ai`. An active written, quiz, poll, or other learning-answer state always receives the text first and is never intercepted by Mirror, even when the text resembles a greeting or capability question.
- **AC-02 — deterministic capabilities.** Greetings and capability questions return deterministic, administrator-configured safe capability text. This path performs no AI provider call or credit reservation and never returns an internal prompt, persona body, or immutable safety envelope.
- **AC-03 — deterministic grounded progress.** Resume, progress, and weakness questions return a user-isolated deterministic summary derived only from persisted `UserProgress`, `WordProgress`, enrollments, and privacy-safe product events. The summary includes language, active pack when evidenced, accuracy, due items, weak areas, and streak only when evidenced. Missing facts are explicitly unavailable. After a restart it never claims an exact unfinished card unless durable data proves it. The deterministic learning engine remains the source of truth.
- **AC-04 — gated explanatory AI.** Other free-form learning questions may use the existing AI path only after current access, completed onboarding, current versioned AI-processing consent, and the existing runtime, economics, credit, budget, breaker, and idempotency gates pass. An active block is not required. A successful explanatory request must traverse the real `AITutorService` metering boundary and provider adapter exactly once; a stub-only or permanently unavailable branch is not a valid implementation. Provider input is limited to administrator persona guidance, an immutable safety envelope, the current question, and a user-isolated grounded snapshot; it excludes raw history, unrelated users, secrets, internal identifiers, and mutable prompt overrides. Existing reservation, settlement, refund, and idempotency semantics remain authoritative.
- **AC-05 — protected administrator configuration.** An authenticated administrator can version and edit Mirror capability text and persona guidance through validated CSRF-protected settings. Successful changes are audited with checksums and without prompt bodies. Invalid or malicious guidance cannot override the immutable safety envelope. Capability, persona, and envelope bodies are never exposed through learner responses, health output, logs, audit details, or exports.
- **AC-06 — persisted response preference.** Each learner has exactly one response preference from `text`, `voice`, or `both`; the default is `text`. A user-facing command/settings flow can change it. Invalid values fail closed without mutation. Account erasure and per-user isolation apply to the preference: erasure must physically delete the preference row or clear its stored value, not merely mask a retained value on reads.
- **AC-07 — ephemeral voice output.** When voice output is separately enabled through the fail-closed `MIRROR_VOICE_OUTPUT_ENABLED` runtime gate and the learner has current speech consent, Mirror uses a concrete speech renderer with an injectable transport to generate Telegram-sendable audio bytes entirely in memory; a permanent fallback caused by an absent renderer is not a valid voice path. The renderer never uses or populates the persistent pronunciation/TTS cache. The gate defaults false, is independent from the voice-input activation flag, and is read without changing runtime or production configuration. `text` sends text only; `voice` sends voice only; `both` sends text then voice. If voice is disabled, consent is missing, or speech generation/storage fails, the learner receives a transparent safe text fallback. Mirror persists neither raw question/answer text nor audio and never double-charges on delivery failure.
- **AC-08 — unchanged consequential gates and regressions.** Mirror does not activate or alter voice input/output flags, AI flags, Telegram Stars, payments, public access, credentials, or production configuration. Existing `/ai`, privacy, access, billing, onboarding, exercise, and deterministic learning flows remain compatible.

## Edge criteria

- **EC-01 — empty history.** A learner with no progress or history receives an honest empty-state response and a safe next step; no progress, pack, accuracy, weak word, streak, or exact card is invented.
- **EC-02 — voice unavailable.** A false/missing voice-output gate or missing current speech consent causes no TTS/speech-provider call, no voice-output charge, and a transparent text fallback.
- **EC-03 — intent-looking exercise answer.** While a written/exercise answer is active, text matching greeting/capability intent remains an exercise answer and never invokes deterministic Mirror intent handling or AI.
- **EC-04 — locale boundary.** The existing eight AI launch locales (`en`, `fr`, `de`, `ja`, `ar`, `zh`, `ru`, `es`) remain covered. Unknown or missing locale data uses a safe fallback and never leaks prompt material.

## Error criteria

- **ERR-01 — invalid settings.** Invalid or malicious administrator guidance and invalid response modes are rejected without state mutation, unsafe content exposure, or audit prompt bodies.
- **ERR-02 — AI failure.** Provider failure produces a sanitized response, invents no learning answer, preserves reservation refund/idempotency semantics, and cannot double-charge.
- **ERR-03 — speech/storage failure.** Speech generation, delivery, or storage failure writes no audio to disk/cache, preserves a safe text fallback, persists no raw payload, and cannot double-charge.

## Constraints

- Persist no raw chat history, raw question, raw answer, transcript, or Mirror audio.
- Use no client/vault data and expose no secrets or internal prompt bodies.
- The deterministic engine owns progress and next-step decisions; an LLM may explain grounded facts but cannot create authoritative learning state.
- Do not activate production flags, Voice, Stars, payments, public access, or providers as part of this feature.
- Preserve account erasure, learner isolation, existing billing/credit semantics, and existing consent versions.

## Public behavior under test

- Telegram free-text and response-settings entry points.
- Deterministic learner-facing capability/progress rendering.
- Existing store behavior and migration round trip for Mirror preferences/settings.
- Existing protected admin HTTP surface, CSRF enforcement, and audit records.
- Existing metered AI service boundary with minimized Mirror context.
- Telegram text/voice delivery ordering and in-memory-only audio behavior.

## Explicitly out of scope

- Production deployment, restart, configuration mutation, provider calls, credentials, live user outreach, payments, Stars activation, public-access activation, merge, release, or migration execution outside disposable test databases.
- Persistent conversation history, recommendation memory, transcript history, audio caching, a new billing model, or authoritative LLM-generated progress.

## RED rule

Every criterion above must map to at least one public-behavior test. Failures must identify missing Mirror behavior rather than dependency, import, fixture, network, credential, or production setup failures.
