# Product Foundation

This stage turns the single-owner bot into a multi-user product foundation. It
does not enable public access, AI calls, billing, Telegram Stars, merge, or
production deployment.

## Content catalog

`content/catalog.json` is the versioned source of truth for learning packs. A
pack has a stable `pack_id`, a short unique storage namespace, publication
status, visibility, price class, version, and declared word count. Startup
validation fails closed on duplicate identifiers, path traversal, missing
content, or a count mismatch.

The existing 661-word English dictionary is `admin` visibility and keeps the
legacy `en` storage namespace so the owner's progress remains intact. The
Vietnamese and Japanese basics packs are public and free. Telegram callbacks
carry `pack_id`; the server rechecks visibility before activation.

## User lifecycle

Users have an immutable-safe role transition: runtime configuration can promote
a learner to `admin`, but a later request cannot downgrade an administrator.
New learners complete two visible onboarding decisions before learning commands
are available:

1. Select a published public pack. Russian meanings and a general-learning goal
   are applied as safe defaults.
2. Select a daily pace of 5, 10, or 20 cards.

Pack enrollment and the active pack are persisted independently from Telegram
session state. Existing configured administrators are bootstrapped onto the
pack matching their previous active language and do not lose legacy progress.

## Telegram learning experience

The home screen has one primary action: `Урок на сегодня`. It starts a
spaced-repetition-prioritized lesson immediately in card mode, using the
learner's saved daily pace. `Повторить` starts a due-only lesson and gives a
clear empty state when nothing is due. Topics, progress, and settings remain
available as secondary actions.

Cards are shown one at a time. The front contains a topic emoji, position,
five-step progress indicator, target word, transcription, and pronunciation.
The revealed side adds the Russian meaning and example, with simple `Знаю` and
`Не знаю` ratings plus an explicit pronunciation replay. Existing quiz, typing,
and topic-block callbacks remain supported for compatibility.

## Product analytics

The bot records only structured events and allowlisted dimensions. Message
text, answers, prompts, responses, names, usernames, email addresses, and phone
numbers are not accepted as event properties. Analytics failure is non-fatal to
the learning workflow.

The protected admin console exposes a 30-day unique-user funnel:

1. `start_received`
2. `pilot_waitlist_joined`
3. `onboarding_started`
4. `onboarding_completed`
5. `block_started`
6. `block_completed`

Recent privacy-safe events can be exported as CSV. Acquisition source is
accepted only from a short ASCII Telegram `/start` payload.

The daily-lesson experience also records `lesson_started`, `card_shown`,
`card_revealed`, `card_audio_replayed`, `card_rated`, and `lesson_completed`.
Only allowlisted dimensions such as pack, language, lesson kind, position,
rating, and aggregate correctness are stored; word or message text is never
included.

## Rollout boundary

The product foundation leaves `BOT_ACCESS_MODE` unchanged. Migration `0005` and
the admin access controls prepare a later, separately approved rollout: deploy
in allowlist mode, verify Telegram readiness, then switch to `pilot` and admit
learners individually. `public` remains a separate product and operational
decision.
