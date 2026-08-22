# Locked bug specification: Telegram user-surface locale integrity

Date: 2026-08-22

## Reproduction and active path

`manual_polling()` registers the command and callback handlers below. The auth
wrapper resolves and persists `interface_locale`, but several active handlers
still render direct Russian literals. A French learner therefore leaves the
localized `/start` and block flow when opening privacy, AI, Voice, billing or a
legacy exercise.

The already localized onboarding, home, topics, settings, stats and active
learning-block paths are neighboring behavior and must remain unchanged.

## Acceptance criteria

- **AC-1 Command menu:** command descriptions exist for all eight interface
  locales; Telegram profile sync installs a default menu plus locale-scoped
  menus. A French menu contains no Russian chrome.
- **AC-2 Help and privacy:** `/help`, `/privacy` and every privacy callback use
  the resolved interface locale. Operation references and configured legal
  notices are content, not chrome.
- **AC-3 AI and Mirror:** entry, disabled/error/status/consent, feedback and
  response-format chrome use the resolved interface locale.
- **AC-4 Voice:** entry, consent, mode, prompt, feedback, translation and stop
  chrome use the resolved interface locale. Target words, user-selected meaning
  text, transcripts and configured processing notices remain content.
- **AC-5 Stars:** disabled, terms, catalog, support, subscription and callback
  chrome use the resolved interface locale. Seller data and the versioned terms
  document remain configured content.
- **AC-6 Legacy exercises:** `/lang`, `/quiz`, `/type`, `/flash` and `/smart`
  prompts, results and buttons use the resolved interface locale. Vocabulary
  targets, meanings and examples remain learning content.
- **AC-7 Notification:** the pilot-access notification is rendered in the
  learner's persisted interface locale without exposing an identifier.
- **EC-1 Fallback:** unknown/empty locale falls back to English; explicit
  Russian remains Russian.
- **EC-2 Completeness:** every new message key exists for all eight supported
  locales and catalog-completeness tests remain green.

## Constraints

- Modify only Telegram learner UI code and the deterministic locale catalog.
- No provider call, payment, message delivery, credential, feature flag,
  database schema or admin-console behavior changes.
- Do not translate or alter vocabulary meaning content, configured seller data,
  configured legal notices, transcripts or operation references.
- No new dependency and no runtime machine translation.
