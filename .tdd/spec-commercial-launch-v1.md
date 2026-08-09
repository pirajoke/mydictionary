# Commercial Launch v1 - Locked TDD Spec

Base: `d7bca5b7319c07bb44846d471306a48d47334635`

## Acceptance criteria

- **AC-1 Final candidate catalog:** the versioned commercial contract contains
  exactly `ai-starter` (50 credits / 100 XTR), `ai-value` (150 / 240 XTR), and
  `ai-monthly` (100 / 180 XTR / 30 days). Candidate products are seeded into
  the database as `draft`, never `active`.
- **AC-2 Nominal margin:** each package has a conservative provider allowance
  of 5,000 microUSD per credit, a 10% refund reserve, 100,000 microUSD support
  overhead, and a nominal contribution margin of at least 5,000 bps at 10,000
  microUSD net per XTR.
- **AC-3 Deterioration check:** the contract calculates the lower-net scenario
  at 8,500 microUSD per XTR. A package below its 5,000 bps floor is explicitly
  reported as blocked; no aggregate average may hide the failure.
- **AC-4 Immutable measurement:** the contract pins a SHA-256 report for the
  single measured Gate-2 call. Validation covers returned model, default tier,
  exactly one provider attempt, token fields, local cost, latency and response
  validation. The report contains no user ID, request ID, prompt, response,
  credential, or provider charge identifier. Unverified dashboard charge is
  represented as unknown, not invented.
- **AC-5 Production terms candidate:** the candidate terms identify the offer,
  price currency, credit delivery, recurring period, cancellation, refund and
  payment-support path. Acceptance explicitly requests immediate digital
  performance and acknowledges the applicable withdrawal consequence.
- **AC-6 Seller fail-closed:** Stars cannot be approved or enabled unless legal
  name, postal address, email, phone and monitored payment-support contact are
  present. `/terms` displays seller and support details; `/paysupport` remains
  available independently of learner access.
- **AC-7 Idempotent seeding:** a no-network CLI validates the exact contract and
  upserts the three products only with `--execute`. A second identical run makes
  no data or audit changes. The CLI cannot activate products.
- **AC-8 Commercial dashboard:** the authenticated billing admin shows contract
  ID/hash, measurement completeness, nominal/stress margins, seller/terms
  readiness, database catalog drift, checkout state, payment counts and local
  reconciliation. It never shows secrets or personal AI content.
- **AC-9 Disabled output:** rendered environment keeps AI, Stars and terms
  approval false and contains no API key, payload secret, seller details,
  support contact, or terms body.

## Error and boundary criteria

- **ERR-1** Reject changed package prices, costs, status, margin formulas or
  subscription period.
- **ERR-2** Reject a missing, modified, malformed or privacy-unsafe measurement
  report.
- **ERR-3** Reject a candidate whose nominal margin is below 5,000 bps.
- **ERR-4** Reject enabled/approved billing with incomplete seller identity,
  stale economics, missing support, missing explicit terms or weak secret.
- **EC-1** Topics remain disabled. If net economics deteriorate to the reviewed
  topics scenario, every failing product is blocked individually.
- **EC-2** Terms and support remain readable while checkout is disabled, but no
  acceptance button or invoice path is exposed.

## Explicitly out of scope

- Merge, production deployment, feature-flag changes, product activation,
  external AI calls, Telegram invoices/transactions/refunds and test-environment
  operations.
- A claim of final legal compliance or a fabricated seller identity/dashboard
  charge.
