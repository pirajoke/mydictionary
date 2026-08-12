# Voice tutor and guided conversation

Stage 6 adds paid voice practice over the learner's active block. The feature is
off by default and does not contact a provider until an operator separately
enables it with complete pricing, consent, and credential settings.

## Learner flows

`/voice` opens one selector for pronunciation practice, guided phrases, and
completed-voice-note translation. Pronunciation practice uses the words in the
active ten-word block. Before the first session for the current notice version, the learner must
accept that Telegram audio will be sent to the configured STT provider. The bot
checks that consent again before downloading each voice message. Each turn is
presented in this order:

1. Russian meaning;
2. target-language word;
3. Latin transcription;
4. reference TTS audio;
5. learner voice message;
6. recognized text and feedback;
7. reference TTS audio again.

`/conversation` uses the same block but asks the learner to speak the example
phrases. The Russian phrase is shown first, followed by the target phrase, the
focus word with its Latin transcription, and phrase TTS. This is a bounded,
guided conversation mode, not an open-ended assistant: it cannot leave the
selected content pack or invent a new curriculum.

`/voice_stop` stops the current session. `/voice_transcript` shows the latest
session's recognized text until its retention deadline.

The active session is persisted, so a process restart does not silently move a
learner to another word. Starting a new voice mode cancels the previous active
session. A concurrent duplicate voice message may be transcribed, but only one
request can atomically advance the session; the other reservation is released.

## Feedback contract

The service compares normalized STT text with the expected word, reading, Latin
transcription, or phrase and returns one of `exact`, `close`, or `retry`. It may
also identify another word from the same block when that is what STT recognized.

This is not an acoustic pronunciation score. It does not claim to measure
accent, phoneme quality, intonation, or fluency. Specialized acoustic scoring
would require a separately evaluated provider and a new product contract.

## Privacy and metering

- Telegram voice metadata is checked before download.
- The downloaded OGG payload stays in memory and is never written to disk or a
  database.
- The selected STT provider receives only the audio, ISO language code, and a
  prompt containing the active block's public vocabulary.
- The transcript is limited to 1,000 characters and expires after 30 days by
  default.
- Admin metrics show status, similarity, content IDs, and retention deadlines,
  but never show transcript text or audio.
- Each STT request uses the existing AI wallet. Reservation, usage settlement,
  transcript creation, and session advancement commit atomically.
- Provider failure or a stale session releases the reserved credit.
- `/privacy` can revoke voice processing consent and stop the active session.
- Changing `VOICE_CONSENT_VERSION` requires a new acceptance.

## Runtime settings

| Setting | Default | Requirement when enabled |
|---|---:|---|
| `VOICE_TUTOR_ENABLED` | `false` | explicit `true` |
| `VOICE_PROVIDER` | `openai` | `openai` or `groq` |
| `VOICE_TRANSCRIPTION_MODEL` | provider default | `gpt-4o-transcribe` for OpenAI; `whisper-large-v3` for Groq |
| `OPENAI_API_KEY` | unset | required for OpenAI STT and for text translation |
| `GROQ_API_KEY` | unset | required when the STT provider is `groq` |
| `VOICE_GROQ_ZDR_VERIFIED` | `false` | explicit `true` after Zero Data Retention is verified for Groq |
| `VOICE_MINIMUM_BILLABLE_SECONDS` | provider default | `10` for Groq, `0` for OpenAI |
| `VOICE_CREDITS_PER_REQUEST` | `1` | 1-100 |
| `VOICE_COST_MICRO_USD_PER_MINUTE` | `0` | current non-zero operator estimate |
| `VOICE_MAX_AUDIO_BYTES` | `8388608` | 1 KiB-20 MiB |
| `VOICE_MAX_DURATION_SECONDS` | `30` | 2-120 seconds |
| `VOICE_SESSION_TTL_MINUTES` | `30` | 5-240 minutes |
| `VOICE_TRANSCRIPT_RETENTION_DAYS` | `30` | 1-365 days |
| `VOICE_CONSENT_VERSION` | unset | reviewed immutable version identifier |
| `VOICE_PROCESSING_NOTICE` | unset | reviewed disclosure, 40-1000 characters |

`VOICE_COST_MICRO_USD_PER_MINUTE` is an operational cost estimate in millionths
of one US dollar. The checked-in economics snapshot records the reviewed Groq
candidate rate and ten-second minimum; runtime activation still requires a
current reviewed snapshot.

The OpenAI adapter follows the official transcription endpoint and sends an OGG
file tuple in memory:

- https://platform.openai.com/docs/api-reference/audio/createTranscription
- https://platform.openai.com/docs/guides/speech-to-text

The Groq adapter uses the OpenAI-compatible transcription endpoint with
`max_retries=0`; one application request therefore makes at most one provider
attempt:

- https://console.groq.com/docs/speech-to-text
- https://groq.com/pricing

Voice-note translation can use Groq for STT and OpenAI for structured text
translation. The two provider operations keep separate reservations and
metering records. Their keys are never interchangeable.

## Activation gate

Before production activation, operators must review model availability and
price, set wallet and Stars margins, run a restore-safe migration backup, test
all eight languages with consented pilot speakers, verify deletion and retention
jobs, and observe cost/error metrics in the admin console. Deployment and flag
activation are separate actions and are not performed by this stage.
