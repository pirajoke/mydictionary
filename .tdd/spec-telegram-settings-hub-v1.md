# Telegram Settings Hub v1

## Goal

Replace the single oversized Telegram settings keyboard with a compact command
hub and progressively disclosed Study and AI Tutor sections. Detailed product
information remains available in the existing private Telegram Mini App.

## Acceptance criteria

- AC-1: The settings home shows the familiar commands `/learn`, `/ai`, `/stats`,
  `/lang`, `/app`, and `/privacy`, without exposing language, pace, style,
  depth, or level option callbacks on the home screen.
- AC-2: In a private chat with Mini App enabled, the first home action opens
  MY DICTIONARY in a separate Web App window. Group chats and disabled Mini App
  state never expose a Web App button.
- AC-3: The Study section contains only visible language packs, lesson sizes
  5/10/20, and a Back action. Languages are arranged no more than two per row.
- AC-4: The AI Tutor section contains only enabled response styles, compact /
  balanced / deep depth, adaptive and A1-C1 levels, and a Back action. Options
  are grouped into compact rows.
- AC-5: Saving lesson size keeps the Study section open; saving style, depth,
  or level keeps the AI Tutor section open.
- AC-6: Home, Study, AI Tutor, Back, and section summaries are localized in all
  eight supported interface locales.

## Edge and error criteria

- EC-1: Every callback remains at most 64 bytes and contains no learner or chat
  identifier.
- ERR-1: Unknown sections or malformed callbacks fail closed with the existing
  localized stale/unavailable response and do not mutate settings.

## Constraints

- Existing settings values and persistence APIs remain unchanged.
- No new command, dependency, database migration, payment behavior, AI metering,
  provider request, or public Stars activation.
- The Mini App remains private-chat only and disabled state remains fail closed.
