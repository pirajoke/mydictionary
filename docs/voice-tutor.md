# Voice tutor and guided conversation

Stage 6 adds paid voice practice over the learner's active block. The feature is
off by default and does not make an OpenAI request until an operator separately
enables it with complete pricing and credential settings.

## Learner flows

`/voice` starts pronunciation practice for the words in the active ten-word
block. Each turn is presented in this order:

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
- OpenAI receives only the audio, ISO language code, and a prompt containing the
  active block's public vocabulary.
- The transcript is limited to 1,000 characters and expires after 30 days by
  default.
- Admin metrics show status, similarity, content IDs, and retention deadlines,
  but never show transcript text or audio.
- Each STT request uses the existing AI wallet. Reservation, usage settlement,
  transcript creation, and session advancement commit atomically.
- Provider failure or a stale session releases the reserved credit.

## Runtime settings

| Setting | Default | Requirement when enabled |
|---|---:|---|
| `VOICE_TUTOR_ENABLED` | `false` | explicit `true` |
| `VOICE_PROVIDER` | `openai` | only `openai` is accepted |
| `VOICE_TRANSCRIPTION_MODEL` | `gpt-4o-transcribe` | reviewed supported model |
| `OPENAI_API_KEY` | unset | required |
| `VOICE_CREDITS_PER_REQUEST` | `1` | 1-100 |
| `VOICE_COST_MICRO_USD_PER_MINUTE` | `0` | current non-zero operator estimate |
| `VOICE_MAX_AUDIO_BYTES` | `8388608` | 1 KiB-20 MiB |
| `VOICE_MAX_DURATION_SECONDS` | `30` | 2-120 seconds |
| `VOICE_SESSION_TTL_MINUTES` | `30` | 5-240 minutes |
| `VOICE_TRANSCRIPT_RETENTION_DAYS` | `30` | 1-365 days |

`VOICE_COST_MICRO_USD_PER_MINUTE` is an operational cost estimate in millionths
of one US dollar. It must be reviewed against the current provider price before
activation; the repository intentionally does not hard-code a time-sensitive
price.

The OpenAI adapter follows the official transcription endpoint and sends an OGG
file tuple in memory:

- https://platform.openai.com/docs/api-reference/audio/createTranscription
- https://platform.openai.com/docs/guides/speech-to-text

## Activation gate

Before production activation, operators must review model availability and
price, set wallet and Stars margins, run a restore-safe migration backup, test
all eight languages with consented pilot speakers, verify deletion and retention
jobs, and observe cost/error metrics in the admin console. Deployment and flag
activation are separate actions and are not performed by this stage.
