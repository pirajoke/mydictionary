# Mini App interface language v1

## Goal

Let an authenticated learner change the language used by MY DICTIONARY itself
from the Mini App Settings tab. The selected interface language must be durable,
must immediately re-localize the Mini App, and must be used by subsequent
Telegram bot replies.

The interface-language preference is independent from the Telegram client
language, the active vocabulary pack, and the language used for definitions.

## Supported locales

The only accepted canonical values are:

`en`, `fr`, `de`, `ja`, `ar`, `zh`, `ru`, `es`.

## Acceptance criteria

### AC-1 — Settings control

- The Learning section of the Mini App Settings tab contains a learner-visible
  localized `Bot language` row.
- The row uses an accessible native selection control with exactly the eight
  supported locales and localized/native language names.
- The durable current interface locale is selected. If no preference exists,
  the signed Telegram locale is used as the fallback.
- The control is keyboard accessible, has a visible focus state, and remains
  usable in RTL layout.

### AC-2 — Authenticated durable change

- Selecting a locale sends an authenticated `POST
  /miniapp/api/interface-locale` request with the exact JSON body
  `{\"locale\": \"<canonical>\"}`.
- The request uses verified Telegram Mini App init data, the active-learner
  privacy gate, no-store responses, and a persistent per-user mutation rate
  limit.
- A successful request persists only the current learner's interface locale
  and returns a fresh, privacy-safe bootstrap already localized in that locale.
- The Mini App immediately re-renders using the returned bootstrap, including
  document `lang` and Arabic RTL direction.
- Re-selecting the current locale is idempotent.

### AC-3 — Telegram bot continuity

- On the learner's next Telegram update, all existing bot surfaces use the
  persisted interface locale before falling back to Telegram
  `language_code`.
- The preference survives process restart and a new per-update learner runtime.
- The change does not mutate the Telegram profile, active pack, definition
  language, learning goal, AI wallet, Stars products, consent, or usage data.

### AC-4 — Safe storage and lifecycle

- A dedicated nullable database field stores the interface-locale override;
  Telegram's observed `users.language_code` remains unchanged and may continue
  to refresh from Telegram updates.
- Migration `0018_interface_locale` upgrades and downgrades cleanly from
  `0017_admin_auth_recovery`.
- Privacy erasure clears the interface-locale override.
- Read-only Mini App bootstrap does not update timestamps or create rows.

### AC-5 — Localization completeness

- Every learner-visible label, language option, pending state, success state,
  error state, and retry action added by this feature exists in all eight
  interface locales.
- The existing meaning-language row continues to describe the language of
  definitions and is never reused as the bot-interface setting.

## Edge cases

### EC-1 — Exact input

- Missing, extra, duplicate, malformed, non-string, mixed-case, or unsupported
  locale input is rejected fail closed with a fixed privacy-safe response.
- No Telegram/user/chat identifier appears in HTML, JSON action values, logs,
  callbacks, or rendered error text.

### EC-2 — UI sequencing

- While a change is pending, the language selector is disabled and exposes a
  localized busy state.
- Changes are serialized. A stale response cannot overwrite a newer selection.
- On failure, the UI reloads authoritative bootstrap state before offering a
  localized retry, so visible and durable state cannot diverge.

## Error contracts

### ERR-1 — Authentication and access

- Missing, invalid, expired, or conflicting Telegram init data returns 401.
- Denied, erased, or missing learners return 403.
- Invalid JSON/body/locale returns 400.
- Rate limiting returns 429 with a positive `Retry-After`.

### ERR-2 — Persistence failure

- Storage or post-write bootstrap failure returns a fixed no-store 503 without
  exposing identifiers, raw exceptions, or partial bootstrap data.
- A failed write cannot corrupt another learner or an unrelated profile field.
- No AI provider, usage meter, billing order, invoice, pack activation, or
  Telegram outbound message is triggered by this endpoint.

## Out of scope

- Changing the active vocabulary pack or definition language.
- Enabling public Telegram Stars or production canary.
- Adding new locales beyond the existing eight.
- Changing Telegram client language.

