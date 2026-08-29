# Mini App Profile Calendar v1 — locked behavior

## Goal

Make the MY DICTIONARY Mini App profile feel like a polished Telegram-native
learning profile: personal, immediately understandable, and motivating without
copying another product's assets, rewards, lottery, or subscription mechanics.

## Acceptance criteria

- **AC-1 — Personal profile hero.** After authenticated bootstrap the Profile
  tab shows the signed Telegram display name, a safe signed Telegram photo when
  available, an initials fallback otherwise, the current language, and the AI
  credit balance. The photo is never persisted and an unsafe URL is discarded.
- **AC-2 — Real streak calendar.** The Profile tab shows the current streak,
  best streak, and a localized month calendar. Activity days come from existing
  read-only learner analytics plus the canonical last activity date. The
  calendar supports previous/next month navigation within the returned window,
  distinguishes activity and today, and exposes accessible labels.
- **AC-3 — Clear MY DICTIONARY actions.** Continue lesson is the primary profile
  action; Share profile is secondary. AI Tutor remains reachable from the AI
  credits tab. Existing deep links remain unchanged.
- **AC-4 — Expressive bottom navigation.** All five existing tabs remain.
  Each has a distinct circular icon treatment, a clear active state, 44 px
  minimum targets, roving tabindex, RTL-aware arrow navigation, and long-label
  behavior at 320 px.
- **AC-5 — Localized production copy.** New streak/calendar/profile copy is
  present and bound for en, fr, de, ja, ar, zh, ru, and es. Month and weekday
  names use the active locale rather than hard-coded English.
- **AC-6 — Responsive, themed, and calm.** The profile works from 320 px through
  Telegram desktop, uses Telegram theme variables with readable fallbacks,
  respects safe areas and reduced motion, and never gates content visibility on
  animation.

## Edge and failure contracts

- **EC-1 — Privacy/read-only bounds.** Bootstrap remains read-only. Activity
  dates are unique ISO dates, bounded to the latest 370 days, and contain no
  event names, session IDs, Telegram IDs, usernames, messages, or prompts.
- **EC-2 — Honest empty states.** With no photo or activity history, initials
  and an empty but usable current-month calendar render without invented days.
- **ERR-1 — Unsafe avatar.** Non-HTTPS, credential-bearing, oversized, or
  non-Telegram photo URLs are omitted without failing authentication/bootstrap.
- **ERR-2 — Calendar resilience.** Invalid activity dates are ignored and month
  controls cannot move outside the bounded history window.

## Explicitly out of scope

- No rewards, lottery, tickets, daily-star economy, unlimited subscription, or
  copied character/logo/photo assets from the reference product.
- No image upload, social graph, referral backend, schema migration, new table,
  payment change, AI metering change, public Stars checkout, or feature-flag
  change.
