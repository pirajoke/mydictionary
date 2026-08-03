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
OPENAI_API_KEY=...
AI_SAFETY_SALT=...
AI_INITIAL_CREDITS=0
AI_CREDITS_PER_REQUEST=1
AI_RESERVATION_TIMEOUT_SECONDS=300
AI_INPUT_USD_PER_MILLION=0
AI_CACHED_INPUT_USD_PER_MILLION=0
AI_CACHE_WRITE_USD_PER_MILLION=0
AI_OUTPUT_USD_PER_MILLION=0
```

`AI_SAFETY_SALT` is a secret random value of at least 16 characters and must
not be committed. When the feature is enabled, the application fails fast if
the API key, model, or salt is missing.

Provider prices are runtime configuration rather than product constants. The
initial allowance is granted once when a user first reserves an AI request.
Changing the environment value does not rewrite an existing allowance.
Reservations older than `AI_RESERVATION_TIMEOUT_SECONDS` are refunded on bot
startup and before that learner's next request. The allowed range is 60-86400
seconds; it must remain longer than the provider's maximum request duration.

The default model is the cost-sensitive GPT-5.6 Luna tier. Model choice and
rates must be validated with the evaluation set before any rollout. See the
[OpenAI model guide](https://developers.openai.com/api/docs/models) and
[Responses API reference](https://developers.openai.com/api/reference/python/resources/responses/methods/create).

## Stored Data

`ai_usage` stores request ID, user ID, action, provider/model, lifecycle status,
context fingerprint, token categories, configured cost estimate, latency, and a
sanitized error class. It contains no question, prompt, generated answer, API
key, or raw Telegram identity sent to the provider.

`ai_allowances` stores pilot available, reserved, and spent units. It is an
operational quota, not a paid wallet.

## Rollout Gate

- Keep the feature flag off in production.
- Run deterministic contract tests for English, Vietnamese, and Japanese.
- Run a separate live-provider evaluation with a non-production test account.
- Compare quality, cost, latency, and grounding before granting pilot credits.
- Production enablement requires a separate explicit deployment decision.
