# Native onboarding funnel v1

## User problem

After the first Telegram greeting, a new learner does not understand what to do
next. The product must guide the learner through a short, button-only setup,
save the answers for that Telegram user, and deliver the learner directly into
the first vocabulary lesson.

## Locked scope

The onboarding is a five-step native Telegram inline-button flow:

1. Choose the language in which Lexi explains and communicates.
2. Choose the language to learn.
3. Choose the learning goal.
4. Choose the preferred learning format.
5. Choose a daily pace.

The completion screen summarizes the choices and exposes one primary action:
`▶️ Start the first lesson`. It must use the existing daily-lesson path.

All selected values are persisted by `telegram_user_id` in the existing
database. No schema migration is required:

- explanation/interface language -> `native_language` and interface locale;
- target language -> active content pack;
- goal -> `learning_goal`;
- preferred format -> existing Mirror preference `mode`;
- pace -> `daily_word_goal`;
- completion -> `onboarding_completed_at`.

## Acceptance criteria

### AC-1 — Short first screen with clear action

For an active new learner, `/start` shows a concise localized Lexi greeting
that says setup takes about a minute and immediately offers one inline button
to choose a language. The button callback is `onboarding:begin`.

### AC-2 — Explanation language

Clicking `onboarding:begin` shows `Step 1 of 5` and localized explanation-
language buttons. Choosing `onboarding:native:<locale>` persists both the
native language and interface locale for the current Telegram user and moves
to `Step 2 of 5`.

### AC-3 — Target language

Choosing `onboarding:pack:<pack_id>` validates compatibility, activates the
learner-visible pack for the current Telegram user, records the pack event,
and moves to `Step 3 of 5` instead of jumping directly to pace.

### AC-4 — Learning goal

Step 3 offers exactly these semantic goals through native buttons:

- `basics` — start from the basics;
- `travel` — travel;
- `conversation` — conversation;
- `work` — work and study.

Choosing `onboarding:goal:<goal>` persists the exact `learning_goal`, records
`onboarding_goal_selected`, and moves to `Step 4 of 5`.

### AC-5 — Preferred format

Step 4 offers three formats through native buttons:

- `practice` — cards and practice;
- `conversation` — more dialogue;
- `teacher` — explanations from a teacher.

Choosing `onboarding:preference:<mode>` persists the existing per-user Mirror
preference with balanced depth and adaptive level, records
`onboarding_preference_selected`, and moves to `Step 5 of 5`.

### AC-6 — Pace and personalized completion

Choosing pace `5`, `10`, or `20` persists `daily_word_goal`, marks onboarding
complete, and edits the existing onboarding message to a concise localized
summary containing the selected target language, goal, format, and pace.
It must not send the old long greeting again.

The completion keyboard contains one primary inline button with callback
`start:daily` and a localized label equivalent to `▶️ Start the first lesson`.

### AC-7 — Direct lesson handoff

Clicking the final `start:daily` button uses the existing start-menu callback
and immediately enters the normal daily lesson flow. No duplicate onboarding
or extra navigation screen is inserted.

### AC-8 — Durable per-user state

The flow continues to work after in-memory `context.user_data` is empty by
reading the active pack and profile values from the database. Two Telegram
user IDs must retain independent onboarding answers.

### AC-9 — Localized native UX

All new visible strings and button labels exist for every supported interface
locale and preserve placeholder parity. The Russian flow uses natural,
compact copy. Callback data stays within Telegram's 64-byte limit.

## Edge cases

- Unsupported native language, private/incompatible pack, unknown goal,
  unknown preference, and invalid pace do not complete onboarding.
- A pace callback without a valid active learner pack asks the learner to
  choose a language again.
- Photo-based onboarding always edits the caption; legacy text onboarding
  always edits message text.
- Admins and learners who already completed onboarding keep their current
  behavior.

## Error expectations

- Persistence failures propagate to the existing error handler; onboarding is
  never marked complete before all profile choices have been stored.
- The welcome image remains optional: if Telegram cannot send it, the same
  funnel is available as text with the same button.

## Non-goals

- Redesigning the Mini App.
- Adding new curriculum packs or dynamically generating vocabulary with AI.
- Re-running onboarding automatically for existing completed learners.
- Changing AI, Voice, billing, Telegram Stars, or access-control behavior.

## Regression boundaries

- Deterministic lessons, quizzes, pronunciation, and spaced repetition remain
  available without AI.
- Existing persistent reply keyboard and `/continue`, `/review`, `/learn`,
  `/stats`, `/dictionary`, `/ai`, `/app`, `/invite`, `/privacy`, and `/help`
  commands remain unchanged.
- Existing catalog visibility and language-pair compatibility rules remain the
  source of truth.
