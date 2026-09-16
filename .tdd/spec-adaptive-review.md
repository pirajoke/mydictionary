# Adaptive native review

## Goal

Keep `Learn` and `Continue` as native Telegram flashcards, while turning the
primary `Review` action into one durable adaptive attempt over due SRS words.

## Acceptance criteria

- **AC-1 — Due-only entry.** A non-empty review uses only the due-word queue
  and starts one durable block whose parent mode is `adaptive`.
- **AC-2 — Per-word challenge.** Within that block, a word with fewer than
  three prior correct answers is shown as a four-choice recognition quiz. A
  word with three or more prior correct answers is shown as written recall.
- **AC-3 — Canonical scoring.** Accepted quiz and written answers reuse the
  existing atomic SRS and XP advancement, then render the next adaptive word.
- **AC-4 — Durable continuation.** Adaptive attempts survive save/restore, and
  retrying mistakes starts a fresh attempt that keeps the adaptive parent mode.
- **AC-5 — Analytics.** Review start events record `mode=adaptive` without
  changing the existing lesson-kind and pack metadata.

## Edge cases and invariants

- **EC-1.** An empty due queue keeps the existing localized empty-review
  response and does not create a block.
- **EC-2.** Daily lessons, Continue, and manually selected cards/quiz/written
  modes retain their existing behavior.
- **ERR-1.** Stale sessions, callbacks for the wrong word, callbacks for a
  written-effective word, and forged adaptive mode-selection callbacks are
  rejected without scoring or advancing.
- A written adaptive answer must be handled by the exercise before the Mirror
  free-text route.
- The parent mode remains `adaptive`; only the effective exercise changes per
  word.

## Out of scope

- New database migrations or dependencies.
- Mini App changes.
- Listening, sentence-context, or additional manual practice modes.
- Automatic duplicate questions inside one durable attempt.
- Replacing the existing end-of-block summary and `Repeat mistakes` action.

## Verification map

`tests/test_adaptive_review_v1.py` covers AC-1 through AC-5, EC-1, EC-2,
ERR-1, dispatcher precedence, persistence, retry, and shared SRS/XP behavior.
The native-chat, learning-entry, learning-block, and durable-session suites
remain the regression boundary.
