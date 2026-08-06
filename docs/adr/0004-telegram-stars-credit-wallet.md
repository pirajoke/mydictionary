# ADR-0004: Telegram Stars and the AI credit wallet

**Status:** Accepted

**Date:** 2026-08-05

## Context

MY DICTIONARY keeps deterministic learning free and meters optional AI tutor
actions. Pilot allowances were sufficient before sales, but they do not provide
the immutable order, payment, credit, and refund history required for Telegram
Stars.

Telegram invoices for digital services use `XTR`. Credits must not be granted
from invoice creation or pre-checkout alone. Telegram can retry updates, and a
payment handler can be restarted after Telegram has accepted money.

## Decision

- Users buy stable MY DICTIONARY AI credits. Provider tokens and cost remain
  internal metrics.
- `ai_wallets` owns total unspent balance, active reservations, and cumulative
  spend. Available credits equal balance minus reservations.
- `billing_credit_ledger` is append-only. Every grant, settled AI spend, manual
  adjustment, and completed refund has a unique idempotency key.
- A payment order snapshots product title, description, credits, XTR price, and
  user. Its payload is HMAC-signed and remains below Telegram's 128-byte limit.
- Pre-checkout validates signature, owner, `XTR`, amount, state, and expiry. The
  bot limits validation to eight seconds so it can answer Telegram within ten.
- Credits are granted only from `successful_payment`. Telegram charge IDs and
  ledger idempotency keys prevent duplicate fulfillment.
- Checkout is fail-closed behind `TELEGRAM_STARS_ENABLED=false`. Successful
  payments for already-issued valid orders are still fulfilled after checkout
  is disabled.
- Refunds begin as an audited admin request that reserves refundable credits.
  The Telegram refund gateway is injected and is not invoked by the web admin.
  Failed or ambiguous calls keep the hold for reconciliation.
- Products cannot become active until measured cost, net value per XTR, and a
  positive minimum margin are configured and the estimate clears that floor.

## Options Considered

### Reuse pilot allowances without payment tables

Rejected because it cannot prove which Telegram charge created a balance or
prevent duplicate delivery and refund drift.

### Store provider tokens as the purchased unit

Rejected because model prices and tokenization change. It would expose internal
cost mechanics and create unstable user value.

### Credit at pre-checkout

Rejected because pre-checkout is authorization, not proof of payment.

## Consequences

- Migration `0006_telegram_stars_billing` copies legacy allowance state into the
  wallet and copies legacy admin ledger entries into a namespaced financial
  ledger.
- Billing payload secrets must remain available while any issued order can
  still produce a successful payment update, even when checkout is disabled.
- A production rollout requires backup, migration, product pricing review,
  explicit flag activation, and separate payment smoke-test approval.
- Remote Telegram transaction reconciliation remains an explicit operator
  action; no background process can issue a refund by itself.
