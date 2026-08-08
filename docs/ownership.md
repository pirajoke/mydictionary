# Ownership and escalation

This matrix separates safe preparation from consequential owner actions. A role
must be assigned to a real person before an owner-gated operation begins.

## Responsibility matrix

| Domain | Single accountable role | Preparation may be delegated to | Separate review required |
| --- | --- | --- | --- |
| Product scope and pilot admission | Product owner | Product analyst / agent | Product owner before approval or outreach |
| Production release and launchd | Production operator | Agent for read-only preflight and draft commands | Product owner before merge, deploy, restart, or enablement |
| Telegram production token | Credential owner | Agent for non-secret checks and receipt template | Credential owner for file creation and BotFather rotation |
| Off-site backup and recovery keys | Recovery owner | Agent for tooling checks | Recovery owner for remote, key custody, upload, and restore |
| AI runtime and provider budget | Product owner | Agent for deterministic evaluation and cost analysis | Product owner before a real call or enablement |
| Voice processing and consent | Product owner | Agent for deterministic tests | Product/legal review before a real voice test or enablement |
| Stars billing, refund, and subscription | Billing owner | Agent for isolated preflight | Billing owner before any transaction or mutation |
| Terms, privacy, and retention | Product/legal owner | Agent for draft comparison | Human approval of the exact version |
| Product metrics and weekly check-in | Product owner | Agent for aggregate read-only report | Human decision; no automatic outreach |
| Incident response and log cleanup | Incident owner | Agent for preview, scan, and sanitized-copy verification | Owner before source deletion or credential action |

One person may hold several roles, but each row still has one accountable role.

## Escalation rules

Stop the current operation and ask for an exact decision when:

1. production release, schema, heartbeat, health, or backup evidence disagrees;
2. a command would read, create, move, rotate, revoke, or expose a credential;
3. a command would send a message, approve a user, call an AI provider, create
   an invoice, charge, refund, or cancel a subscription;
4. a backup target, encrypted object, checksum, database, or recovery identity
   is ambiguous;
5. a migration or restore has started and rollback could discard writes;
6. production and test Telegram environments could share a token, user,
   database, data directory, terms, or payload secret;
7. a report would expose a learner identifier, message, prompt, answer, charge
   identifier, private path, or raw log;
8. the requested action expands beyond the reviewed branch/PR outcome;
9. a percentage is being used for a product decision with fewer than ten
   eligible pilot learners;
10. an owner approval is older than or different from the exact current action.

## Handoff minimum

Every consequential operation should have a private receipt containing only
non-secret evidence: timestamp, actor role, reviewed target, before/after
release or revision, check results, rollback boundary, and remaining gates.

Receipts must never contain credentials, database URLs, learner data, raw log
content, Telegram charge IDs, or recovery identity material.
