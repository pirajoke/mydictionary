# ADR 0002: Meter AI Tutor Requests Before Payments

Status: accepted for stage 2

## Context

AI requests create variable provider cost and can fail after a learner starts an
action. The product needs usage statistics and deterministic refunds before the
paid wallet and Telegram Stars ledger are implemented.

## Decision

- Keep the tutor behind `AI_TUTOR_ENABLED=false` by default.
- Reserve a fixed pilot allowance credit before each provider call.
- Settle the reservation only after a valid block-grounded response.
- Release the complete reservation after provider, parsing, or grounding
  failure.
- Store technical usage and cost data, but never prompts or generated answers.
- Keep provider calls behind an `AIProvider` protocol.
- Use the OpenAI Responses API adapter first, with structured JSON output,
  `store=false`, and a salted privacy-preserving safety identifier.
- Keep paid balances and append-only financial ledger entries out of this stage.

## Consequences

- A learner cannot create unbounded provider cost after the feature is enabled.
- Failed requests leave the learner's pilot allowance unchanged.
- Admin analytics can later aggregate requests, tokens, cost, latency, models,
  and failure codes without reading private conversations.
- Pilot allowance rows are not a financial ledger and must not be used for
  Telegram Stars fulfillment or refunds.

## Rejected Options

- Charge after the provider call: this permits overspending under concurrency.
- Store full prompts and answers for debugging: this increases privacy and
  retention risk without being required for stage 2 metrics.
- Let the model calculate or mutate credits: balances remain application-owned
  transactional state.
