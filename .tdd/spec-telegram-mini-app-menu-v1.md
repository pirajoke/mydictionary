# Telegram Mini App menu v1 — locked specification

Status: locked on 2026-08-29

## Product intent

Create a Telegram Mini App menu for MY DICTIONARY inspired by the navigation
clarity of the supplied ChattyEnglishBot screenshots, without copying its
branding, avatars, lottery, reward claims, or unsupported product behavior.
The result must use MY DICTIONARY's real learner data, language catalog, AI
credit wallet, and existing Telegram Stars rollout state.

Visual direction: a dark, Telegram-native "living dictionary" with MY
DICTIONARY's ink-green identity, warm paper surfaces, amber AI-credit accents,
compact typography, restrained motion, and the existing brand mark. It must be
mobile-first, keyboard-accessible, responsive, and respect reduced motion.

## Acceptance criteria

### AC-1 — Secure Telegram entry

- When explicitly enabled, `/miniapp` serves a no-store HTML shell and static
  assets with a route-specific CSP that permits the official Telegram Web App
  SDK while keeping admin pages `frame-ancestors 'none'`.
- `/miniapp/api/bootstrap` accepts Telegram `initData` only in a bounded request
  header, verifies Telegram's HMAC, rejects duplicate fields, validates a
  recent bounded `auth_date`, and derives the learner ID only from the signed
  `user` object.
- Missing, malformed, expired, future, tampered, erased, unknown, pending, or
  blocked learners fail closed without creating a user or returning learner
  data.
- The bot token is loaded only through the existing protected token-file
  mechanism; it is never rendered, logged, persisted in the browser, or placed
  in a URL/query string.

### AC-2 — Profile and progress

- The default tab shows the signed learner's display name, current language,
  level, XP, streak/best streak, sessions, accuracy numerator/denominator,
  today's XP, daily word goal, tracked-word count, learned-word count, and AI
  credit balance.
- Metrics come from the existing PostgreSQL learner tables. Missing optional
  progress produces honest zero/empty states rather than fabricated history.
- The interface provides Telegram deep-link actions for continuing a lesson,
  opening the AI Tutor, and sharing the bot. It never includes a learner ID in
  a callback, URL, DOM data attribute, or log.

### AC-3 — My Words

- The Words tab shows at most 60 tracked words for the active language, with
  target text, curated meaning when available, correct/wrong attempts, learned
  state, and due-review state.
- Words are derived from `word_progress` and the checked-in content catalog;
  they are not invented and do not expose pack IDs or vocabulary hashes.
- A learner with no tracked words receives a concise MY DICTIONARY empty state
  and a lesson deep link.

### AC-4 — AI credits and Stars

- The Credits tab shows available/reserved/spent credits and states the current
  contract: one successful Tutor answer costs one AI credit; failed provider or
  validation attempts do not consume a credit.
- It lists only active, one-time billing products in display order and shows
  localized product title, credits, and XTR price.
- When public Stars checkout is disabled, purchase controls are visibly
  disabled and no checkout/order/invoice mutation is attempted. When enabled,
  controls only deep-link to the existing `/buy` Telegram flow; the Mini App
  does not implement a second payment path.
- No lottery, ticket exchange, daily reward, subscription, referral reward, or
  unlimited-use claim is introduced.

### AC-5 — Languages and settings

- The Languages tab lists only published packs visible to the learner's role,
  grouped to one choice per supported target language, with real flags, labels,
  direction, word count, and the current language marked.
- The Settings tab summarizes the real daily goal, meaning language, learning
  goal, Mirror response mode/style/depth/level, and feature availability for
  AI and Voice.
- Language/settings/privacy actions return to the existing Telegram bot flows;
  v1 performs no new profile mutation endpoint.

### AC-6 — Telegram integration

- When enabled with an HTTPS URL, the bot exposes `/app`, includes it in the
  localized command list, replies with a `WebAppInfo` button in private chat,
  and synchronizes a `MenuButtonWebApp` without blocking polling startup.
- The Mini App defines safe deep-link actions for `learn`, `ai`, `buy`, `lang`,
  `settings`, and `privacy`; `/start miniapp_<action>` routes to the existing
  handlers without duplicating learning, consent, or payment logic.
- Group chats do not receive an inline Web App launcher; no user/chat ID is
  embedded in the configured public URL.

### AC-7 — Internationalization and frontend quality

- All learner-visible Mini App copy is complete for `en`, `fr`, `de`, `ja`,
  `ar`, `zh`, `ru`, and `es`; unsupported interface locales fall back to
  English. RTL is applied for Arabic.
- Bottom navigation has exactly five tabs: Profile, Words, Credits, Languages,
  Settings. It uses semantic controls, visible focus, 44px touch targets,
  safe-area insets, loading/empty/error/disabled states, and mobile layouts
  from 320px upward plus a bounded desktop presentation.
- Motion is limited to useful tab/loading feedback and is disabled under
  `prefers-reduced-motion`.

## Edge cases

### EC-1 — Data bounds and privacy

- Bootstrap JSON has a fixed allowlist and bounded arrays/strings. It contains
  no Telegram ID, username, raw initData, credentials, message history,
  prompts, answers, charge identifiers, database URLs, pack IDs, or vocabulary
  hashes.
- API and shell responses are `no-store`; errors are fixed and privacy-safe.

### EC-2 — Runtime compatibility

- Admin authentication, CSRF, reset/OAuth routes, health checks, deterministic
  learning, AI/Voice fail-closed gates, and the existing Stars payment path
  retain their behavior.
- Disabled Mini App configuration returns 404 and does not require a bot token.
- The admin launcher forwards only the Mini App flags, HTTPS URL, safe bot
  username, auth age, and token-file path. Enabled invalid configuration stops
  startup before serving traffic.

## Error contracts

### ERR-1 — Authentication/configuration failure

- Authentication failures return one generic 401 JSON body; denied learner
  state returns a generic 403. No branch reveals whether an ID exists.
- Enabled configuration rejects HTTP URLs, URL query/fragment/userinfo, unsafe
  bot usernames, direct+file token conflict, unsafe token files, and auth ages
  outside 60–900 seconds.

### ERR-2 — Storage/catalog failure

- A bootstrap storage or catalog failure returns a fixed 503 response with no
  raw exception and no partial learner data.
- The HTML shell still renders an accessible retry state in JavaScript.

## Out of scope

- Public Stars activation, canary activation, new purchases/refunds, lotteries,
  subscriptions, referral rewards, gifts, voice synthesis controls, new learner
  mutations, Telegram credentials, and unrelated admin redesign.
- Copying ChattyEnglishBot source, proprietary assets, avatar, wording, or brand.
