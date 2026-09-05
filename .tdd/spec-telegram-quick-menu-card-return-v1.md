# Telegram quick menu and persistent block cards v1

Locked: 2026-09-05

## Goal

Replace the duplicated persistent language keyboard with the learner's four
most-used bot actions, while keeping the selected vocabulary block available
when the learner switches between study, quiz, and written modes.

## Acceptance criteria

- AC-1: The persistent Telegram reply keyboard contains exactly four localized
  actions in every supported interface locale: continue lesson, review words,
  AI tutor, and progress audit. It contains no content-pack/language labels.
- AC-2: Telegram's visible slash-command menu prioritizes the same learning
  journey (`continue`, `review`, `learn`, `stats`, optional `ai`, `privacy`,
  `help`) and keeps optional Mini App/referral entry points when enabled. It
  does not advertise the duplicated `lang` command. The `/lang` handler
  remains callable and language selection remains available in the Mini App.
- AC-3: A successful language switch and the regular `/start` surface replace
  any legacy language reply keyboard with the localized quick-action keyboard.
- AC-4: Quick actions dispatch only their exact allowlisted localized labels.
  Continue resumes a valid incomplete block or starts today's lesson; review
  starts the due review; AI opens the existing read-only Tutor entry surface;
  audit shows deterministic progress. Opening the quick menu itself never
  invokes an AI provider or charges credits.
- AC-5: Switching an active vocabulary block to quiz or written mode preserves
  `block_all_indices` exactly and does not delete previously displayed word
  cards.
- AC-6: Quiz and written exercise surfaces expose a localized return-to-cards
  action. Returning restores the original block study list with the exact
  selected indices, rotates the callback session, and performs no answer,
  progress, XP, or billing mutation.
- AC-7: The block summary also exposes the return-to-cards action so the same
  selected words can be self-studied again.

## Edge and failure criteria

- EC-1: Reply-keyboard labels and callback payloads remain bounded by Telegram
  limits and contain no learner or chat identifiers.
- EC-2: A completed/invalid block is not accidentally resumed as an active
  exercise; continue safely starts today's lesson.
- ERR-1: Malformed, stale, or wrong-block return callbacks fail closed through
  the existing stale-button response and do not change state.
- ERR-2: AI-disabled quick action returns the existing localized disabled
  response without provider or metering work.

## Constraints

- Preserve deterministic learning when AI, Voice, Stars, or Mini App are off.
- Preserve `/lang` as a manually callable compatibility route.
- Do not persist or expose Telegram identifiers, message contents, or secrets.
- Do not add dependencies or change the vocabulary catalog.

## Out of scope

- Restoring an interrupted block after a process restart.
- Changing spaced-repetition scoring or quiz correctness rules.
- Removing language selection from the Mini App or Settings.
