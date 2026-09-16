# Mirror teacher continuity v1

## Objective

Turn Mirror into a continuous, structured language-teacher chat without making
AI a dependency of deterministic lessons. Learner answers should advance the
exercise instead of restarting it, catalog words used in the conversation
should become visible learning history, and a short recent-history view should
be available in the authenticated Mini App profile.

## Acceptance criteria

1. The Russian phrase `что я проходил` is handled as a deterministic progress
   request. The reply contains at most three clearly labelled sections and, when
   available, names recently practised terms.
2. A short learner answer after a prior learning challenge is classified as
   practice/correction, while an unrelated greeting remains general
   conversation.
3. Learning replies are rendered as concise teacher turns: result, explanation
   or example, and next action. Raw provider Markdown decoration is removed and
   no more than three application-owned section markers are shown.
4. Catalog terms mentioned by the learner or tutor are recorded as exposures in
   the existing word-progress namespace. Exposure updates `last_seen` and makes
   the term visible in My words, but does not increment correct answers, wrong
   answers, XP, or sessions.
5. The authenticated Mini App bootstrap exposes at most three complete recent
   Mirror exchanges only when AI consent is granted and Mirror memory is
   enabled. The history is rendered with `textContent` inside the existing
   collapsed More statistics block and remains hidden when empty.
6. The Mirror provider contract explicitly forbids reusing an example or task
   found in recent dialogue and advances after a correct answer.

## Edge cases

- Duplicate term matches are written only once per turn and exposure writes are
  bounded to twelve terms.
- Erased or blocked users cannot record word exposure.
- Expired or incomplete Mirror exchanges are not exposed by the read-only
  profile history query.
- Storage failures while recording exposure or dialogue history never suppress
  an otherwise successful chat reply and never log learner text.

## Error behavior

- Read-only profile bootstrap must not prune, migrate, or otherwise mutate
  dialogue rows.
- Missing history or a store without the optional read-only history capability
  yields an empty history list.

## Out of scope

- An immutable full chat transcript archive.
- Automatic correctness scoring or XP based solely on an LLM response.
- Redesigning ordinary greetings or replacing deterministic cards, quizzes,
  written practice, pronunciation, or spaced repetition.
