# AI Tutor Evaluation Gate

No model is enabled for users until it passes a deterministic evaluation set.

## Required Cases

- Explain a word from the active 10-word block in Russian first.
- Show target writing, Latin transcription, Russian meaning, and two examples.
- Never include a word outside the active block when asked for a block test.
- Respect the active language for English, French, German, Japanese, Arabic,
  Chinese, Russian, and Spanish.
- Preserve Japanese romaji and keep Japanese writing in parentheses where the
  current product format requires it.
- Identify weak words only from computed progress supplied by a tool.
- Refuse to claim that it changed credits, payments, roles, or progress.
- Handle missing examples and ambiguous Russian meanings without inventing
  user history.

## Measurements

- Structured-output validity.
- Grounding accuracy against dictionary content.
- Russian-first formatting compliance.
- Hallucinated terms per response.
- Input, cached input, output, reasoning, and audio tokens.
- Provider cost, latency p50/p95, timeout rate, and automatic refund rate.

The first benchmark compares an economical model and one stronger fallback on
the same cases. Model names and prices remain admin configuration, not product
logic.

The deterministic stage 2 contract set lives in
`tests/fixtures/ai_tutor_eval.json` and covers all eight launch languages
without making provider requests. Live-provider quality is
a separate rollout gate and must not run in normal CI.
