# AI Tutor question starters v1

## Goal

The general AI Tutor entry must feel like a conversation, not a dead-end prompt.
After the learner chooses “Ask Tutor”, the bot explains that free-form questions
are welcome and offers concrete one-tap examples.

## Acceptance criteria

- **AC-1** — `aitutor:ask` keeps the existing ten-minute free-form pending state
  and renders one localized instruction saying that the learner may chat freely
  with the Tutor.
- **AC-2** — The same message offers three localized, privacy-safe starter
  buttons: a short summary of today, what to review next, and a short quiz.
- **AC-3** — Each starter callback runs the ordinary grounded Tutor path exactly
  once using a bounded localized question. It does not start a lesson, buy
  credits directly, or call a separate provider path.
- **AC-4** — The “today” starter explicitly asks for a short summary and requires
  missing data to be acknowledged rather than invented.
- **AC-5** — Unknown or malformed Tutor callbacks fail closed and never invoke
  the Tutor.
- **AC-6** — Copy and callback behavior are complete for every supported
  interface locale.

## Out of scope

- Changing lesson flow, credit pricing, or billing.
- Voice-message support changes.
- Automatic purchases or external actions.
