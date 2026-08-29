# Mini App dashboard redesign v1

Locked: 2026-08-30

## Objective

Bring Profile, My words, AI credits, Languages, and Settings into one compact,
trustworthy mobile-dashboard system inspired by the supplied reference while
preserving MY DICTIONARY branding, Telegram theming, and all existing product
behavior.

## Acceptance criteria

- **AC-1 — Shared shell.** All five tabs use the same compact top-bar,
  section, list, metric, button, spacing, radius, and navigation vocabulary.
  The visual system is calm and data-first, not a set of unrelated hero cards.
- **AC-2 — Profile.** Identity, current language, AI balance, primary actions,
  streak/calendar, and detailed metrics remain visible and are reorganized into
  a clear dashboard hierarchy.
- **AC-3 — My words.** Tracked/learned/due summary, word rows, badges, attempt
  counts, and the teaching empty state use the shared dashboard system.
- **AC-4 — AI credits.** Wallet totals, Tutor entry, credit policy, product
  packs, price controls, and checkout-disabled state use the shared dashboard
  system without changing product actions or Stars authorization.
- **AC-5 — Languages.** Current language, compatible pack switches, word
  counts, selected/pending/error/retry states, and Telegram fallback action are
  presented as an accessible settings list.
- **AC-6 — Settings.** Learning, Tutor, and feature groups—including the bot
  language selector—use the shared dashboard rows with clear enabled/disabled,
  focus, pending, error, and retry states.
- **AC-7 — Responsive and accessible.** The UI works from 320px through 720px,
  honors safe areas, Telegram light/dark variables, RTL, keyboard tabs, visible
  focus, reduced motion, 44px targets, and readable contrast. No horizontal
  overflow or clipped localized navigation labels.

## Edge contracts

- **EC-1 — Behavior preservation.** Existing element IDs, tab semantics,
  `data-action` values, API calls, authenticated mutations, calendar logic,
  localized copy, avatar behavior, and billing/language-switch flows stay
  unchanged.
- **EC-2 — Theme resilience.** The no-Telegram fallback and Telegram light/dark
  themes remain readable; inactive elements never rely on color alone.
- **EC-3 — Density.** Primary tab content fits a typical Telegram viewport
  without oversized decorative sections; information remains scannable rather
  than being hidden.

## Error contracts

- **ERR-1 — Loading and failure.** Loading, global failure/retry, empty words,
  checkout unavailable, language-switch failure, and interface-locale failure
  use the same accessible state vocabulary as the normal dashboard.
- **ERR-2 — No design-only behavior changes.** The redesign does not add
  providers, dependencies, database writes, products, payments, user data, or
  new network requests.

## Out of scope

- New product features or analytics.
- New AI-generated assets or third-party branding.
- Changes to Mini App authentication, Stars economics, storage, migrations, or
  Telegram bot business logic.
