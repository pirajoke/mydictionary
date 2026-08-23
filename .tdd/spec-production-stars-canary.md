# Production Stars owner canary

## Outcome

Prove one real Telegram Stars purchase and immediate refund on the owner's
production account without exposing checkout to any other learner or treating
the result as the canonical Telegram Test launch receipt.

## Authorization boundary

- One owner-only production canary.
- Maximum and exact canary invoice amount: 10 XTR.
- Exact product: `ai-mini`, 20 AI credits, one-time purchase only.
- The reviewed public `ai-mini` catalog price remains 69 XTR; the 10 XTR
  amount is a temporary owner-only canary override and never reprices the
  public product.
- Request the refund immediately after durable, idempotent fulfillment.
- Public checkout remains disabled before, during and after the canary.
- No subscription, other product, other payer, public launch, credential
  disclosure, learner message, or canonical launch-gate override is allowed.

## Observable acceptance criteria

1. `TELEGRAM_STARS_ENABLED=false` continues to mean public billing is off.
2. A separate canary configuration fails closed unless it is explicitly
   enabled with exactly one positive owner Telegram ID, product `ai-mini`, and
   canary amount `10` XTR.
3. Only the configured owner can open billing terms/products, accept current
   terms, select `ai-mini`, receive an invoice, pass pre-checkout and reach
   fulfillment while canary mode is active.
4. Every non-owner is rejected before order creation or invoice delivery; a
   forged/mismatched pre-checkout is rejected. A successful-payment update for
   a valid order that was issued before canary activation must still be routed
   through the ordinary idempotent fulfillment path, because a payer must
   never be charged without fulfillment after a feature flag changes. Normal
   cards, AI and Voice behavior outside billing are unchanged.
5. The canary catalog exposes only the one-time `ai-mini` product and creates
   an owner-only invoice at exactly 10 XTR for 20 credits. The underlying
   reviewed `ai-mini` product remains active at 69 XTR; subscription metadata,
   a repriced public product or any other catalog mutation is rejected.
6. A successful payment grants credits exactly once. Duplicate Telegram
   delivery cannot grant additional credits or enqueue a second refund. Two
   concurrent owner taps cannot create two payable canary orders or invoices;
   the single-canary claim is enforced by a durable unique database marker, not
   by an unlocked read-before-write check.
   Every marker consumer also validates the fixed canary actor/provenance; a
   generic or tampered `app_settings` row cannot reclassify an older purchase.
   The new 10 XTR canary uses a new versioned claim and may coexist with the
   preserved, unpaid 69 XTR v1 order; that historical record is never deleted,
   rewritten, made payable or included in v2 status/evidence.
7. The first durable successful canary payment creates exactly one pending
   refund request. Processing it through the existing Telegram gateway is
   idempotent, deducts/restores the canary credit grant according to existing
   refund accounting, and does not print or persist charge/user IDs in reports.
   An automatic gateway failure is not retried blindly. A later explicit
   owner-authorized recovery can safely reconcile `failed` or uncertain
   `processing` state against Telegram before any retry/finalization. Recovery
   scans bounded Telegram history page-by-page and treats a capped/truncated
   history as uncertain, never as proof that a refund is absent.
8. A privacy-safe canary status reports only: public checkout off, canary
   armed/completed/refunded state, product, amount and aggregate booleans.
9. The production-canary evidence is labelled
   `telegram_production_canary` and is never accepted by
   `validate_stars_test_receipt`, which continues to require
   `environment=telegram_test`.
10. After the canary, canary mode is disabled again and a fresh production
    probe confirms public checkout off, canary off, bot heartbeat ready, admin
    health ok and the refund completed. Final receipt construction is accepted
   only from this disabled-and-refunded status. A privacy-safe read-only status
   reader remains available after disabling the canary.
11. A reviewed operator entrypoint exposes only three explicit operations:
    privacy-safe status, owner-approved reconciliation-first refund recovery,
    and mode-0600 final receipt creation. Writes require `--execute`; no command
    prints owner, order, payment, refund or charge identifiers. Production
    recovery loads the existing mode-0600 `BOT_TOKEN_FILE` through the shared
    fail-closed secret loader; it never requires an inline token. The exact
    OVH commands run in the current Docker services with the production-gated
    profile, use only the persistent `/app/state` mount for the final receipt,
    and include executable read-only SHA, PostgreSQL revision, heartbeat,
    loopback/public health, backup and canary-status probes.

## Error and edge cases

- Missing, zero, multiple or malformed owner IDs fail configuration.
- Any canary amount other than 10, another product, an underlying `ai-mini`
  catalog price other than 69, archived product, subscription,
  stale terms, missing seller profile, stale economics or unsigned order fail
  before Telegram accepts payment.
- Refund failure stops the operation and leaves durable pending evidence for
  manual recovery; it is never retried blindly.
- Canary orders carry durable provenance independent of owner/product/amount,
  so historical matching purchases cannot contaminate status or evidence.
- A historical v1 marker/order at 69 XTR does not block creation of the v2
  10 XTR claim and is never mutated by v2 operations.
- The owner receives an explicit canary-refunded confirmation, never the
  generic message that credits remain available.
- No logs, receipts, commands or durable writebacks include Telegram IDs,
  names, usernames, messages, tokens, charge IDs, database URLs or raw logs.

## Verification gates

- Focused RED then GREEN tests for configuration, handler isolation,
  fulfillment/refund idempotency and receipt separation.
- Full unit suite, compilation and `git diff --check`.
- Complete diff and privacy/secret scan.
- Branch, commit, push and review-ready PR before any production mutation.
- Merge/deploy/restart remain separate exact release actions under the
  repository contributor contract.
