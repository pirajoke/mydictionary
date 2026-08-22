# Ownership and escalation

Assign each accountable role to a real person before an owner-gated operation.
One person may hold several roles, but each domain still has one owner.

## Responsibility matrix

| Domain | Accountable role | Safe preparation | Separate review required |
|---|---|---|---|
| Product scope and cohort | Product owner | Aggregate analysis and experiments | Admission or outreach |
| OVH release | Production operator | Read-only preflight and rollback draft | Merge, deploy, restart |
| Public Cloudflare route | Network/credential owner | Connector-state diagnostics | Token, tunnel, DNS, service change |
| Telegram token | Credential owner | Metadata checks and receipt template | BotFather rotation and file mutation |
| Off-site recovery | Recovery owner | Tooling checks | Remote, key custody, upload and restore |
| AI provider budget | Product owner | Deterministic eval and cost model | Real provider call or limit change |
| Voice and consent | Product/legal owner | Deterministic tests | Real voice test or consent change |
| Stars billing | Billing owner | Isolated preflight | Transaction, refund, cancel, activation |
| Metrics | Product owner | Aggregate report | Product decision or outreach |
| Incidents and cleanup | Incident owner | Preview and sanitized-copy verification | Deletion or credential action |

## Escalation rules

Stop and request an exact decision when:

1. release, schema, heartbeat, health or backup evidence disagrees;
2. an action touches credentials, DNS, tunnel enrollment or key custody;
3. an action sends a message or calls a provider;
4. an action creates or mutates payment, refund or subscription state;
5. a backup object, checksum, identity, target database or data-loss window is
   ambiguous;
6. production and test Telegram environments might share state or credentials;
7. evidence could reveal learner, payment, prompt, message, raw-log or secret
   data;
8. the action expands beyond the reviewed branch or current approved target;
9. a percentage with fewer than ten eligible learners is being used as a
   product decision;
10. the cited approval is older than or different from the exact action.

Every consequential operation leaves a private, non-secret receipt: timestamp,
actor role, reviewed target, before/after release or revision, checks, rollback
boundary and remaining gates.
