# MY DICTIONARY agent contract

This file is the repository-level operating contract for human and automated
contributors. It does not grant production authority.

## Product boundary

MY DICTIONARY is a Telegram-first vocabulary trainer with a protected admin
console. Production runs on the owner-controlled Mac mini. Render is an
unsupported historical artifact.

The deterministic learning core must remain usable when AI, voice, and
Telegram Stars are disabled.

## Canonical sources

| Domain | Canonical source |
| --- | --- |
| Product scope and repository map | `README.md` |
| Vocabulary packs and counts | `content/catalog.json` |
| Product metric definitions and freshness | `docs/product-metrics.md` |
| Production deployment and rollback | `docs/runbooks/mac-mini-deployment.md` |
| Pilot cohort and D1/D7 rules | `docs/pilot-operations.md` |
| AI and Stars economics | `config/launch-economics.json` |
| AI/Voice/Stars launch gates | `docs/launch-readiness.md` |
| Backup and restore contract | `docs/product-safety.md` |
| Responsibility and escalation | `docs/ownership.md` |
| Security and operational incidents | `docs/incidents.md` |
| Delivery roadmap and historical decisions | GitHub issue #6 |

Runtime state is never inferred from documentation alone. Verify the active
release, database revision, heartbeat, health, backup status, and feature flags
read-only on the production host before reporting them as current.

## Safe autonomous work

Agents may perform these actions when they are within the requested scope:

- inspect repository and aggregate privacy-safe production state read-only;
- create an isolated `codex/*` branch;
- edit source, tests, documentation, and local audit artifacts;
- run deterministic local and disposable-PostgreSQL tests;
- commit, push, and open a draft pull request when publication was requested;
- prepare commands, checklists, receipts, and rollback plans without executing
  consequential production actions.

## Owner-gated actions

Stop and obtain a separate, explicit approval for the exact action and target
before any of the following:

- merge a pull request or deploy/restart production;
- change production launchd state or enable autodeploy;
- create, read, move, rotate, revoke, or expose credentials;
- configure an off-site backup remote or recovery identity;
- upload, download, decrypt, restore, prune, or delete a backup;
- approve pilot users or send Telegram notifications/messages;
- enable AI, voice, Stars, public access, or non-zero initial credits;
- make an AI provider request;
- create an invoice, payment, refund, or subscription mutation;
- delete or replace source logs, production data, or recovery evidence;
- change repository visibility or publish private/user data.

Approval for one action does not approve the next action in a sequence. In
particular, token-file cutover, BotFather token rotation, historical-log
cleanup, off-site upload, restore drill, Stars test, merge, and deployment are
separate gates.

## Privacy rules

- Never print or persist Telegram IDs, names, usernames, messages, answers,
  prompts, credentials, charge identifiers, database URLs, or private paths in
  public artifacts.
- Product analytics contain only allowlisted structured dimensions.
- Production checks must aggregate before output.
- Use `DatabaseStore(..., migrate=False)` for read-only aggregate probes.
- Never include raw logs or environment dumps in issues, pull requests, test
  output, or project-update records.

## Delivery workflow

1. Resolve the repository root, branch, and exact base SHA.
2. Inspect the working tree and preserve unrelated user changes.
3. Create or reuse one isolated `codex/*` branch for one coherent outcome.
4. Add a reproducing test before behavior changes with regression risk.
5. Run focused checks, then the full deterministic suite.
6. Review `git diff --check`, the complete diff, and secret-pattern output.
7. Commit intentionally, push, and leave the pull request as draft unless the
   owner explicitly requests otherwise.
8. Record the verification through the project-update webhook.
9. Keep merge, production deployment, credentials, payments, and external
   messaging outside the pull request workflow unless separately approved.

## Required evidence

Every handoff should state:

- base and head commit;
- files changed;
- focused and full checks with exact results;
- production state only when freshly verified;
- remaining owner gates and one next safe step.

Percentages for pilot metrics must always include absolute numerator and
denominator. A cohort below ten learners is directional evidence only.
