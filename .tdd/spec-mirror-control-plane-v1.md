# Mirror Control Plane v1

Status: locked 2026-08-11

## Goal

Make Mirror answers contextual, evidence-based, configurable, and measurable while
adding safe voice practice and voice-note translation. The implementation must
remain disabled/fail-closed at production runtime until a later deployment and
feature-flag approval.

## Acceptance criteria

### AC-01 Communication policy

- Mirror exposes six fixed communication modes: `teacher`, `conversation`,
  `coach`, `practice`, `brief`, and `exam`.
- The control plane stores an enabled mode list, default mode, answer depth
  (`compact`, `balanced`, `deep`), and learner level (`adaptive`, `a1`-`c1`).
- Every mode has bounded administrator guidance. The immutable safety envelope
  cannot be edited or overridden.
- Unknown values, empty enabled-mode lists, unsafe guidance, and disabled default
  modes are rejected atomically.

### AC-02 Preferences and administration

- Learners keep isolated mode, depth, and level preferences. Erased users fall
  back to safe defaults and cannot persist new preferences.
- Telegram Settings shows only enabled modes and adds no new public bot command.
- The protected admin page can change defaults, enabled modes, depth, level, and
  per-mode guidance with CSRF protection.
- Every successful control-plane update stores a versioned snapshot and a
  privacy-safe audit entry containing field names and hashes, not prompt text.
- An administrator can restore an earlier snapshot; restore is also audited.

### AC-03 Contextual task routing

- Mirror classifies learning questions into progress review, translation nuance,
  correction, grammar, pronunciation, practice, and general conversation.
- A natural progress question uses the metered AI path after current consent,
  rather than returning only the deterministic summary.
- `/stats` and the deterministic fallback remain free and available when AI is
  disabled, consent is absent, credits are unavailable, or the provider fails.

### AC-04 Deep progress evidence

- The grounded snapshot contains lifetime accuracy, tracked and learned words,
  due reviews, streak, recent activity, and ranked weak terms.
- Where durable historical data cannot support a trend, the snapshot says that
  trend is unavailable; it must not invent improvement or decline.
- Provider input includes task kind, communication mode, answer depth, learner
  level, bounded recent dialogue, and the grounded snapshot.
- The response contract requires a direct Russian-first answer, grounded
  evidence when available, a useful interpretation, and one concrete next step.
  It must avoid generic greetings, praise, and unsupported claims.

### AC-05 Privacy-safe quality feedback

- Every completed Mirror response records a privacy-safe quality audit keyed to
  its metered request: task, mode, depth, level, contract version, response
  length, evidence/example counts, next-step presence, and deterministic score.
- No question text, answer text, transcript, Telegram profile data, or provider
  secret is stored in the quality audit.
- The Telegram response can receive one idempotent helpful/not-helpful rating.
  A user cannot rate another user's response.

### AC-06 Analytics

- Admin analytics supports 7/30/90-day ranges and reports learning engagement,
  progress quality, Mirror success/failure, helpfulness, cost, latency, and
  voice completion without exposing message or transcript content.
- Mode/task/level breakdowns distinguish no-data from zero performance.
- The dashboard and AI/Voice views remain usable at desktop and mobile widths.

### AC-07 Voice modes

- The voice entry point presents pronunciation, guided phrase, and voice-note
  translation modes without adding a public command.
- Pronunciation and guided phrase modes remain scoped to the active learning
  block and preserve the existing text-match honesty disclaimer.
- A new voice prompt or reference retires the previous replaceable voice message
  so repeated taps do not create an unbounded audio stack.

### AC-08 Voice-note translation

- Outside an active practice session, the translation mode accepts one bounded
  Telegram voice note, checks current voice consent before download, and keeps
  raw audio only in process memory for the provider request.
- The source language is auto-detected. Russian input translates to the active
  target language; non-Russian input translates to Russian.
- The result is Russian-first and contains detected language, source transcript,
  translation, Latin transcription when applicable, and optional replaceable
  reference audio.
- STT and translation are separately metered. If translation fails after a
  billable transcription, the learner receives the transcript and an honest
  partial-result notice; no duplicate provider attempt is hidden.

### AC-09 Consent and runtime gates

- Enabling durable dialogue or voice translation requires reviewed immutable
  consent versions and notices matching the actual data sent and retained.
- Existing consent versions do not silently authorize broader history or voice
  translation processing.
- Voice translation is disabled by default and requires positive reviewed cost
  settings. Raw audio is never persisted.

### AC-10 Language matrix

- Deterministic contracts cover English, French, German, Japanese, Arabic,
  Chinese, Russian, and Spanish.
- Script languages preserve target writing and a Latin reading aid; Russian
  remains the explanation/meaning language.

## Error and boundary criteria

- ERR-01: Invalid admin policy updates make no database changes.
- ERR-02: Provider, storage, or metering failures remain fail-closed and never
  fabricate a translation, score, or successful completion.
- ERR-03: Voice is rejected before download for missing consent, excessive size,
  excessive duration, disabled mode, or inactive learner access.
- ERR-04: Feedback callbacks are idempotent and ownership checked.
- EC-01: Policy strings and provider payloads remain within existing bounded
  limits and preflight cost controls.
- EC-02: Migration upgrade/downgrade preserves existing style and progress data.
- EC-03: Empty datasets render explicit no-data states in admin analytics.

## Out of scope

- Live microphone/WebRTC streaming inside Telegram chat.
- Production deployment, flag changes, credential changes, AI provider calls,
  Stars transactions, refunds, or product activation.
- Phoneme-level acoustic scoring or claims that transcript similarity measures
  accent quality.
- Copying Zerkalo user content, private context, or psychological-support prompts.
