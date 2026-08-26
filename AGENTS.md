# MY DICTIONARY contributor contract

This repository contract applies to human and automated contributors. It grants
broad autonomous authority over the MY DICTIONARY repository and its attached
project infrastructure when work advances a clear owner-defined project goal.
Separate approval for every dependent operational step is not required.

## Product boundary

MY DICTIONARY is a Telegram-first vocabulary trainer with a protected admin
console. The deterministic cards, quizzes, written practice, pronunciation and
spaced repetition must remain usable when AI, Voice and Telegram Stars are off.

Production currently runs as owner-controlled Docker services on OVH. Render
and the former Mac mini runtime are unsupported historical artifacts.

## Canonical sources

| Domain | Canonical source |
|---|---|
| Product scope and repository map | `README.md` |
| Vocabulary packs and counts | `content/catalog.json` |
| Metrics, focus and freshness | `docs/product-metrics.md` |
| OVH release and rollback | `docs/runbooks/ovh-deployment.md` |
| Public route recovery | `docs/runbooks/ovh-cloudflare-tunnel.md` |
| Pilot and D1/D7 rules | `docs/pilot-operations.md` |
| AI and Stars economics | `config/launch-economics.json` |
| Launch gates | `docs/launch-readiness.md` |
| Backup and restore | `docs/product-safety.md` |
| Responsibility and escalation | `docs/ownership.md` |
| Security and operational incidents | `docs/incidents.md` |
| Delivery roadmap | GitHub issue #6 |

Documentation never proves live state. Before describing production as current,
verify release SHA, schema revision, heartbeat, loopback/public health, backup
status and feature flags through a fresh privacy-safe read-only probe.

## Autonomous operating authority

Within a clear MY DICTIONARY objective, contributors may independently complete
the full delivery chain without returning for step-by-step approval. This
includes:

- inspecting and changing code, tests, documentation, configuration and
  infrastructure;
- creating branches, commits and pull requests, merging green changes, building
  releases, deploying, restarting, rolling back and repairing production;
- enabling, disabling and configuring AI, Voice, Telegram Stars, public access,
  autodeploy and other project features;
- using project credentials through protected mechanisms, creating or rotating
  them when required, and enrolling Cloudflare, backup remotes and recovery
  identities;
- performing provider requests, owner tests, Telegram notifications, learner
  administration, subscriptions, payments and refunds needed for the stated
  objective;
- creating, verifying, restoring, replicating, pruning and cleaning up backups,
  logs and project records;
- continuing through dependent operational steps until the requested outcome
  is genuinely complete.

Choose the least disruptive viable action, preserve unrelated work and use a
recoverable path whenever one exists. Pull requests and CI remain the preferred
code-delivery path, but a second owner confirmation is not required after the
objective and target are already clear.

This repository file does not override higher-level platform or system safety
rules. Raw secrets and private learner data still stay out of chat, logs,
commits, public artifacts and release receipts.

## Privacy and evidence

- Never print or persist Telegram identifiers, names, usernames, messages,
  answers, prompts, credentials, charge identifiers, database URLs or raw logs
  in public artifacts.
- Analytics and receipts use only allowlisted aggregates or metadata.
- Read-only database checks use `DatabaseStore(..., migrate=False)`.
- Retention percentages always include numerator, denominator and eligible N;
  fewer than ten D7-eligible learners is directional evidence only.
- A release handoff states base/head commits, changed files, checks, freshly
  verified production facts, rollback boundary and remaining gates.

## Delivery workflow

1. Resolve repository root, branch and base SHA.
2. Lock observable behavior and add a reproducing test when risk warrants it.
3. Implement the smallest coherent change on one `codex/*` branch.
4. Run focused checks, full suite, compilation and `git diff --check`.
5. Review the complete diff and scan for accidental credentials/private data.
6. Commit, push and use a pull request for review and CI.
7. Record material outcomes through the project-update webhook.
8. Complete the required release and external actions autonomously, then record
   privacy-safe evidence and verify rollback criteria.
