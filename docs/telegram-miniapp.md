# Telegram Mini App

The MY DICTIONARY Mini App is an optional companion to the Telegram
bot. It borrows the compact five-tab navigation pattern from the supplied
product reference while keeping MY DICTIONARY branding, vocabulary data,
economics, privacy rules, and existing bot actions.

## Learner surface

- **Profile**: level, XP, streaks, sessions, accuracy, today's XP, daily goal,
  tracked and learned words, and available AI credits.
- **Dictionary**: curated swipe practice (smart mix, forgotten/due, new words),
  plus browser dictionary/search and standalone download actions,
  followed by at most 60 tracked words from the active Telegram pack, with
  curated meaning, review/learned state and correct/incorrect attempt counts.
- **AI credits**: durable available/reserved/spent balances, the one-credit
  contract, and active one-time Stars packs. Checkout buttons stay disabled
  while public Stars checkout is off.
- **Languages**: visible catalog packs, localized names, direction, word count,
  and the current language.
- **Settings**: localized daily goal, meaning language, learning goal, Mirror
  response mode/style/depth/level, plus AI and Voice availability.

Bot-only changes continue through allowlisted `/start miniapp_*` deep links.
Language/interface changes and privacy actions use signed, protected APIs.
Opening or refreshing the Mini App does not update learner timestamps,
create progress or wallet rows, reserve credits, call an AI provider, create an
invoice, or modify settings.

## Swipe practice

Press **Start swiping** in Dictionary. The existing five-item navigation stays
unchanged. The language shortcut opens the existing Languages tab.
Smart mix prefers seven due/mistaken words and three new words, filling
shortages without unrelated learned fillers. Decks have at most ten curated
cards from the current compatible pack, translated into the learner's meaning
language. Custom vocabulary keeps its separate practice flow.

Left/**Again** applies the bot's incorrect-answer SRS and puts the card after
two others once. Right/**Know** applies the correct-answer SRS. Buttons and
keyboard arrows are equivalent; Space/Enter flips a focused card. Device
pronunciation is optional and does not require paid Voice or an AI provider.
IPA stays standard notation in a readable, regular-weight font.

Each answer is saved transactionally before the card advances. A lost response
is replayed with the same operation ID, never charged twice in XP. Latest-answer
undo restores SRS and answer XP within ten minutes, retaining the day's practice
streak. Newer changes from another session/Telegram prevent destructive undo.
Completion adds the canonical 25 session XP once and refreshes profile metrics.

Four strict signed POST routes live under `/miniapp/api/swipe/`: `deck`, `rate`,
`undo`, `complete`. Queue ownership, active pack and selected content identities
are server-authoritative. Expired/changed content sessions fail closed. The
additive `0023_miniapp_swipe_sessions` migration stores bounded short-lived
state/receipts, without terms or messages; cleanup and learner erasure remove it.
Only pressing Start creates a session; bootstrap/tab navigation remains read-only.

Public dictionary actions open `/dictionary/` or `/dictionary/download` with only
target/native/interface language choices. They send no signed initData or
learner identity to that public page. Its independently saved words/practice
remain local; see [offline dictionary](offline-dictionary.md).

## Security and privacy

- The bootstrap accepts Telegram `initData` only in the
  `X-Telegram-Init-Data` header and verifies Telegram's HMAC, duplicate fields,
  timestamp bounds, and signed user identity.
- Only an existing learner whose access and privacy states are both active can
  receive data. Pending, blocked, erased, missing, invalid, expired, and future
  identities fail closed with fixed errors.
- Bootstrap responses are `no-store`, identity-free beyond the signed learner's bounded
  display name, and exclude Telegram IDs, usernames, messages, prompts,
  answers, credentials, charge IDs, database URLs, pack IDs, and vocabulary
  identifiers.
- Swipe responses contain only random owned session/operation IDs, public pack
  IDs, card indices, curated vocabulary and aggregate counts; no Telegram IDs or
  private vocabulary progress hashes. Signed initData stays out of URLs/storage.
- The page uses a route-specific CSP, Telegram theme variables with accessible
  fallbacks, safe-area insets, RTL layout, reduced-motion support, and keyboard
  tab navigation.
- The bot token is read only from the existing absolute, owner-only mode-`0600`
  `BOT_TOKEN_FILE`; inline/conflicting token configuration is rejected.

## Configuration

The feature defaults off. Bot and admin must receive the same reviewed values:

```text
MINIAPP_ENABLED=true
MINIAPP_PUBLIC_URL=https://mydictionary.meshly.fr/miniapp
MINIAPP_BOT_USERNAME=<the existing bot username>
MINIAPP_AUTH_MAX_AGE_SECONDS=300
BOT_TOKEN_FILE=<the existing protected token mount>
```

The admin must also receive the existing `AI_INITIAL_CREDITS` value so the
read-only balance matches `/ai`. Never place the token value in environment
output, compose diffs, logs, receipts, or chat.

The Cloudflare tunnel must route `/miniapp`, `/miniapp/static/*`, and
`/miniapp/api/*` to the admin service. The public URL is exact: HTTPS,
no query/fragment/userinfo, and path `/miniapp` without a trailing slash.

## Activation checks

1. Deploy one reviewed SHA to bot and admin while preserving all unrelated
   feature flags and public Stars checkout state.
2. Confirm loopback and public `/health`, schema revision, heartbeat, one
   polling process, backup verification, and unchanged restart counts.
3. Confirm `/miniapp` returns the shell, static assets return 200, and an empty
   bootstrap header returns the fixed 401 response without learner data.
4. In a private owner chat, confirm `/app` and the Telegram menu button open the
   five localized tabs. Verify one LTR and Arabic RTL locale, narrow width,
   light/dark theme, empty words, disabled checkout, and deep links.
5. Confirm opening and switching tabs changes no learner, progress, wallet,
   usage, billing, or audit rows.
6. Verify swipe know/again, undo, network retry, empty modes and signed-access
   failures. Answers must remain visible through the existing Telegram SRS.

## Rollback

Set `MINIAPP_ENABLED=false` in bot and admin together and restart both services.
The shell and assets then return 404, `/app` is removed from command menus, and
the bot resets Telegram's persistent Web App menu button to the default. No
database rollback or learner-data change is required.
After applying the additive swipe migration, do not automatically downgrade the
database or start older code. Disable Mini App or fix forward; restore only from
an exact reviewed backup with an explicit data-loss boundary.
