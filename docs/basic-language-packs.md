# Eight basic language packs

MY DICTIONARY ships free 100-entry starter packs for English, French, German,
Japanese, Arabic, Chinese, Russian, and Spanish. The existing Vietnamese pack
remains available as an additional free pack.

## Content contract

- Every pack provides a target form, a Russian meaning, a Latin transcription,
  a speech form, and at least one learning topic.
- The seven new schema v2 packs share stable entry IDs and the same ten topics,
  with ten entries in each topic.
- Russian uses short Russian definitions as meanings so target and meaning are
  not duplicates.
- IPA is used for English, French, German, and Spanish. Chinese uses pinyin;
  Japanese uses Hepburn romaji; Arabic and Russian use learner-oriented Latin
  transcription.
- Speech synthesis uses the locale, voice, and rate declared by each pack in
  `content/catalog.json`. Content generation never contacts a TTS service.

## Source and generation

`content/basic_100.tsv` is the aligned source of truth for the seven new packs.
Its vocabulary matrix is original project content rather than a copied export
from a third-party learning service.
Run the deterministic generator after changing it:

```sh
python3 scripts/build_basic_packs.py
python3 scripts/build_basic_packs.py --check
```

The second command is suitable for CI and fails if a generated JSON file is
missing or differs from the source matrix.

The Japanese pack intentionally stays on the schema v1 compatibility adapter.
This preserves its existing example sentences and historical learner progress
identities while still exposing canonical target, meaning, romaji, topics, and
speech fields to the bot.
