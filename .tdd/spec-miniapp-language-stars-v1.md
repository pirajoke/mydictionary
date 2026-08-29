# Mini App language switch + AI Stars v1

Status: locked
Owner request: 2026-08-30
Target: Telegram Mini App and production OVH runtime

## Normal behavior

- AC-1: The Languages tab renders one familiar switch control for every visible,
  compatible dictionary. Exactly one switch is selected. The selected switch is
  disabled/idempotent, exposes an accessible checked state, and preserves the
  pack label, word count, text direction, and localized current label.
- AC-2: Activating another switch sends an authenticated, no-store Mini App
  request for that exact public pack. A successful response durably changes only
  the current learner's active pack/language, invalidates stale lesson state on
  the next bot interaction, and returns a fresh privacy-safe bootstrap payload so
  the UI updates without leaving the Mini App.
- AC-3: The Credits tab keeps checkout disabled while Stars is off. When Stars is
  on, every active one-time product card is enabled and opens the exact selected
  product through a bounded Telegram deep link; it never substitutes the owner
  canary price or exposes learner/chat identifiers.
- AC-4: The selected product deep link reuses the existing terms, order, invoice,
  pre-checkout, fulfillment, refund, idempotency, and reconciliation contracts.
  Accepted current terms produce one invoice for the selected active product;
  missing terms show the current terms first and resume that same product once
  after acceptance.
- AC-5: Public production activation sets `TELEGRAM_STARS_ENABLED=true` for bot
  and admin together, keeps `STARS_PRODUCTION_CANARY_ENABLED=false`, preserves
  AI/Voice/Mini App flags, and exposes checkout only after restart and fresh
  readiness verification.

## Edge conditions

- EC-1: Pack IDs and product IDs are ASCII allowlisted, bounded to Telegram/API
  limits, contain no identity, and must resolve to a currently visible/compatible
  pack or active one-time product.
- EC-2: Switching to the already-current pack is mutation-free. Two rapid switch
  taps cannot corrupt progress; the last successfully committed response is the
  visible selected state.
- EC-3: RTL labels, 320px layouts, keyboard focus, reduced motion, disabled,
  pending, success, and error states remain readable and use the existing Mini
  App design vocabulary.

## Failure behavior

- ERR-1: Missing/invalid/expired Telegram init data, erased/inactive learner,
  malformed JSON, unknown/incompatible pack, or oversized identifier fails
  closed with fixed privacy-safe 4xx responses and no learner mutation.
- ERR-2: Database/bootstrap failure returns one fixed privacy-safe 503 response;
  the UI restores the prior selected switch and offers a localized retry state.
- ERR-3: Disabled Stars, stale terms/economics, inactive/draft/subscription
  product, missing payload secret, catalog mismatch, backup/readiness failure, or
  canary/public conflict prevents public activation and invoice creation.

## Constraints

- Deterministic learning remains available with AI/Voice/Stars off.
- No new dependency or migration.
- No raw secrets, learner identifiers, payment identifiers, prompts, or logs in
  tests, UI payloads, receipts, commits, or deployment output.
- Public packages remain 20/50/150 AI credits at 69/129/319 XTR; the owner-only
  10-XTR canary is not reused or exposed.
- Production rollout requires a verified PostgreSQL backup and fresh privacy-safe
  release/schema/health/heartbeat/flags/catalog/readiness evidence.

## Out of scope

- Subscriptions (`ai-monthly`) remain draft and are not displayed or activated.
- No test or production purchase is made on behalf of a learner during rollout.
- No changes to AI credit pricing, credit consumption, refund policy, or public
  learner access mode.
