# MY DICTIONARY

MY DICTIONARY is a Telegram-first vocabulary trainer with themed lessons,
spaced repetition, pronunciation audio, quizzes, and a protected operations
console.

## Product scope

- Free starter packs for English, French, German, Japanese, Arabic, Chinese,
  Russian, and Spanish, plus the existing Vietnamese pack.
- Topic-based 10-word learning blocks, flashcards, written and multiple-choice
  tests, XP, streaks, and scheduled review.
- Russian meanings, target-language spelling, Latin transcription, and
  text-to-speech pronunciation.
- PostgreSQL multi-user storage with Alembic migrations and an explicit
  local-only SQLite mode.
- A server-rendered admin console for learner access, pilot D1/D7 retention,
  privacy-safe product analytics, credit operations, and audit history.
- Optional AI tutor, voice practice, and Telegram Stars billing. All three are
  fail-closed and remain off until their separate rollout gates are approved.
- Verified local PostgreSQL backups, encrypted off-site replication tooling,
  retention controls, health monitoring, and a migration-aware Mac mini
  release process.

## Local development

Requirements:

- Python 3.12+
- PostgreSQL 16 for the full storage and admin path

Install the locked dependencies:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --requirement requirements.lock
```

Keep secrets outside Git. The bot requires `BOT_TOKEN`; production also
requires `DATABASE_URL`. SQLite is available only when
`ALLOW_SQLITE_DEV=true` is set explicitly.

Access is fail-closed by default: `BOT_ACCESS_MODE=allowlist` admits only the
Telegram IDs listed in `ALLOWED_USER_ID` or comma-separated
`ALLOWED_USER_IDS`. Set one of those values for private local testing. Use
`BOT_ACCESS_MODE=public` only as a deliberate public-access opt-in; `pilot`
keeps self-registration separate from owner approval.

Start the Telegram polling process:

```bash
python bot.py
```

For admin-console setup and local commands, see
[`docs/admin-console.md`](docs/admin-console.md).

## Validation

```bash
python -m unittest discover -s tests -v
python -m compileall -q .
```

GitHub Actions runs the complete suite against PostgreSQL 16, including
migrations, isolated persistence, and concurrent credit reservations.

## Repository map

| Path | Purpose |
|---|---|
| `AGENTS.md` | Repository agent boundaries, canonical sources, and owner gates |
| `bot.py` | Telegram adapter and polling entry point |
| `mydictionary/` | Storage, catalog, learning, billing, privacy, AI, voice, and admin services |
| `migrations/` | Alembic database migrations |
| `content/`, `words*.json` | Versioned vocabulary sources and generated packs |
| `ops/` | Mac mini deploy, backup, monitoring, retention, and billing wrappers |
| `tests/` | Product, storage, operations, safety, and provider-contract tests |
| `docs/product-foundation.md` | Product principles and rollout boundary |
| `docs/product-metrics.md` | NSM, OMTM, metric formulas, freshness, and weekly check-in |
| `docs/pilot-operations.md` | Controlled cohort and D1/D7 measurement |
| `docs/launch-readiness.md` | Paid and voice release gates |
| `docs/ownership.md` | Responsibility matrix and escalation rules |
| `docs/incidents.md` | Privacy-safe append-only incident history |
| `docs/runbooks/mac-mini-deployment.md` | Production deployment and recovery runbook |

Production runs on an owner-controlled Mac mini. `render.yaml` is an obsolete
historical artifact and is not a supported or deployable production
configuration.

## Security and privacy

- Never commit Telegram, database, admin, backup, or provider credentials.
- Product analytics accept only allowlisted structured fields, never learner
  messages, answers, prompts, names, or contact details.
- AI usage records retain operational metadata rather than prompts or generated
  answers; voice transcripts are temporary and separately consented.
- Admin mutations require authentication and CSRF protection and are written to
  an audit log.
- Feature activation, migrations, external messages, payments, and production
  deployment require explicit operational approval.

## License

The application source code is MIT-licensed; see [`LICENSE`](LICENSE). The
seven generated schema-v2 starter packs derive from the project's original
`content/basic_100.tsv` matrix. Verify provenance and redistribution rights
before republishing legacy or externally supplied vocabulary datasets.
