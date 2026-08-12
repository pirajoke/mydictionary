# Product polish: locale, compact admin, Groq voice, and economics

## Scope

This change starts from PR #45 and remains disabled/inert at runtime until a
separate production deployment and feature-flag approval. No real provider or
Telegram Stars calls are part of this cycle.

## Telegram locale contract

- AC-I18N-01: Normalize Telegram `language_code` values to `en`, `fr`, `de`,
  `ja`, `ar`, `zh`, `ru`, or `es`; normalize regional variants such as
  `zh-Hans` and fall back to English for missing or unsupported values.
- AC-I18N-02: `/start`, onboarding copy, onboarding buttons, completion copy,
  the primary start menu, and access-gate responses use the normalized locale.
- AC-I18N-03: Onboarding stores the normalized Telegram locale as the learner's
  native language, while the selected learning pack remains independent.
- AC-I18N-04: Free Mirror greetings and capability responses use the normalized
  locale for all eight launch languages.
- AC-I18N-05: Billable Mirror requests include a validated interface locale and
  an immutable instruction to answer in that language by default. Unsupported
  locale values fail closed before a provider attempt.
- EC-I18N-01: Existing Russian calls that omit locale keep Russian output where
  required for backwards-compatible tests and admin-owned personal flows.

## Compact admin contract

- AC-ADMIN-01: The persistent navigation exposes exactly six primary sections:
  Overview, Users, Product, AI & Voice, Payments, and Settings.
- AC-ADMIN-02: Every existing admin tab remains reachable through a contextual
  secondary navigation; no route or capability is removed.
- AC-ADMIN-03: At narrow widths the sidebar becomes a compact disclosure menu
  and the workspace occupies the full viewport without horizontal clipping.

## Groq transcription contract

- AC-GROQ-01: Voice practice accepts `VOICE_PROVIDER=groq`, requires
  `GROQ_API_KEY`, defaults to `whisper-large-v3`, and never requires the Groq
  key when voice is disabled.
- AC-GROQ-02: Voice translation may use Groq for STT while retaining OpenAI for
  the text translation stage; both credentials are independently validated.
- AC-GROQ-03: The Groq adapter uses the OpenAI-compatible transcription endpoint
  with `max_retries=0`, in-memory OGG input, bounded prompt/language fields, and
  normalized response telemetry.
- AC-GROQ-04: Existing consent, credit reservation, cost settlement, ephemeral
  audio, transcript retention, and failure recovery behavior is unchanged.
- AC-GROQ-05: Enabling Groq transcription requires an explicit
  `VOICE_GROQ_ZDR_VERIFIED=true` confirmation; otherwise startup fails closed
  before any provider request.
- ERR-GROQ-01: Unknown providers, missing provider credentials, empty output,
  oversized output, and malformed provider responses fail closed.

## Economics contract

- AC-ECON-01: The exact reviewed default-tier `gpt-5.6-luna` rates remain
  0.20 USD input, 0.02 cached input, 0.25 cache write, and 1.20 output per
  million tokens. Package pricing must not mislabel a different model or
  processing mode as the runtime rate.
- AC-ECON-02: One standard AI credit uses a conservative 6,000 micro-USD cost
  envelope in every package calculation.
- AC-ECON-03: The draft catalog is Mini 20/60 XTR, Start 50/100 XTR, Value
  150/250 XTR, and Monthly 100/180 XTR.
- AC-ECON-04: Nominal package contribution margin is at least 50%; stress margin
  is reported without being misrepresented as a guarantee.
- AC-ECON-05: The snapshot records Groq `whisper-large-v3` at 0.111 USD/hour,
  a 10-second minimum billable duration, and a 925 micro-USD ceiling for one
  allowed 30-second transcription.

## Out of scope

- Merge, production deployment, feature-flag changes, credential enrollment,
  live Groq/OpenAI calls, Telegram invoices, payments, refunds, and product
  activation.
- Translating the 800 stored Russian dictionary meanings into seven additional
  meaning languages.
