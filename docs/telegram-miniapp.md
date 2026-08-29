# Telegram Mini App

The MY DICTIONARY Mini App is an optional, read-only companion to the Telegram
bot. It borrows the compact five-tab navigation pattern from the supplied
product reference while keeping MY DICTIONARY branding, vocabulary data,
economics, privacy rules, and existing bot actions.

## Learner surface

- **Profile**: level, XP, streaks, sessions, accuracy, today's XP, daily goal,
  tracked and learned words, and available AI credits.
- **My words**: at most 60 tracked words from the active pack, with curated
  meaning, review/learned state, and correct/incorrect attempt counts.
- **AI credits**: durable available/reserved/spent balances, the one-credit
  contract, and active one-time Stars packs. Checkout buttons stay disabled
  while public Stars checkout is off.
- **Languages**: visible catalog packs, localized names, direction, word count,
  and the current language.
- **Settings**: localized daily goal, meaning language, learning goal, Mirror
  response mode/style/depth/level, plus AI and Voice availability.

All changes continue in the bot through allowlisted `/start miniapp_*` deep
links. Opening or refreshing the Mini App does not update learner timestamps,
create progress or wallet rows, reserve credits, call an AI provider, create an
invoice, or modify settings.

## Security and privacy

- The bootstrap accepts Telegram `initData` only in the
  `X-Telegram-Init-Data` header and verifies Telegram's HMAC, duplicate fields,
  timestamp bounds, and signed user identity.
- Only an existing learner whose access and privacy states are both active can
  receive data. Pending, blocked, erased, missing, invalid, expired, and future
  identities fail closed with fixed errors.
- Responses are `no-store`, identity-free beyond the signed learner's bounded
  display name, and exclude Telegram IDs, usernames, messages, prompts,
  answers, credentials, charge IDs, database URLs, pack IDs, and vocabulary
  identifiers.
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
`/miniapp/api/bootstrap` to the admin service. The public URL is exact: HTTPS,
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

## Rollback

Set `MINIAPP_ENABLED=false` in bot and admin together and restart both services.
The shell and assets then return 404, `/app` is removed from command menus, and
the bot resets Telegram's persistent Web App menu button to the default. No
database rollback or learner-data change is required.
