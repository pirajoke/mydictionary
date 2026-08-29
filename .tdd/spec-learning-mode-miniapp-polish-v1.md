# Learning-mode cleanup and Mini App polish v1

Status: locked on 2026-08-29.

## AC-1 — clean mode transition

When a learner opens individual word/pronunciation cards from the study list,
the bot tracks only its own bounded message identifiers for that chat. Switching
the active block into quiz or written mode deletes those tracked word messages
and the last pronunciation message before rendering the first question.

## AC-2 — fail-open deletion

Telegram deletion failures are privacy-safe and do not prevent the requested
quiz or written attempt from starting. Cleanup is idempotent and clears its
local tracking before awaiting network deletion.

## AC-3 — Telegram menu label

The persistent Telegram WebApp menu button is labelled exactly `Menu`. Command
descriptions and disabled-state rollback remain unchanged.

## AC-4 — Telegram avatar

Authenticated Telegram `photo_url` values may use the documented Telegram CDN
families (`t.me`, `telegram.org`, `telegram-cdn.org`, `cdn-telegram.org`, and
`telesco.pe`, including subdomains). Only bounded HTTPS URLs without embedded
credentials, ports, or fragments are accepted. The frontend may use the same
Telegram client photo as a display-only fallback; it never supplies identity
or authorization. Initials remain the honest fallback when Telegram withholds
the photo under the user's privacy settings.

## AC-5 — compact interface

The Mini App reduces avatar, credit-star, streak, calendar, action, and bottom
navigation scale so the profile fits materially more content on a normal phone
viewport. Interactive targets remain at least 44 CSS pixels and all existing
light/dark, RTL, reduced-motion, contrast, and safe-area contracts remain.

## AC-6 — original section imagery

Words, AI Credits, and Languages use three original, locally served, optimized
MY DICTIONARY raster illustrations. They contain no text, third-party logos,
lottery/reward imagery, or copied competitor assets; they are decorative with
empty alt text and lazy decoding/loading.

## EC-1 — bounded state

Per-chat review-message tracking accepts only positive integer bot message IDs,
deduplicates them, and retains at most 20 identifiers.

## ERR-1 — unavailable media

An unsafe or failed avatar and unavailable decorative image never expose a
secret, learner identifier, or broken authorization state. Core learning and
Mini App data remain usable.

## Out of scope

- No economics, product catalog, credit, payment, Stars, AI, Voice, database,
  retention, or learner-record changes.
- No public Stars or canary activation.
- No copying of Chatty artwork, avatars, promotions, subscriptions, or rewards.
