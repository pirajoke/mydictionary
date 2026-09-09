# Personal vocabulary

The **My words** tab in the Telegram Mini App exposes two explicit actions:
**Add my words** and **Practice my words**. Both return to the authenticated bot
chat, where Telegram can accept text, photos, PDF files, and voice notes without
putting provider credentials into the Mini App process.

## Import flow

1. The learner starts an import for the currently active target and meaning
   language pair.
2. Lexi accepts one of:
   - one word or phrase per line, optionally followed by `-`, `—`, `:`, `;`, or
     a tab and its translation; bullets and numbered-list prefixes are removed;
   - a Telegram photo;
   - a PDF document;
   - a voice note within the existing voice limits.
3. A pasted list whose translations are complete is parsed deterministically
   and does not use an AI credit. Missing translations, photos, and PDFs use the
   existing consented AI path and one successful AI request credit. Voice first
   uses the existing consented transcription path and can then use one AI credit
   for structured vocabulary extraction.
4. Lexi returns a bounded preview with target terms, concise translations, and
   transcriptions where useful. Nothing is stored until the learner presses the
   confirmation button.
5. Confirmation upserts the words into the learner's personal dictionary.
   Cancelling, changing languages, or letting the preview expire saves nothing.

One import accepts at most 40 unique entries, pasted text is limited to 8,000
characters, and uploads are limited to 8 MiB. A learner can store at most 500
personal entries per target language. Duplicates update the existing entry for
the same learner and language pair.

## Practice

**Practice my words** creates a session containing only confirmed personal
entries for the active language pair. Due words are selected first, followed by
unseen words and then previously seen words. Each card reveals its translation
on demand, offers a native-pronunciation link, and records **I know** or **I
don't know yet** in the personal spaced-repetition state.

Personal entries remain separate from versioned starter packs. AI, voice, and
Telegram Stars can be disabled without breaking deterministic import of an
already translated text list or practice of previously saved words.

## Privacy and provider boundary

- Binary uploads and voice transcripts are held only long enough to create the
  preview and are not written to application storage.
- OpenAI extraction uses strict structured output and `store=false`; only
  technical usage metadata is retained in the existing metering ledger.
- Voice and AI processing use their existing independent versioned consent
  gates.
- The Mini App bootstrap returns at most 60 personal entries and only the
  target, meaning, transcription, learned, and due fields.
- `/privacy` deletes all personal vocabulary and its review state.
