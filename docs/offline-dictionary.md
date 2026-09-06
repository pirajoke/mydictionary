# Lexi browser dictionary

The adult Telegram learning flow now has a persistent **Dictionary** action.
The Mini App's Dictionary tab retains tracked learning words and provides
browser lookup/download actions. The separate public `/dictionary/` needs no
Telegram account and does not read learner storage.

## Capabilities and boundaries

- 700 entries from seven explicitly redistribution-approved public, free,
  published schema-v2 starter packs: English, French, German, Arabic, Chinese,
  Russian and Spanish. These represent 100 aligned vocabulary concepts, not
  700 distinct words in each language. Private/admin packs and the legacy
  Japanese/Vietnamese packs are not exported.
- Target/translation language selectors, pair swapping, Unicode-normalized
  bidirectional search, accepted Russian meanings and transcription.
- Saved words and short written recall with corrections. Saved entries have a
  simple local next-review timestamp; this is independent of Telegram SRS/XP.
- UI languages: Russian, English and French. Other requested interface locales
  fall back to English; vocabulary-language coverage is independent of UI.
- Queries stay in the browser. The **Translate in Yandex** link sends the
  current query only on click and is labelled as an external online service.
  This is not a proprietary general-purpose translation engine.
- CSV export contains saved entries from the selected language pair and escapes
  spreadsheet formula prefixes. It is explicitly initiated by the user.

## Offline use

**Save on this device** registers a worker scoped to `/dictionary/` and caches
only the public dictionary shell, dictionary CSS/JS and manifest. After saving,
the page can reopen offline in a supported browser/home-screen installation.
The Mini App, admin pages, authentication, API responses and user identity are
never cached by this worker. HTTP responses retain `no-store`; explicit browser
Cache API writes apply only to the four public allowlisted resources.

The worker revision hashes dictionary content, template, CSS, JS, worker source,
manifest and CSP. New revisions install a complete new cache and remove only
previous dictionary caches. Removing offline packs leaves saved words intact.
Browsers may evict local storage. A Telegram WebView cold start offline is not
promised: use Safari/Chrome or the home-screen browser app.

**Download dictionary** returns a standalone HTML attachment containing the
public packs, CSS and JS. It preserves validated language choices but contains
no learner/account data or saved favourites from another browser. Exact script
and stylesheet hashes authorize embedded assets via CSP. Interactive file
previews on phones vary; open in a browser. Saved vocabulary lives in that
browser/file context, so CSV export is available separately.

No offline AI conversation, general-text neural translation, guaranteed offline
audio, cloud synchronization or complete child curriculum is claimed.

## Learning companion recovery

Deep Mirror responses allow up to 1000 output tokens (including reasoning),
within the configured limit and the existing monetary preflight. This replaces
the 480-token cap associated with an incomplete production response. Incomplete
responses still fail without learner debit. Retry is explicit, consumes the
existing pending question once, and repeats normal consent, quota and rate gates.
Recovery offers Review and Dictionary as useful independent actions.

Exact reviewed requests such as “план на сегодня” receive a short authored
routine without a provider call or AI credit. Existing reminders remain
user-configured; this release does not enroll new notification recipients.

## Verification

Backend: `python -m unittest tests.test_offline_dictionary`.
Browser: start an isolated `OfflineDictionaryTest` app, then run
`node tests/browser/dictionary.cjs` with Playwright resolvable and optionally
`DICTIONARY_TEST_URL=http://127.0.0.1:<port>`.

`node tests/browser/dictionary-upgrade.cjs` starts its own isolated fixture and
verifies a v1-to-v2 worker upgrade, coherent new shell/JS/CSS/content, cleanup of
only old dictionary caches, and a cold offline lookup on the new version.

Browser checks cover 42 non-identical language pairs, reverse and Unicode
lookup, persisted saved entries, written feedback, no external query requests,
mobile overflow, offline save/remove/resave, a new tab while network is blocked,
standalone HTML with no network, and malformed local storage. Physical iOS and
Android file-preview/home-screen behavior still needs pilot device validation.

## Rollback

No schema migration. Server rollback uses the normal OVH image procedure;
worker revision changes with rolled-back assets too. Existing offline caches
can continue serving their saved release until online reconnection/update.
The user can remove only offline packs using the page control without deleting
saved vocabulary.
