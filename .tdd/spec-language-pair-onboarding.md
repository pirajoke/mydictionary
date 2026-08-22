# Language-pair onboarding and learner-facing meanings

## Scope

Separate the Telegram interface locale from the dictionary translation pair.
The interface follows Telegram's phone language; onboarding explicitly chooses
the language used for meanings and then the language being learned. Existing
profiles and progress remain valid and require no database migration.

## Acceptance criteria

- AC-LANG-01: `/start` and onboarding questions use the normalized Telegram
  `language_code`. A supported regional code is normalized to its base locale;
  an unsupported non-empty code falls back to English.
- AC-LANG-02: `onboarding:begin` asks which language should be used for word
  meanings and does not silently persist the interface locale as that choice.
  When the detected interface locale is supported as a curated meaning
  language, its option is shown first as the recommendation.
- AC-LANG-03: Selecting `onboarding:native:<language>` persists the meaning
  language and then asks which language the learner wants to study.
- AC-LANG-04: The learning-language keyboard contains only published public
  packs with a complete curated mapping to the selected meaning language and
  excludes a same-language pair.
- AC-LANG-05: Selecting a compatible learning pack and a daily pace completes
  onboarding while preserving the selected meaning language and active target
  pack.
- AC-LANG-06: For an existing `fr` meaning-language profile learning `en`, the
  revealed English `kitchen` card displays `🇫🇷 cuisine` and never the
  canonical Russian `🇷🇺 кухня`. Interface copy continues to follow the
  Telegram locale independently.
- AC-LANG-07: Core learner-visible flashcard, multiple-choice, and typed-answer
  meanings use the selected curated pair consistently. Russian remains the
  canonical storage language and progress IDs are unchanged.

## Edge and error criteria

- EC-LANG-01: Selecting Russian as the meaning language preserves every current
  public target pack, including legacy Japanese and Vietnamese packs, while
  excluding the same-language Russian target.
- EC-LANG-02: Existing completed users are not sent through onboarding again;
  their stored `native_language` and active pack take effect immediately.
- ERR-LANG-01: An unknown meaning language or a forged/incompatible pack
  callback is rejected with localized unavailable/stale copy and does not
  activate the pack or complete onboarding.
- ERR-LANG-02: An explicitly selected non-Russian pair never silently falls
  back to a Russian meaning when a curated mapping is missing.

## Compatibility

- Previously sent `onboarding:native:ru` buttons remain valid.
- No database schema change and no rewrite of vocabulary/progress identities.
- Russian defaults remain available for legacy direct helper calls outside a
  bound learner runtime.

## Out of scope

- Runtime or AI-generated translation.
- Japanese or Vietnamese as meaning languages until a complete curated aligned
  matrix is supplied.
- Replacing the legacy Japanese/Vietnamese target packs or resetting progress.
- Translating target-language example sentences when no curated aligned example
  exists; in that case only the target example is shown.

## Allowed implementation files

- `bot.py`
- `mydictionary/catalog.py`
- `mydictionary/localization.py`
- `tests/test_language_pair_onboarding.py`
- `tests/test_onboarding.py`
- `tests/test_interface_localization.py`

## Verification

- Targeted language-pair and onboarding tests.
- All affected learning/localization/catalog tests.
- Full unit-test suite.
- Linux container tests before deployment.
- Live Telegram identity, single-worker, health, log, and rendered pair checks.
