# MY DICTIONARY contributor contract

This repository contract applies to human and automated contributors. It
documents boundaries; it never grants production, credential, payment, or
communication authority.

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

## Safe autonomous work

Within the user's requested scope, contributors may inspect the repository,
run privacy-safe read-only aggregate checks, create an isolated `codex/*`
branch, edit code/tests/docs, run tests, and prepare a pull request or private
runbook. Preserve unrelated working-tree changes.

## Stop and obtain exact approval

Do not perform any of these actions from broad project intent alone:

- read, create, move, rotate, revoke or reveal a credential;
- enroll Cloudflare, an off-site remote or a recovery identity;
- make a provider request, payment, refund or subscription mutation;
- send a Telegram message, approve a learner or expose learner data;
- restore, prune or delete a backup, log or production record;
- enable AI, Voice, Stars, public access or autodeploy;
- merge, deploy or restart production unless the exact release action is in
  the current approved scope.

Approval for one step never approves the next step in a credential, payment,
restore or cleanup sequence.

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
8. Run only the explicitly approved release or external action, then record
   privacy-safe evidence and verify rollback criteria.
