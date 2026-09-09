# Varied Lexi tutor responses v1

Status: locked
Date: 2026-09-09

## Goal

Make Lexi's Telegram answers feel like a real conversation instead of rendering
every AI result with the same `💡`, `📌`, and `👉` template. Variation must be
driven by the learner's request type, remain concise, and preserve the existing
response language, dialogue memory, strict provider schema, metering, and safety
boundaries.

## Acceptance criteria

- **AC-01 Natural conversation:** `general_conversation` renders as natural
  prose without a mandatory leading emoji or a mandatory support-section marker.
- **AC-02 Translation:** `translation_nuance` renders the direct reply and any
  word/transcription/meaning details as a compact language card using relevant,
  non-repeated markers instead of the universal lightbulb/pin pair.
- **AC-03 Correction and grammar:** `correction` and `grammar` each use a
  distinct learning-oriented marker set so the visual structure communicates the
  answer type.
- **AC-04 Pronunciation and practice:** `pronunciation` prioritizes a listening
  marker, while `practice` presents the requested activity as an action or
  challenge rather than a report.
- **AC-05 Progress:** `progress_review` keeps its concise metric/action behavior
  but uses progress and goal markers rather than the universal marker pair.
- **AC-06 Bounded decoration:** a rendered response uses at most three section
  markers, never places two decorative markers side-by-side, and never repeats a
  section marker in one response.
- **AC-07 Prompt alignment:** the reviewed provider prompt explains the
  task-specific formats and no longer says the application always adds
  `💡`, `📌`, and `👉`.
- **AC-08 Existing contract:** parsing, deduplication, 900-character response
  ceiling, answer-depth behavior, selected response language, dialogue memory,
  credit settlement, and quality telemetry remain unchanged.

## Edge cases

- **EC-01 Unknown/omitted task:** an omitted or unknown-compatible task falls
  back to the natural conversation format rather than failing rendering.
- **EC-02 Sparse answer:** an answer with only `answer_ru` remains valid and
  produces non-empty learner-facing text.
- **EC-03 Provider decoration:** legacy provider-supplied `💡`, `📌`, or `👉`
  is stripped before the application applies any task-specific presentation.
- **EC-04 Duplicate support:** repeated facts across schema fields are rendered
  once, as before.

## Error criteria

- **ERR-01** Invalid provider schema remains rejected before rendering.
- **ERR-02** This change must not introduce learner IDs, raw private data, or
  new external dependencies into provider input or logs.

## Constraints

- The variation is semantic and deterministic by `task_kind`; it is not random.
- Use zero to three relevant emoji markers per response.
- Do not add headings such as internal task names or JSON field names.
- Do not alter the Telegram thinking-animation rotation.
- Do not alter the AI response schema or persisted dialogue format.

## Out of scope

- New AI models, pricing, credits, voice transcription, onboarding, Mini App UI,
  or database migrations.
