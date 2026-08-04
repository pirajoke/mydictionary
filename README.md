# MY DICTIONARY

Telegram-first vocabulary learning bot with multilingual content, topic-based study blocks, spaced repetition, text-to-speech, and an optional gated AI tutor.

## Product scope

- English, Vietnamese, and Japanese vocabulary packs with Russian meanings and transcriptions.
- Guided onboarding and topic-based 10-word learning blocks.
- Flashcards, quizzes, review scheduling, and learner progress.
- Edge TTS pronunciation support.
- PostgreSQL-backed multi-user storage with Alembic migrations.
- Optional AI tutor with deterministic evaluation, credits, cost accounting, and fail-closed configuration.
- Separate server-rendered admin console with audited operator actions.

Payments and subscriptions are not part of the current release. The AI tutor remains disabled until its evaluation and rollout gates are approved.

## Local development

Requirements:

- Python 3.12+
- PostgreSQL 16 for the full storage and admin test path

Install dependencies:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --requirement requirements.txt
```

Configure secrets outside Git. The bot requires `BOT_TOKEN`; production also requires `DATABASE_URL`. Local SQLite is available only when `ALLOW_SQLITE_DEV=true` is set intentionally.

Start the Telegram polling process:

```bash
python bot.py
```

## Validation

```bash
python -m unittest discover -s tests -v
python -m compileall -q .
```

The GitHub Actions workflow runs the suite against PostgreSQL 16.

## Architecture

| Path | Purpose |
|---|---|
| `bot.py` | Telegram adapter and polling entrypoint |
| `mydictionary/` | Storage, learning, AI tutor, catalog, and admin services |
| `migrations/` | Alembic database migrations |
| `content/`, `words*.json` | Checked-in vocabulary content |
| `tests/` | Product, storage, AI-contract, and admin tests |
| `docs/product-foundation.md` | Product principles and rollout boundary |
| `docs/architecture-ai-platform.md` | Target service architecture |
| `docs/admin-console.md` | Admin runtime and security controls |
| `docs/ai-evaluation.md` | AI tutor evaluation gate |

Production is designed for the owner-controlled Mac mini runtime. `render.yaml` is retained as a legacy/alternative deployment artifact, not the current target architecture.

## Security and privacy

- Never commit Telegram, database, admin, or AI-provider credentials.
- AI usage records contain operational metadata, not learner prompts or generated answers.
- Admin state changes are authenticated, CSRF-protected, and audit logged.
- Production feature enablement and credential changes require explicit approval.

## License

MIT. See [`LICENSE`](LICENSE).
