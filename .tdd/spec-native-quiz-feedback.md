# Native quiz answer feedback

## Goal

Make a Telegram quiz answer teach before it advances: preserve explicit
correct/incorrect feedback with the canonical word details, then place the
next question or summary below it as a new chat message.

## Acceptance criteria

- **AC-1 — Correct feedback.** An accepted correct quiz callback replaces the
  answered question with `✅` and the canonical word details, with no active
  answer keyboard left behind.
- **AC-2 — Incorrect feedback.** An accepted incorrect quiz callback replaces
  the answered question with `❌` and the same canonical word details.
- **AC-3 — Chat-order continuation.** After feedback, the next question is
  sent as a new message below it; on the final word, the summary is sent below
  it instead.
- **AC-4 — Shared modes.** The behavior applies to both manually selected
  `quiz` blocks and quiz-effective questions inside `adaptive` Review.

## Edge cases and failures

- **EC-1.** SRS/XP scoring remains delegated to the existing atomic
  `block_advance` path exactly once.
- **ERR-1.** Stale, non-current, malformed, or wrong-effective-mode callbacks
  remain rejected without feedback, scoring, or advancement.
- **ERR-2.** If durable scoring rejects the answer, success/error feedback is
  not rendered over the original question.

## Constraints

- Keep Telegram chat as the primary learning surface.
- No artificial delay, extra confirmation click, dependency, schema change,
  Mini App change, or answer-text persistence.
- Preserve existing localization, Markdown formatting, pronunciation, SRS,
  XP, completion summary, and retry-mistakes behavior.

## Verification map

Behavior tests live in `tests/test_native_quiz_feedback_v1.py`; existing
learning-block, adaptive-review, native-session, and native-chat suites are the
regression boundary.
