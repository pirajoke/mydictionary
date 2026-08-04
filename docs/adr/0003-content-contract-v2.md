# ADR 0003: Versioned Language-Neutral Content Contract

Status: accepted for Content Contract v2

## Context

The original dictionaries encode the target term as `en`, the Russian meaning
as `ru`, and pronunciation behavior in Python maps. That shape works for the
first English, Vietnamese, and Japanese files, but every additional language
would require application code changes. It also couples persisted learner
progress to mutable term and meaning text.

The product needs free basic packs for languages with Latin, CJK, Cyrillic, and
right-to-left writing systems. All packs need topics, readable transcription,
and a deterministic TTS voice without risking an accidental English fallback.

## Decision

- Use `content/catalog.json` schema version 2 as the source of truth for pack
  metadata and the shared topic taxonomy.
- Give every pack a target language, meaning language, writing direction,
  display flags, content schema/version, visibility, and pronunciation policy.
- Normalize every entry at startup to `target`, `meaning`, `transcription`,
  `speech`, `topics`, and optional bilingual examples.
- Require schema-v2 entries to have a stable `entry_id`. New progress identity
  is derived from `pack_id + entry_id`, not editable display text.
- Allow `legacy_progress_id` only as a migration bridge for a previously
  published entry. It is a content identity, not learner state.
- Continue accepting checked-in schema-v1 files through a strict adapter. The
  adapter reproduces the historical SHA-256 identity from `en + ru`, preserving
  all existing database progress without a data migration.
- Reject unknown fields, duplicate identities, undeclared topics, unsafe paths,
  non-NFC text, control/format characters, invalid callback lengths, and missing
  transcription or TTS metadata at startup.
- Pass an explicit voice, rate, and pack-version cache namespace to TTS. Missing
  configuration fails closed and never falls back to another language.
- Generate bidi isolation in the rendering layer for RTL target text. Direction
  controls are forbidden inside content files.

## Entry Contract

```json
{
  "schema_version": 2,
  "entries": [
    {
      "entry_id": "hello",
      "target": "مرحبا",
      "meaning": "привет",
      "transcription": "marhaban",
      "speech": "مَرْحَبًا",
      "topics": ["greetings"],
      "example": {
        "target": "مرحبا يا صديقي",
        "meaning": "привет, мой друг"
      }
    }
  ]
}
```

`example` may be `null`. `transcription` may be empty only when the pack declares
`transcription_system: none` and `transcription_position: hidden`. `speech` is
the exact text sent to the configured TTS voice and may differ from the display
form. Topics must exist in the catalog taxonomy.

## Migration Rules

1. Keep a published pack's `pack_id`, `storage_key`, and entry identity stable.
2. Before converting a schema-v1 entry, calculate its historical progress ID
   from the exact trimmed legacy `en` and `ru` strings.
3. Add that digest as `legacy_progress_id` to the schema-v2 entry.
4. Assign a durable semantic `entry_id`; never reuse it for a different concept.
5. Increase `content_version` whenever display, speech, transcription, topic, or
   example content changes. Increase `content_schema` only for structural
   contract changes.
6. Run the contract suite and verify that all migrated progress IDs match before
   publishing the pack.

## Consequences

- A new language pack can be added as catalog data without editing bot, admin,
  quiz, block, topic, Forvo, AI-context, or TTS routing code.
- Text corrections no longer reset progress for native schema-v2 entries.
- Existing learners retain progress while the three original files remain on
  the schema-v1 adapter and during a later explicit migration.
- The strict loader intentionally stops startup for malformed checked-in
  content; content publication therefore requires the deterministic test suite.
- Catalog metadata and parser validation evolve together and remain code-reviewed.

## Rejected Options

- Keep language-specific Python dictionaries: this scales linearly with every
  language and keeps behavior fragmented.
- Infer TTS voices from language codes: locale and preferred voice are product
  choices, and a fallback can pronounce content in the wrong language.
- Use array position or term text as the new identity: ordering and wording are
  editorial details and must not reset learner history.
- Put bidi control characters in content: invisible controls are difficult to
  audit and can alter surrounding Telegram text.
