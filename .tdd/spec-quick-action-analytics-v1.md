# Quick-action analytics v1

## Goal

Measure whether the learning-first Telegram reply keyboard moves learners into
practice and completion without storing button text, message content, or user
identity in aggregate product reports.

## Acceptance criteria

- **AC-1 — Selection event:** every exact quick-action dispatch records one
  `quick_action_selected` event before routing. The event uses the stable action
  key (`continue`, `review`, `mode`, `words`, `lang`, or a supported legacy
  action) as its `source`; it does not copy localized button text into
  properties.
- **AC-2 — Learning source:** when Continue or Review creates a new lesson from
  the persistent reply keyboard, `lesson_started`, `block_started`, and
  `block_mode_started` use `source=reply_keyboard`.
- **AC-3 — Existing entry points:** slash commands and Mini App/home callbacks
  retain the existing default `source=home`; their public call signatures remain
  compatible unless a source is explicitly supplied.
- **AC-4 — Resume visibility:** selecting Continue for an unfinished lesson
  still records `quick_action_selected` even though it resumes the existing
  session and creates no duplicate lesson-start event.

## Edge cases

- **EC-1:** unknown or inexact text records no quick-action event and is left to
  the existing free-text path.
- **EC-2:** analytics failure remains non-blocking through the existing
  `record_product_event` boundary.

## Constraints

- No schema or migration change.
- No new dependency.
- No Telegram identifiers, localized labels, messages, answers, or prompts in
  the event payload.
- Do not change word selection, SRS, scoring, button layout, or command routing.

## Out of scope

- Retrospectively attributing pre-release `source=home` events.
- Changing the D1/D7 formulas before the scheduled decision-grade checkpoint.
