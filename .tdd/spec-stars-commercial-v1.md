# Stars Commercial v1

Status: locked on 2026-08-14.

This contract supersedes AC-ECON-03 and AC-ECON-04 in
`spec-product-polish-i18n-groq-economics.md`; those earlier prices did not meet
the later 8,500 micro-USD/XTR stress floor. It also supersedes the catalog,
provider-envelope, and seed-count values in AC-1, AC-2, and AC-7 of
`spec-commercial-launch-v1.md`; all fail-closed, legal, measurement, and
no-activation requirements from that contract remain in force.

## Credit contract

- AC-CREDIT-01: A normal learner AI request reserves one configured credit
  before provider work, settles it only after a valid provider response, and
  releases it on every failed or rejected response. Existing global spend,
  in-flight, breaker, and rolling per-user request limits remain mandatory.
- AC-CREDIT-02: A user whose durable role is `admin` is exempt from the credit
  charge only. The request still creates a normal metered usage row, reserves
  project exposure, permits at most one provider attempt, and remains subject
  to all runtime spend and rate limits. Its reserved and billed credits are
  both zero and its wallet is unchanged.
- AC-CREDIT-03: New learners retain the approved 40-credit initial grant. Free
  deterministic dictionaries, lessons, cards, quizzes, written practice, and
  pronunciation playback never require Stars or AI credits.

## Telegram purchase UX

- AC-UX-01: When an AI request is rejected because the learner has no credits,
  the bot shows one compact localized paywall with the current balance and a
  single purchase action. It does not create an invoice automatically.
- AC-UX-02: The rejected question is kept only in bounded Telegram
  `user_data`: at most 500 characters, no raw voice/audio, and a 30-minute
  expiry. A newer rejected question replaces the older one.
- AC-UX-03: After a newly fulfilled Stars payment, the receipt reports the new
  balance and offers one `Continue question` callback when a pending question
  is still current. The callback consumes and clears that pending question
  before routing it through the ordinary consented Mirror path. Duplicate or
  stale callbacks cannot run it twice.
- AC-UX-04: Existing `/buy`, versioned terms acceptance, active-product list,
  signed single-user order, XTR invoice, pre-checkout validation, and
  `successful_payment` fulfillment remain the only checkout path.
- EC-UX-01: With Stars disabled or with no active products, the paywall remains
  informative and fail-closed; it exposes no invoice button and changes no
  wallet state.

## Commercial catalog

- AC-PRICE-01: The immutable candidate catalog is Mini 20/69 XTR, Start
  50/129 XTR, Value 150/319 XTR, and Monthly 100/229 XTR. Every product remains
  `draft`; this implementation has no activation command.
- AC-PRICE-02: Every package retains the conservative 6,000 micro-USD provider
  envelope per credit, 10% refund reserve, and 100,000 micro-USD support
  overhead. Nominal and 8,500 micro-USD/XTR stress contribution margins must
  both be at least 50%.
- AC-PRICE-03: One-time packages are the initial launch surface. The monthly
  subscription remains draft until a separate renewal/cancel/refund approval.

## Analytics and audit

- AC-ANALYTICS-01: The product records privacy-safe events for AI paywall
  shown, billing package selected, invoice created, and successful payment.
  Events contain bounded product/mode dimensions but no question, answer,
  invoice payload, charge ID, credentials, or seller data.
- AC-ANALYTICS-02: The admin commercial funnel exposes those stages together
  with payment count, payer count, gross XTR, AI provider cost, and an explicitly
  labelled estimated contribution margin. Existing order/payment/refund and
  reconciliation views remain available.
- EC-ANALYTICS-01: A duplicate `successful_payment` does not create a second
  credit grant or a second successful-payment product event.

## Failure behavior

- ERR-01: Invoice creation, pre-checkout, fulfillment, resume, analytics, or AI
  failure never logs or displays a secret, signed payload, charge ID, question,
  or answer.
- ERR-02: A payment accepted by Telegram but not locally fulfilled keeps the
  existing `/paysupport` recovery message and creates no speculative credits.
- ERR-03: Billing configuration, seller identity, reviewed terms, economics,
  product margin, and isolated test-environment gates continue to fail closed.

## Out of scope

- Merge, production deployment, restart, feature-flag changes, credential or
  seller-data enrollment, product activation, real AI/provider calls, Telegram
  invoices, Stars payments, refunds, subscription mutations, and public launch.
- Changes to the approved AI model, provider rates, initial credit count,
  provider budgets, deterministic learning access, or Telegram command count.
