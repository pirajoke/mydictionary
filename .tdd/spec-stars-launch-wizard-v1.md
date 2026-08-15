# Stars Launch Wizard v1

Status: locked on 2026-08-15.

This contract extends `spec-stars-commercial-v1.md`. It adds a safe operator
path from the existing disabled commercial scaffold to a future, separately
approved Telegram Stars launch. It does not itself enable checkout or perform
any Telegram operation.

## One-time enrollment

- AC-ENROLL-01: An authenticated administrator can use one bounded enrollment
  window to submit seller identity, support contact, exact versioned terms, and
  dedicated Telegram test credentials. Profile and test credentials are
  consumed independently.
- AC-ENROLL-02: The production billing profile and Telegram test credentials
  are written as separate regular JSON files owned by the service user with
  mode `0600`. The parent must be an existing owner-controlled local-config
  directory, and symlinks, replacement, replay, unsafe permissions, oversized
  payloads, and windows longer than one hour fail closed.
- AC-ENROLL-03: The invoice payload secret is generated server-side with at
  least 256 bits of entropy. Terms are normalized once, hashed from the exact
  stored UTF-8 text, and require an explicit approval checkbox.
- AC-ENROLL-04: Every enrollment POST requires the existing authenticated
  session, valid CSRF token, and the current admin password. Audit events contain
  only action, outcome, and a short SHA-256 fingerprint; they never contain
  seller data, terms text, bot token, Telegram user ID, payload secret, or file
  path.
- EC-ENROLL-01: Disabled enrollment returns 404, an expired window returns 410,
  consumed entries cannot be overwritten, and a failed validation writes no
  partial destination file.

## Runtime profile

- AC-PROFILE-01: `BillingSettings` may load the billing profile only through an
  absolute owner-only regular file configured by `BILLING_LAUNCH_PROFILE_FILE`.
  The profile has an exact versioned schema and passes all existing seller,
  terms, hash, Telegram message-budget, and payload-secret validation.
- ERR-PROFILE-01: Inline seller, terms, approval, support, or payload-secret
  settings cannot be mixed with the profile file. Missing, malformed, extra,
  unsafe, or conflicting data fails closed without exposing values.

## Readiness and activation

- AC-GATE-01: A no-network readiness command reports only boolean/status gates
  for the private billing profile, dedicated test credentials, reviewed current
  economics, exact candidate catalog, disabled production checkout, and a
  privacy-safe test receipt.
- AC-GATE-02: A valid test receipt is owner-only, contains no identifiers or
  credentials, and proves purchase, duplicate delivery, restart recovery,
  reconciliation, and refund scenarios passed in Telegram's test environment.
- AC-ACTIVATE-01: The activation command is dry-run by default and refuses a
  database write without `--execute`. When every gate is green, it may change
  only `ai-mini`, `ai-starter`, and `ai-value` from the exact approved draft
  catalog to active. `ai-monthly` remains draft.
- AC-ACTIVATE-02: Activation is idempotent, audited by the existing product
  audit path, refuses catalog drift or any pre-existing unexpected active
  product, and never changes `TELEGRAM_STARS_ENABLED`, credentials, runtime
  configuration, terms, prices, credits, or subscription state.
- ERR-GATE-01: Any missing/invalid gate returns a safe list of blocker codes and
  prevents all writes. Output never contains PII, secrets, Telegram IDs,
  database URLs, local paths, invoice payloads, or charge IDs.

## Admin presentation and analytics

- AC-ADMIN-01: The billing tab shows one compact launch checklist and a single
  link to the enrollment wizard when a window is available; it does not add a
  new primary navigation group.
- AC-ADMIN-02: The checklist distinguishes setup, test evidence, catalog, and
  checkout status and retains existing payment/funnel metrics. Consumed forms
  display status and fingerprints only, never submitted values.

## Out of scope

- Merge, production deployment, restart, feature-flag changes, product
  activation in any real database, real credential entry, AI/provider calls,
  Telegram invoices, Stars payments, refunds, subscription mutations, or public
  launch.
- Changing the approved catalog, economics snapshot, AI model, initial credits,
  free learning modes, or Telegram command surface.
