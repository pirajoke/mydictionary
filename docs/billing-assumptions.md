# Billing Assumptions

These are implemented Stage 4 constraints, not launch prices.

- Users see stable AI credits. Provider tokens remain an internal cost metric.
- Dictionary browsing, blocks, deterministic quizzes, flashcards, and spaced
  repetition do not consume AI credits.
- An AI action reserves credits before the provider request and settles them
  after success. Failure, cancellation, or timeout releases the reservation.
- Credit movements use an append-only ledger plus a transactionally maintained
  wallet balance and idempotency key.
- Digital services sold inside Telegram use Telegram Stars (`XTR`). Credits are
  granted only after a `successful_payment` update.
- Every payment stores the Telegram charge ID. Refund and subscription actions
  are audited.
- Initial action weights are hypotheses only: short explanation 1, generated
  examples 1, deep explanation 2, roleplay 2, voice analysis 2-3.
- Public package prices are set only after a closed alpha measures real model,
  speech, infrastructure, refund, and support costs.
- The checked-in package table is a dated draft hypothesis, validated by
  `ops/mydictionary_economics.py`; it does not create active catalog products.
- Text AI is controlled by the credit wallet and has no per-user daily request
  cap. Conservative preflight and project day/month/in-flight budgets plus the
  retrospective response breaker continue to bound provider exposure.
- Voice translation keeps its independent
  `VOICE_TRANSLATION_MAX_DAILY_REQUESTS_PER_USER=5` safety limit; it does not
  inherit the text-AI sentinel.
- The provider SDK uses zero automatic retries. A response is metered before
  output validation; an unknown attempted outcome fails closed and opens the
  breaker. The response threshold is not represented as a hard cost cap.
- Enabled runtime configuration must match an exact approved economics
  snapshot ID/hash and pass a freshness check on every request.
- Unlimited AI usage is excluded from the first launch.
- Product activation requires measured package cost, a configured conservative
  net value per XTR, current economics review, approved terms, and an estimated
  margin at or above its explicit floor.
- Turning checkout off does not turn successful-payment fulfillment off. The
  payload secret remains available until issued orders are reconciled.
- Refund API calls are explicit operator actions through an injected gateway;
  the admin web process only creates audited credit holds and requests.
