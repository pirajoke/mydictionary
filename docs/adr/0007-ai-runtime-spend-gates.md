# ADR 0007: Bind AI runtime to metered spend gates

Status: accepted for disabled scaffolding

## Context

A learner credit limits product entitlement but does not itself bound provider
cost. Automatic SDK retries, billable invalid responses, concurrent requests,
stale rates, model aliases, and storage failures can all make actual spend
exceed a credits-times-average estimate.

## Decision

- Keep AI disabled and initial credits at zero by default.
- Bind an enabled process to one approved economics snapshot by ID and canonical
  SHA-256; reload it and check freshness on every request.
- Require the exact reviewed provider model and `service_tier="default"`, then
  verify both values returned by the provider.
- Configure the OpenAI SDK with `max_retries=0`. Record exactly one provider
  attempt before network I/O.
- Compute a conservative preflight token/cost upper bound from instructions,
  serialized input, strict output schema, protocol overhead, and output limit.
- Serialize project day, month, and concurrent in-flight exposure through a
  singleton PostgreSQL budget row.
- Record every returned provider response before output validation. Preserve
  billable telemetry when parsing, schema, grounding, or later settlement fails.
- Open a persistent breaker on unknown attempted outcomes, model/tier mismatch,
  response-cost outliers, stale recovery after an attempt, or telemetry storage
  failure.
- Store emergency response telemetry in a private append-only journal with no
  user ID, prompt, or output. Block new calls until it is reconciled.
- Expose breaker and budget state in the authenticated admin. Reset requires no
  active attempts, an empty fallback journal, a reason, CSRF validation, and an
  audit record.

## Consequences

The application can reject projected exposure before a call and prevent
cross-user oversubscription. Returned invalid output remains visible as billable
usage. The retrospective response threshold still cannot guarantee a hard
per-request provider cap; provider-side project caps and alerts remain required
for the first real call.

Unknown outcomes deliberately stop the service even though the learner credit
is refunded. An operator must reconcile provider telemetry before reset.

## Rejected options

- Treat credits as a cost cap: provider cost is variable and failures may bill.
- Use the SDK default retry policy: one application attempt could create more
  than one provider attempt.
- Count only validated responses: billable invalid and incomplete responses
  would disappear from economics.
- Keep the breaker in process memory: multiple workers and restarts would bypass
  it.
