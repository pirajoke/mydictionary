# Stars Commercial v1 verification

## RED evidence

The first targeted run failed for the intended reasons: no distinct credit
exhaustion signal, no admin credit exemption, no paywall/resume handlers, and a
catalog that failed the 8,500 micro-USD/XTR stress floor.

## Traceability

| Contract | Primary evidence |
| --- | --- |
| AC-CREDIT-01 | `test_success_settles_credit_and_records_technical_usage`, `test_provider_failure_refunds_entire_reservation` |
| AC-CREDIT-02 | `test_admin_request_is_metered_without_changing_wallet`, `test_admin_exemption_still_obeys_daily_attempt_limit`, `test_zero_credit_reservation_is_rejected_for_a_learner` |
| AC-CREDIT-03 | `test_ac_05_only_ai_is_approved_with_forty_free_pilot_credits`; deterministic learning suite remains green |
| AC-UX-01/02 | `test_credit_paywall_is_compact_and_keeps_one_bounded_question` |
| AC-UX-03 | `test_successful_payment_is_fulfilled_through_service`, `test_resume_callback_consumes_question_before_mirror`, `test_duplicate_payment_has_no_event_or_resume_action` |
| AC-UX-04 | Existing `/buy`, consent, pre-checkout, fulfillment, restart, and subscription tests in `test_stars_handlers.py` and `test_billing.py` |
| EC-UX-01 | `test_disabled_billing_paywall_has_no_purchase_action`, `test_disabled_terms_have_no_acceptance_button` |
| AC-PRICE-01/02/03 | `test_checked_in_snapshot_has_approved_ai_and_candidate_stars`, `test_seed_products_is_explicit_draft_and_idempotent`, `test_cli_has_no_product_activation_action` |
| AC-ANALYTICS-01 | Paywall, invoice, payment, duplicate-payment handler tests; analytics property allowlist tests |
| AC-ANALYTICS-02 | `test_commercial_funnel_uses_durable_orders_payments_and_ai_usage` |
| ERR-01/02/03 | Privacy-safe event tests, payment validation/reconciliation tests, and economics/configuration fail-closed tests |

## Quality gates

- `python -m compileall -q bot.py mydictionary ops tests`: passed.
- `python ops/mydictionary_economics.py --check`: passed; stress launchable.
- `python ops/mydictionary_commercial_launch.py check`: passed; no write.
- Targeted affected suite: 41 tests passed before refactor.
- Full suite: 492 tests passed, 3 expected skips.
- `git diff --check`: passed.

No real AI call, Telegram invoice, Stars transaction, refund, product
activation, credential change, feature-flag change, merge, or deployment was
performed.
