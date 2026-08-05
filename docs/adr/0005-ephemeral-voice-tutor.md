# ADR 0005: Ephemeral audio with text-level pronunciation feedback

Status: accepted

## Context

MY DICTIONARY needs voice input, block-scoped conversation practice, readable
transcripts, usage metering, and feedback across eight scripts. Raw voice is
high-risk personal data, while generic transcription output is not evidence of
phoneme-level pronunciation quality.

## Decision

Use Telegram OGG voice messages only in memory and send them to a provider-neutral
transcription interface. The initial adapter uses OpenAI's transcription API.
Persist the recognized text for a bounded period, but never persist raw audio.

Bind every voice session to stable vocabulary IDs from one active block. Support
two modes: individual pronunciation and guided example phrases. Use deterministic
text matching for `exact`, `close`, and `retry` feedback and state explicitly
that this is not acoustic scoring.

Use the existing AI wallet and usage table. Complete the usage row, credit ledger,
voice turn, and session position in one database transaction. Keep the entire
feature off by default and require an explicit provider cost estimate before it
can be enabled.

## Consequences

- Process restarts and concurrent Telegram updates cannot silently corrupt a
  learner's position or double-charge a completed turn.
- Privacy deletion and retention can remove transcripts independently of
  immutable financial records.
- Open-ended spoken tutoring and phoneme-level feedback are intentionally out of
  scope until separate safety, quality, and cost evaluations exist.
- Provider model and pricing changes are runtime configuration reviews, not
  hard-coded product assumptions.
