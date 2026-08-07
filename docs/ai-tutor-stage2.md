# AI Tutor Stage 2

## User Flow

1. The learner creates a valid topic block with `/learn`.
2. `/ai <question>` or the block's `AI-репетитор` button submits only that
   active block to the tutor.
3. The application renders Russian explanation first, then target writing,
   canonical transcription, Russian meaning, and examples.
4. `/ai_stats` shows pilot allowance, completed/refunded requests, provider
   tokens, and configured estimated cost.

The model cannot change learning progress, credits, payments, or roles. Terms,
transcriptions, and meanings displayed to the learner come from dictionary
content, not generated output.

## Runtime Configuration

The feature is disabled unless explicitly enabled:

```text
AI_TUTOR_ENABLED=false
AI_PROVIDER=openai
AI_MODEL=gpt-5.6-luna
AI_SERVICE_TIER=default
OPENAI_API_KEY=...
AI_SAFETY_SALT=...
AI_INITIAL_CREDITS=0
AI_CREDITS_PER_REQUEST=1
AI_RESERVATION_TIMEOUT_SECONDS=300
AI_INPUT_USD_PER_MILLION=<positive reviewed rate>
AI_CACHED_INPUT_USD_PER_MILLION=<positive reviewed rate>
AI_CACHE_WRITE_USD_PER_MILLION=<positive conservative rate>
AI_OUTPUT_USD_PER_MILLION=<positive reviewed rate>
AI_ECONOMICS_SNAPSHOT_PATH=<approved snapshot>
AI_ECONOMICS_SNAPSHOT_ID=<exact ID>
AI_ECONOMICS_SNAPSHOT_SHA256=<canonical SHA-256>
AI_MAX_PREFLIGHT_COST_MICRO_USD_PER_REQUEST=5000
AI_RETROSPECTIVE_BREAKER_MICRO_USD_PER_RESPONSE=5000
AI_MAX_PROJECT_COST_MICRO_USD_PER_DAY=25000
AI_MAX_PROJECT_COST_MICRO_USD_PER_MONTH=100000
AI_MAX_IN_FLIGHT_COST_MICRO_USD=5000
```

`AI_SAFETY_SALT` is a secret random value of at least 16 characters and must
not be committed. When the feature is enabled, the application fails fast if
the API key, model, salt, any metered price category, exact approved snapshot,
or project budget is missing or invalid. It reloads and validates snapshot
freshness on every request.

Provider prices are runtime configuration rather than product constants. The
initial allowance is granted once when a user first reserves an AI request.
Changing the environment value does not rewrite an existing allowance.
Reservations older than `AI_RESERVATION_TIMEOUT_SECONDS` are refunded on bot
startup and before that learner's next request. The allowed range is 60-86400
seconds; it must remain longer than the provider's maximum request duration.
An attempted provider call with no known response opens the persistent breaker
because the refund does not prove that the provider incurred no cost.

The default model is the cost-sensitive GPT-5.6 Luna tier. Model choice and
rates must be validated with the evaluation set before any rollout. See the
[OpenAI model guide](https://developers.openai.com/api/docs/models) and
[Responses API reference](https://developers.openai.com/api/reference/python/resources/responses/methods/create).

## Stored Data

`ai_usage` stores request ID, user ID, action, provider/model, lifecycle status,
context fingerprint, snapshot ID/hash, requested/returned service tier,
provider-attempt state, token categories, configured/actual cost estimate,
latency, and a sanitized error class. It contains no question, prompt,
generated answer, API key, or raw Telegram identity sent to the provider.

Provider response telemetry is committed before output parsing and grounding.
If that database write fails, a mode-0600 fallback journal stores only the
technical response fields and blocks all later calls until operator
reconciliation. The SDK uses `max_retries=0`; one application attempt therefore
allows one provider attempt.

`ai_allowances` stores pilot available, reserved, and spent units. It is an
operational quota, not a paid wallet.

## Rollout Gate

- Keep the feature flag off in production.
- Run deterministic contract tests for all eight launch languages.
- Run a separate live-provider evaluation with a non-production test account.
- Compare quality, cost, latency, and grounding before granting pilot credits.
- Production enablement requires a separate explicit deployment decision.
