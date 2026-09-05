# Reviewed prompt contracts

These plain-text files are the versioned runtime instructions reviewed with the
code that consumes them.

| Contract | Version | Runtime consumer | Evaluation surface |
|---|---|---|---|
| `ai-tutor-v1.txt` | AI Tutor v1 | `OpenAIResponsesProvider.generate` | `tests/fixtures/ai_tutor_eval.json` |
| `mirror-v7.txt` | Mirror v7 (active) | `OpenAIResponsesProvider.generate_mirror` | `tests/fixtures/mirror_quality_v2.json`, `tests/test_zerkalo_communication_v1.py` |

`mirror-v6.txt` is retained as the historical predecessor to the active
`mirror-v7.txt` contract. `mirror-v5.txt` and `mirror-v4.txt` remain historical
evidence of the earlier reviewed behavior.

## Change procedure

1. Create a **new version** of the relevant prompt file; do not silently rewrite
   an already reviewed contract.
2. Request **review** of the prompt and its runtime wiring.
3. Update and run the corresponding **evaluation** fixture or quality gate.
4. Add or update a contract **test**, then run the affected and full suites.
