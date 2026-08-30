# Mini App Profile Game v1

## Goal

Replace the Profile tab's flat eleven-card metric wall with a compact,
game-like learning summary that prioritizes the next useful action.

## Acceptance criteria

### AC-1 — One game progress surface

- Profile renders one level/XP game surface using the existing durable
  `progress.level` and `progress.xp` values.
- Level and XP remain text-accessible and are not encoded by color alone.
- The surface uses existing Telegram theme tokens and contains no invented
  progress-to-next-level value.

### AC-2 — Three visible achievements

- The visible achievement strip contains exactly three real outcomes:
  current streak, answer accuracy, and learned words.
- Values come from the existing bootstrap payload and remain correct for zero
  attempts and zero learned words.
- The strip is compact at 320px, RTL-safe, and does not horizontally overflow.

### AC-3 — Daily quest

- Profile presents one daily quest using the real configured daily word goal
  and real today's XP.
- The quest reuses the existing `learn` action and localized Continue lesson
  copy; it must not add a new endpoint or storage mutation.
- The UI does not claim that today's XP and the word goal are the same unit.

### AC-4 — Fewer visible indicators

- The previous eleven-tile metric wall is removed.
- Detailed statistics are collapsed by default and contain no more than four
  secondary metrics.
- Level, XP, streak, accuracy, today's XP, daily goal, and credits are not
  duplicated inside the collapsed metric list.

### AC-5 — Existing product behavior is preserved

- Avatar, language, credit chip, calendar, Share, Continue lesson, five tabs,
  product checkout, language switching and Settings behavior retain their
  existing IDs/actions/API targets.
- No backend schema, API, billing, AI, Stars, authentication, or learner-data
  behavior changes.

## Edge constraints

### EC-1 — Accessibility and motion

- Interactive targets remain at least 44px, focus-visible states remain
  visible, and decorative icons are hidden from assistive technology.
- Any new motion is state-driven and disabled under
  `prefers-reduced-motion: reduce`.

### EC-2 — Localization and direction

- New learner-visible text must reuse existing localized copy keys or be added
  for all eight supported interface locales.
- The layout must work in both LTR and RTL without changing chronological
  calendar direction.

### ERR-1 — Empty and zero data

- Zero attempts display `0/0`; zero streak, XP, learned words, and daily goal
  render honestly without hiding the game surface or fabricating progress.

## Out of scope

- Rewards, purchasable items, leaderboards, streak insurance, badges stored in
  the database, XP-economy changes, new analytics events, and new artwork.
