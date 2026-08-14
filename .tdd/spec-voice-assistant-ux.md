# Voice Assistant UX v1

Status: locked on 2026-08-14.

## Normal behavior

- AC-01: With current voice and AI consent, a voice note outside an active
  practice session is downloaded once, transcribed once, and routed to the
  same contextual Mirror assistant path as typed text.
- AC-02: An active pronunciation or guided-phrase session always takes
  precedence over free-form voice assistance and translation state.
- AC-03: A stale `translation` entry mode cannot trap the learner when voice
  translation is disabled; it is cleared and the note follows the normal
  voice-assistant path.
- AC-04: A newly displayed learning block exposes one clear action for
  practising all block words by voice. Once started, the learner sends one
  word per voice note and receives the next prompt automatically.
- AC-05: Exact and close recognition advance to the next word. A retry result
  persists the attempt but keeps the same expected word, explains the
  correction, and replays only that word's reference audio.
- AC-06: `/voice` explains the two voice behaviors (direct AI questions and
  block practice) and shows only modes that are currently enabled.

## Boundaries and failures

- EC-01: Voice consent and AI consent are checked before Telegram audio is
  downloaded or any provider is called. Consent can be granted inline; the
  learner then resends the note because raw audio is never retained.
- EC-02: Audio duration and size limits are checked before download and before
  provider work.
- ERR-01: A transcription/provider failure releases the reserved voice credit
  and never invokes Mirror.
- ERR-02: A completed transcription is billed once. The subsequent Mirror
  request uses its existing, separate AI metering contract.

## Constraints

- One pronunciation turn is one Telegram voice note; multi-word alignment
  inside a single recording is out of scope for v1.
- Feedback compares provider transcription with canonical block content. It
  must not claim acoustic, accent, or phoneme-level scoring.
- Voice translation remains a separate explicit mode when enabled.
- No schema migration, new dependency, live provider call, Stars/payment
  action, merge, production deploy, or production flag change is part of this
  implementation.
