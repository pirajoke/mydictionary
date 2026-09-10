# Mini App Help and Privacy v1

Status: locked on 2026-09-09.

## Product intent

Move the long help instructions and privacy self-service out of the main
Telegram conversation and into native, localized Mini App detail views. Keep
Telegram commands as short entry points so users with older menus can still
reach the correct Mini App screen without receiving a wall of text.

## Acceptance criteria

- **AC-1 — Native Settings destinations.** The existing Settings rows
  `settings-help` and `settings-privacy` open an internal Mini App detail view.
  They must not call `openTelegramLink`, close the Mini App, or render a bot
  command response.
- **AC-2 — Accessible detail view.** The detail view has a localized heading,
  a real back button, a labelled content region, safe focus entry and return,
  Escape-key dismissal, at least 44px controls, responsive layout, RTL support,
  dark/light Telegram theme support, and reduced-motion support.
- **AC-3 — Useful help, no command dump.** Help explains the core learning flow
  in five concise steps: choose a language, start a lesson, reveal and rate a
  word, review due words, and add personal vocabulary. It provides internal
  calls to action for the first lesson/Profile and personal words/Dictionary.
  The help view does not show slash commands.
- **AC-4 — Truthful live privacy state.** Privacy explains learning-data,
  voice-transcript, AI-dialogue-memory, billing/audit retention, and the effect
  of erasure without inventing policy. It shows authenticated current state for
  AI consent, voice consent, and Mirror memory, plus configured retention days.
- **AC-5 — Privacy self-service.** From the Mini App a learner can revoke AI
  consent, revoke voice consent, or erase learning data. Requests use verified
  Telegram init data, an allowlisted action, strict JSON validation, the
  existing store/privacy operations, and rate limiting. Erasure requires an
  explicit client confirmation. A failed request never reports success.
- **AC-6 — Compact command entry points.** In a private chat, while Mini App is
  enabled, `/help` and `/privacy` send a short localized message with a Web App
  button targeted to `?view=help` or `?view=privacy`. They do not send the long
  instruction or policy text. Group chats and disabled/unconfigured Mini App
  retain a safe localized text fallback.
- **AC-7 — Complete localization.** All new visible copy, status text, button
  labels, errors, and accessible labels are non-empty in `en`, `fr`, `de`,
  `ja`, `ar`, `zh`, `ru`, and `es`.
- **AC-8 — Cohesive Lexi UI.** The internal screens reuse the existing Mini App
  typography, spacing, rounded surfaces, local SVG vocabulary, and orange/teal
  Lexi palette. No remote assets or new dependencies are introduced.

## Edge and error criteria

- **EC-1.** `?view=help` and `?view=privacy` open the requested detail after an
  authenticated bootstrap; an unknown or empty view is ignored and leaves the
  normal initial tab unchanged.
- **EC-2.** Missing consent versions, disabled voice/AI, or disabled Mirror
  memory produce honest unavailable/disabled states and never a false granted
  state.
- **EC-3.** Revoking an already absent consent and erasing already-erased
  learning data are idempotent success states.
- **ERR-1.** Missing, stale, oversized, or invalid Telegram init data returns an
  authentication error. Inactive/erased learners are denied.
- **ERR-2.** Unknown actions, non-JSON bodies, extra fields, and malformed
  confirmation values are rejected without changing data.
- **ERR-3.** Temporary server/network failures keep the detail view open,
  re-enable controls, and show one localized retry message.

## Constraints and out of scope

- Preserve the existing retention policy, database schema, feature flags,
  billing/audit records, Telegram menu, legacy callback handling, and all other
  Settings destinations.
- Do not expose Telegram identifiers, messages, raw logs, prompts, payment
  records, consent document versions, secrets, or internal exception details.
- No AI call, payment, invoice, dependency, remote image, or policy/schema
  migration is part of this feature.

## Verification map

- `tests/test_miniapp_help_privacy_v1.py`: AC-1 through AC-8, EC-1 through
  EC-3, ERR-1 through ERR-3.
- Existing Mini App, bot handler, privacy, localization, and full unit suites:
  regression coverage.
- JavaScript syntax, Python compilation, `git diff --check`, and a responsive
  rendered review: delivery gates.
