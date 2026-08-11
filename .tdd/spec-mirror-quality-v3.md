# Mirror Quality v3 - locked specification

## Outcome

Make free-text Mirror replies feel like a context-aware language conversation,
while preserving deterministic learning, AI metering, safety gates, privacy
erasure, and the seven-command Telegram menu.

## Acceptance criteria

- AC-01 Natural answer: a plain conversational answer renders as ordinary
  Russian text without mandatory section labels, flag prefixes, or an AI-credit
  footer.
- AC-02 Adaptive language detail: target writing, Latin transcription, Russian
  meanings, examples, and a next step render only when the provider supplied
  them. Ambiguous meanings remain visible.
- AC-03 Style modes: every learner has one isolated persistent Mirror style:
  `teacher` (default), `conversation`, `brief`, or `practice`. Invalid values
  fail closed.
- AC-04 Context contract: the provider payload includes the selected style and
  no more than the latest 20 validated dialogue turns. The current question is
  separate from prior dialogue.
- AC-05 Durable memory: when `MIRROR_MEMORY_ENABLED=true`, a successful metered
  exchange is stored for seven days by default and becomes available after a
  process restart. Only the latest 20 unexpired turns are returned.
- AC-06 Memory gate: durable dialogue storage is off by default. Enabling it
  requires a configured current AI consent version; otherwise startup/config
  validation fails. A storage failure must not hide an already generated answer.
- AC-07 Data lifecycle: retention preview/execution includes expired Mirror
  turns, and `/privacy` erasure physically deletes all Mirror turns and resets
  the stored style.
- AC-08 Telegram UX: style selection is available through existing Settings
  callbacks and does not add a public command.
- AC-09 Learning quality: Russian remains first; the eight launch languages
  retain target writing and readable Latin transcription when language details
  are present.
- AC-10 Safety/economics: no new provider attempt, retry, credit path, payment,
  Voice, Stars, or production feature activation is introduced.

## Edge and error cases

- EC-01 Expired turns and turns owned by another learner never enter context.
- EC-02 Dialogue text is trimmed, empty turns and unknown roles are rejected,
  and oversized turns are bounded before storage/provider input.
- EC-03 Erased learners cannot change style or append dialogue.
- ERR-01 Invalid memory booleans or retention outside 1-30 days fail closed.
- ERR-02 Invalid provider response structure remains rejected by the existing
  settlement path.

## Out of scope

- Real AI calls, prompt experimentation against production users, merge,
  deployment, feature-flag changes, Voice, Stars, and payments.
- Copying Zerkalo's psychological-support domain, personal questionnaire, or
  private user data.
