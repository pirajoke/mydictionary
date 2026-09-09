# Custom vocabulary import v1

## Outcome

A learner can open **My words** in the Telegram Mini App, choose **Add my
words**, and finish the import in the bot using pasted text, a photo, a PDF, or
a voice note. Saved entries belong to the learner and the currently active
target/meaning language pair. The learner can then choose **Practice my words**
to study only those entries.

## Acceptance criteria

1. The Mini App words view exposes two prominent actions: add custom words and
   practice custom words. Bootstrap deep links are allowlisted and route to real
   bot handlers.
2. Pasted text works without AI when each line contains a target word and a
   translation. Separators `-`, `—`, `:`, `;`, and tab are accepted. Empty
   lines, duplicates, and unsafe/oversized values are rejected or normalized.
3. A target-only paste, a supported photo, or a PDF is extracted/enriched into
   at most 40 entries by the configured OpenAI Responses provider with strict
   structured output, `store=False`, the existing consent gate, and the
   existing metered credit/budget lifecycle. The original binary is not stored.
4. A voice note received while import mode is active is transcribed through the
   existing consented voice service and then parsed/enriched. The original audio
   and transcript are not stored after the bounded preview is created.
5. Every import shows a bounded preview containing target, translation, and
   transcription. Nothing is persisted until the learner confirms **Save**;
   **Cancel** discards the preview.
6. Persistence is scoped by Telegram user id and active language pair, dedupes
   normalized target terms, sorts entries predictably, enforces 500 entries per
   learner/language, and is removed by privacy erasure.
7. Custom-only practice selects due entries before unseen entries, never mixes
   catalog words, shows one card at a time, and stores know/don't-know SRS state.
8. Mini App bootstrap includes a privacy-safe, bounded custom-word list for the
   active language with translation, transcription, learned and due status.
9. Unsupported documents, files larger than 8 MiB, empty extraction results,
   stale previews, language changes, disabled AI/voice, missing consent, quota,
   and provider failures fail closed with useful localized messages and no
   partial save or charge for a failed AI response.

## Non-goals

- Raw file or audio retention.
- Editing PDF/image contents in the Mini App process.
- Mixing custom entries into the curated deterministic lesson packs.
- Background OCR without explicit learner action and consent.

## Quality gates

- Focused RED tests fail before implementation and pass after it.
- Full unit suite, compilation, migration upgrade/downgrade/upgrade, JavaScript
  syntax check, and `git diff --check` pass.
- A privacy-safe Mini App/browser smoke test covers both CTA deep links and the
  rendered custom list.
