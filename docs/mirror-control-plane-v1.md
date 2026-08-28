# Mirror Control Plane v1

Mirror Control Plane v1 adds a versioned teaching policy, richer grounded
answers, privacy-safe quality analytics, and a completed-voice-note translation
flow. The release is scaffolding-first: migrations and UI do not enable durable
memory, voice providers, Telegram Stars, or payments.

## Learner controls

The existing settings screen exposes only communication modes enabled by the
current admin policy:

- `teacher`: direct explanation with relevant language detail;
- `conversation`: natural continuation with contextual correction;
- `coach`: evidence, interpretation, and one next step;
- `practice`: one bounded exercise after the answer;
- `brief`: compact answer without optional examples;
- `exam`: one skill check at a time without early hints.

Answer depth is `compact`, `balanced`, or `deep`. Learner level is `adaptive`
or CEFR `A1` through `C1`. These values are stored per learner and are erased
with learning data. They do not alter the immutable safety envelope.

The admin profile tab can enable modes, select defaults, edit bounded guidance,
and restore a previous snapshot. Every update creates a new immutable snapshot.
Audit records contain changed field names and hashes, never guidance text.

## Grounding and quality

Natural progress questions use the same metered AI path as other Mirror
questions. The provider receives a bounded snapshot with lifetime accuracy,
tracked and learned words, due reviews, weak terms, seven-day activity, and
streak. A trend is marked unavailable until a real historical series exists.
Provider or metering failure falls back to the deterministic `/stats` summary.

The structured response contract separates the direct answer, evidence,
interpretation, language examples, and next step. Quality telemetry stores only
request ID, teaching dimensions, lengths, counts, and a deterministic contract
score. Helpful/not-helpful feedback is idempotent and owner-checked. No learner
question, generated answer, transcript, username, or credential is stored in
quality analytics.

## Voice modes

`/voice` presents pronunciation, guided phrases, and voice translation in one
menu. An active pronunciation or guided-phrase session has precedence over the
translation entry state.

Voice translation processes a completed Telegram voice note, not a live audio
stream. Russian speech routes to the active learning language; other detected
languages route to Russian. STT and translation reserve and settle credits as
separate operations. If STT succeeds and translation fails, the learner still
receives the transcript with an explicit partial-result notice. Raw audio,
transcript text, and translated text are absent from usage telemetry.

Translation has an independent consent type and version. Existing
`voice_processing` consent does not authorize translation.

## Disabled-by-default settings

| Setting | Default | Activation requirement |
|---|---:|---|
| `MIRROR_MEMORY_ENABLED` | `false` | history-specific AI notice/version and retention review |
| `VOICE_TUTOR_ENABLED` | `false` | reviewed STT model, price, notice, and pilot evaluation |
| `VOICE_TRANSLATION_ENABLED` | `false` | provider key, distinct consent, current positive STT/input/output prices |
| `TELEGRAM_STARS_ENABLED` | `false` | separate billing gate and approved commercial terms |

Voice translation additionally requires:

- `VOICE_TRANSLATION_MODEL`;
- `VOICE_TRANSLATION_CONSENT_VERSION`;
- `VOICE_TRANSLATION_PROCESSING_NOTICE`;
- `VOICE_TRANSLATION_STT_MICRO_USD_PER_MINUTE`;
- `VOICE_TRANSLATION_INPUT_USD_PER_MILLION`;
- `VOICE_TRANSLATION_OUTPUT_USD_PER_MILLION`;
- `VOICE_TRANSLATION_PRICING_REVIEWED_ON`;
- bounded duration, byte, and preflight-cost limits.

The reviewed provider, models, tier, and three rates form a hashed economics
snapshot stored with both reservations. Text AI is controlled by the credit
wallet and has no per-user daily request cap; project day/month/in-flight
budgets still bound provider exposure. Voice translation retains the separate
`VOICE_TRANSLATION_MAX_DAILY_REQUESTS_PER_USER=5` limit. Every provider attempt
is recorded before execution; every returned billable response is persisted
before content validation. A telemetry storage failure opens the shared breaker
and writes only provider identity, usage, cost, latency, and error code to the
existing metering journal.

Do not activate any flag as part of a code deployment. Production migration,
feature activation, live AI evaluation, and Stars testing remain separate
operational stages.
