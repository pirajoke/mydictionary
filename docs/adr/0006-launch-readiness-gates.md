# ADR-0006: Fail-Closed Launch Readiness Gates

**Status:** Accepted
**Date:** 2026-08-05
**Deciders:** MY DICTIONARY owner

## Context

The product already has free language packs, AI credit accounting, voice
transcription, Telegram Stars orders, refunds, subscriptions, and an admin
console. A launch audit found four boundaries that could not safely rely on UI
copy or operator memory: third-party processing consent, terms acceptance,
provider-cost configuration, and payment reconciliation over bounded history.

## Decision

Persist immutable consent document versions per learner and enforce the current
version at the service boundary. Snapshot the accepted terms version on every
payment order. Reject enabled AI or voice configurations with incomplete cost
or disclosure settings. Treat ledger tables as the authority for commercial
conversion and make remote Stars history completeness explicit during
reconciliation. Install an exact dependency resolution in CI and releases.

## Options considered

### UI-only confirmation

Low implementation cost, but callbacks and pre-checkout can bypass presentation
state, version changes are unauditable, and process restarts lose state. Rejected.

### Consent columns on `users`

Simple reads, but it overwrites acceptance history, mixes unrelated documents,
and cannot represent multiple versions. Rejected.

### Versioned consent records and service checks

Adds one table and migration, but supports document rotation, explicit
revocation, payment audit requirements, and fail-closed checks. Selected.

### Analytics events as the sales authority

Useful for intent, but events are deliberately best effort and subject to
retention. Rejected for invoices, payments, AI completion, and repeat purchases.

## Consequences

- A document version change intentionally blocks new billing or voice work until
  the learner accepts again.
- Billing terms remain after learning-data erasure; voice consent does not.
- Old unpaid orders with an earlier terms version fail pre-checkout and must be
  recreated. Already delivered successful payments remain fulfillable.
- Operators must maintain reviewed positive pricing for every metered token
  category and refresh the dependency lock deliberately.
- Live provider quality and real payment behavior remain separate approval gates.
