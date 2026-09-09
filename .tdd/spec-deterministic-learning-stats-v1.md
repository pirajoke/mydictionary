# Deterministic learning statistics cards v1

Status: locked (revision 1 clarified AC-6 scope after runtime trace)

## Context

The inline `Vocabulary`, `Mistakes`, and `Progress` actions in the active lesson
Tutor menu currently call the paid AI companion. This produces inconsistent,
repetitive prose for facts that already exist in the learner database.

## Acceptance criteria

- **AC-1**: `bait:<active-session>:vocabulary`, `mistakes`, and `progress`
  read the authenticated learner's grounded progress snapshot and never call the
  AI provider, AI consent, reservation, or metering path.
- **AC-2**: Each action renders a distinct, compact, deterministic card in the
  current interface locale. The cards use stable gamified hierarchy, a ten-cell
  progress bar, factual metrics, and no model-authored prose.
- **AC-3**: The progress card shows accuracy, tracked/mastered words, due reviews,
  streak, and a single concrete focus based only on stored data.
- **AC-4**: The vocabulary card prioritizes tracked/mastered/due vocabulary and
  lists bounded weak terms when available. The mistakes card shows correct,
  wrong, accuracy, and bounded weak terms.
- **AC-5**: Cards attach native inline actions for review and the next lesson,
  using existing `start:review` and `start:daily` callbacks.
- **AC-6**: Once a statistics callback has been rendered, it remains usable if
  AI becomes unavailable: it does not check AI availability and never enters
  AI consent, provider, reservation, or metering. The explicit `ask` action
  remains AI-gated and otherwise unchanged.

## Edge and error criteria

- **EC-1**: Missing or malformed numeric snapshot fields render safe zero or
  placeholder values without crashing or inventing progress.
- **EC-2**: A learner with no progress sees a concise empty-state card and a
  start-first-lesson action.
- **ERR-1**: Stale, malformed, or unknown callbacks continue to fail closed and
  never reach either statistics storage or AI.

## Constraints

- Preserve authentication and active-session validation.
- Preserve the existing free deterministic `/stats` command.
- Do not add dependencies, change the database schema, or expose identifiers.
- Do not modify AI chat memory, language routing, voice, credits, or checkout.
- Telegram buttons do not support arbitrary background colors; color hierarchy
  is expressed through semantic emoji, typography, grouping, and action labels.

## Out of scope

- Reproducing Duolingo branding, artwork, proprietary copy, or exact UI.
- Changing the Mini App dashboard.
- Exposing the Tutor entry point when the complete `AI_TUTOR_ENABLED` feature is
  administratively disabled; the separate deterministic Statistics home action
  remains the supported no-AI entry point in that configuration.

## Revision note

AC-6 was narrowed from global Tutor-menu visibility to the three requested
statistics callbacks. Runtime tracing showed that global AI-off deliberately
hides the whole Tutor surface, while the user's requirement is that these
buttons do not use AI when present. Expanding feature-flag navigation would be
a separate product behavior change.
