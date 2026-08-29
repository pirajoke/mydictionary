# AI Tutor economics entry v1

Status: locked on 2026-08-29.

## Outcome

Make `/ai` the single localized entry point for the AI Tutor. It must explain
the credit economy, show the learner's current durable balance, expose the
already-approved Telegram Stars catalog when checkout is available, and let
the learner start a normal contextual Tutor conversation even when no lesson
block is active. The existing Stars terms, signed order, invoice, fulfillment,
refund, pending-question and one-credit metering paths remain authoritative.

## Acceptance criteria

### AC-1 — Free economics screen

- `/ai` without arguments no longer requires an active lesson block.
- It sends one localized screen containing the current available AI-credit
  balance and the exact policy: one successfully generated AI answer costs one
  AI credit; a failed or rejected answer costs zero.
- Opening the screen is read-only: it does not request AI or billing consent,
  call a provider, reserve or spend credits, create an order or invoice, or
  write dialogue memory.
- A missing or malformed balance is shown as unavailable rather than invented.

### AC-2 — Existing Stars catalog, not a second checkout

- When checkout is available to the learner and active one-time products
  exist, the same screen shows each active product as localized title, exact
  credit count and exact XTR price.
- Product callback data remains `buy:<product_id>` and therefore continues
  through the existing versioned terms, signed order, XTR invoice,
  pre-checkout, fulfillment, refund and reconciliation paths.
- Product IDs, credits, prices, order payloads and database catalog rows are
  not changed or copied into a new commercial source of truth.
- Monthly/draft/inactive products are not exposed by this screen.

### AC-3 — Contextual Tutor chat without a lesson block

- The screen always offers one localized `Ask Tutor` action. Without an active
  block it starts a ten-minute one-question pending state whose next text is
  routed once through the ordinary Mirror/Tutor chat path, preserving bounded
  dialogue memory, product profile, progress and interface locale.
- `/ai <question>` also uses the ordinary contextual Mirror/Tutor path when no
  active block exists. It keeps the existing compact grounded companion path
  when a valid active block exists.
- If current AI-processing consent is missing, the first general Tutor
  question presents the existing versioned consent and a valid acceptance
  resumes that exact question once through the ordinary contextual path; it
  must not dead-end by sending the learner back to `/ai`.
- Exercise-answer routing keeps priority. Expired, malformed or consumed
  pending states never call the provider or spend a credit.

### AC-4 — Lesson actions remain grounded

- With a valid active lesson, the existing vocabulary, mistake, progress and
  ask actions remain available and session-bound.
- Without a valid active lesson, the three lesson-specific analyses are not
  shown; a localized `Start a lesson` action routes to the existing topic
  picker without creating a new learning path.

### AC-5 — Fail-closed commercial visibility

- When public checkout is disabled, the learner is not eligible, the catalog
  read fails, or no active product exists, no product callback is shown and no
  invoice path is opened. Successfully read active one-time packages may still
  be listed as read-only economics together with an explicit localized
  purchase-unavailable notice. The balance, economy explanation, Tutor chat
  and deterministic learning remain available.
- Direct or stale callbacks continue to be validated by the existing billing
  handlers; this feature does not weaken their authorization or consent gates.

### AC-6 — Localization, privacy and Telegram limits

- New screen, balance-unavailable, lesson-start and general-chat copy exists
  for `en`, `fr`, `de`, `ja`, `ar`, `zh`, `ru`, and `es`.
- Learner-facing chrome follows the interface locale. Product identity,
  learner questions, dictionary content and examples are not translated or
  logged by this entry screen.
- Callback data is at most 64 bytes and contains no learner identifier.
- The screen and analytics contain no provider token counts, costs, Telegram
  identifiers, payment identifiers, credentials, questions or answers.

## Edge and error cases

- AI disabled keeps the existing localized disabled response and exposes no
  catalog.
- Storage failure while reading the balance or catalog cannot create an order,
  invoice, credit mutation or provider call.
- Repeated `Ask Tutor` presses replace the pending state instead of stacking
  requests.
- Empty text never reaches the provider.

## Explicitly unchanged

- Approved catalog prices and credit quantities, terms version, seller data,
  payment/refund semantics, initial credit grant, global AI budgets, one-credit
  settlement, Voice economics and deterministic lesson access.
- No migration, dependency or new payment provider is required.

## Verification

- Behavioral RED/GREEN tests for no-block and active-block `/ai`, balance,
  product buttons, disabled/failing catalog, general pending chat, `/ai
  <question>`, all eight locales, callback registration and mutation-free
  opening.
- Existing Tutor menu, Mirror continuity, billing, Stars handler, localization,
  economics and privacy suites.
- Full unit suite, `compileall`, `git diff --check`, secret/private-data scan and
  an independent payment-path review.
