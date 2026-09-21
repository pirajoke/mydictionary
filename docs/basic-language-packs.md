# Eight basic language packs

MY DICTIONARY ships free 500-entry starter packs for English, French, German,
Japanese, Arabic, Chinese, Russian, and Spanish. The existing Vietnamese pack
remains available as an additional free pack.

## Content contract

- Every pack provides a target form, a Russian meaning, a Latin transcription,
  a speech form, and at least one learning topic.
- The seven new schema v2 packs share stable entry IDs and the same ten topics,
  with 50 entries in each topic.
- Russian uses short Russian definitions as meanings so target and meaning are
  not duplicates.
- IPA is used for English, French, German, and Spanish. Chinese uses pinyin;
  Japanese uses Hepburn romaji; Arabic and Russian use learner-oriented Latin
  transcription.
- Speech synthesis uses the locale, voice, and rate declared by each pack in
  `content/catalog.json`. Content generation never contacts a TTS service.

## Source and generation

`content/basic_100.tsv` is the aligned source of truth for the seven schema v2
packs. Its legacy filename is retained because deployment allowlists and older
automation refer to it. The first 100 rows are the original project matrix;
the 400-row extension was curated from the openly available
[`appsinacup/polyglot-dictionaries`](https://github.com/appsinacup/polyglot-dictionaries)
1000-word lists at commit `0375cbb7117c8833b8d69da5e8c60a052bab0b28`, then
reviewed and aligned to one everyday sense per entry. That repository is MIT
licensed and identifies Wiktionary as the source of its translations;
Wiktionary-derived content remains subject to Wiktionary attribution and
CC BY-SA terms.

English, French, German, and Spanish IPA was drawn from
[`open-dict-data/ipa-dict`](https://github.com/open-dict-data/ipa-dict) at
commit `43c3570eb3553bdd19fccd2bd0091534889af023`. Missing headwords were checked
against Wiktionary-derived WiktAPI data, and a small number of multiword forms
were composed from the same word-level IPA. `ipa-dict` is MIT unless a credited
upstream dataset states another license; notably its German data is
Wiktionary-derived CC BY-SA. Pinyin and Hepburn readings were generated with
`pypinyin` 0.55.0 and `pykakasi` 2.3.0 respectively. The reviewed, normalized
outputs are checked into this repository; builds do not fetch these services or
packages.

The historical pack IDs such as `en-basics-100`, the storage keys, and the
source filename are intentionally unchanged. They are persistence identities,
not counts: changing them would split existing learner progress. Catalog labels
and `entry_count` are the authoritative UI metadata and now report 500.

Run the deterministic generator after changing it:

```sh
python3 scripts/build_basic_packs.py
python3 scripts/build_basic_packs.py --check
```

The second command is suitable for CI and fails if a generated JSON file is
missing or differs from the source matrix.

The Japanese pack intentionally stays on the schema v1 compatibility adapter.
Its original first 100 entries and order are unchanged; 400 reviewed entries
were appended with kana reading, ASCII Hepburn romaji and topic metadata. This
preserves existing example sentences and historical learner progress identities
while exposing canonical target, meaning, romaji, topics, and speech fields to
the bot.
