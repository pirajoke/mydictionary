# Contextual Telegram quick actions

## Goal

Make the persistent Telegram reply keyboard continue the learner's study flow instead of duplicating secondary Mini App navigation.

## Acceptance criteria

- **AC-1 — Learning-first hierarchy:** in every supported interface locale, the persistent keyboard contains exactly five actions in three rows: full-width Continue; Review + Practice mode; Choose words + Change language. AI, progress, and dictionary are absent from this keyboard and remain available through existing commands and Mini App surfaces.
- **AC-2 — Exact safe routing:** every new localized label resolves only on exact text, remains at most 64 characters, and the quick-action handler stays registered before free-text Mirror handling.
- **AC-3 — Contextual mode chooser:** Practice mode opens a localized inline chooser for Cards, Quiz, and Written practice. If an incomplete block exists, the chooser preserves its exact word set and session. Otherwise it prepares one SR-prioritized daily-size block in the active pack without starting or scoring it before the learner selects a mode.
- **AC-4 — Explicit word choice:** Choose words delegates to the existing `/learn` topic/list picker for the active pack instead of starting a random lesson.
- **AC-5 — Existing traction:** Continue still resumes the exact incomplete block; Review still starts only due words; Change language still uses the established language picker.

## Edge cases

- **EC-1:** if the active pack has no words, Practice mode returns the existing localized no-words message and no unusable callbacks.
- **EC-2:** a completed or stale block is not reused by Practice mode.
- **EC-3:** language tiles never return to the persistent quick keyboard.

## Constraints

- No changes to spaced-repetition selection, scoring, saved progress, Mini App navigation, or slash-command availability.
- No new dependency.
- All eight interface locales remain complete.
- Telegram callback data remains session-bound and within existing limits.

## Out of scope

- Redesigning the Mini App itself.
- Changing lesson size, topic taxonomy, or the word-priority algorithm.
- Removing AI, statistics, or dictionary functionality from the product.
