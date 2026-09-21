# AI chat interactive quiz — locked behavior

## Scope

Turn the existing AI-tutor “quick quiz” affordance into a native Telegram quiz
while keeping ordinary AI conversation free-form. The quiz reuses the canonical
catalog, SRS progress, XP and durable native block machinery; it must not depend
on a successful AI provider call.

## Acceptance criteria

- **AC-1 — Native entry:** `aitutor:quiz` starts a five-question native Telegram
  quiz immediately and does not ask the provider to emit a text-only question.
- **AC-2 — Natural request:** reviewed, explicit requests such as “давай тест”,
  “quiz me”, and their supported-interface-language equivalents route to the same
  native quiz. Ordinary learning questions remain in AI chat.
- **AC-3 — Grounded selection:** the test uses up to five canonical words,
  preferring the active block, then due reviews, then the normal SRS picker.
- **AC-4 — Varied interaction:** questions alternate between target word → meaning
  and meaning → target word. Every question has four session-bound answer buttons.
- **AC-5 — Immediate feedback:** an accepted answer removes the old buttons,
  displays ✅/❌ plus the correct word details, and advances once.
- **AC-6 — Result card:** an AI-chat quiz ends with score `N/total`, one ✅/❌ row
  for every tested word, its correct pairing, and actions to retry mistakes, start
  a fresh test, or continue talking to Lexi.
- **AC-7 — Durable progress:** answers continue through the existing native block
  persistence/SRS/XP path; the feature introduces no parallel learner record.
- **AC-8 — Conversational variety:** when Lexi offers a typed practice step, it
  selects a form that fits the dialogue (short conversation, choice, cloze,
  ordering, correction, or free response) and does not repeat the immediately
  preceding exercise form or wording.

## Edge and error cases

- **EC-1:** fewer than five available words produces the largest non-empty unique
  set; zero available words returns the existing localized no-words message.
- **EC-2:** RTL target terms keep the catalog’s directional isolation.
- **ERR-1:** malformed, stale, repeated, or non-current answer callbacks retain the
  existing fail-closed behavior and cannot advance or score twice.
- **ERR-2:** when AI is disabled or unavailable, already-started native quizzes
  remain usable because scoring is deterministic.

## Out of scope

- AI-generated factual quiz content outside the canonical vocabulary catalog.
- Mini App changes.
- New database tables or migrations.
