from decimal import Decimal
import tempfile
import unittest
from unittest.mock import AsyncMock, MagicMock

from sqlalchemy import func, select

from mydictionary.ai_tutor import ProviderUsage
from mydictionary.storage import AIUsage, DatabaseStore, VoiceTurn
from mydictionary.voice_tutor import (
    OpenAITranscriptionProvider,
    TranscriptionResult,
    VoiceConfigurationError,
    VoiceProviderError,
    VoiceTutorService,
    VoiceTutorSettings,
    VoiceWord,
    evaluate_transcript,
)


class FakeProvider:
    def __init__(self, results):
        self.results = list(results)
        self.requests = []

    async def transcribe(self, request):
        self.requests.append(request)
        result = self.results.pop(0)
        if isinstance(result, BaseException):
            raise result
        return result


def settings(**overrides):
    values = {
        "enabled": True,
        "provider": "openai",
        "model": "gpt-4o-transcribe",
        "openai_api_key": "test-key",
        "credits_per_request": 1,
        "initial_credits": 5,
        "reservation_timeout_seconds": 300,
        "max_audio_bytes": 1024 * 1024,
        "max_duration_seconds": 30,
        "session_ttl_minutes": 30,
        "transcript_retention_days": 30,
        "cost_micro_usd_per_minute": Decimal("6000"),
    }
    values.update(overrides)
    return VoiceTutorSettings(**values)


WORDS = (
    VoiceWord("a" * 64, "週", "しゅう", "shuu", "неделя"),
    VoiceWord("b" * 64, "本", "ほん", "hon", "книга"),
)


class VoiceFeedbackTest(unittest.TestCase):
    def test_reading_variant_matches_without_claiming_acoustic_quality(self):
        feedback = evaluate_transcript("しゅう", expected=WORDS[0], words=WORDS)

        self.assertEqual(feedback.code, "exact")
        self.assertEqual(feedback.matched, WORDS[0])
        self.assertEqual(feedback.similarity_bps, 10000)

    def test_another_block_word_is_identified_but_expected_word_is_retry(self):
        feedback = evaluate_transcript("ほん", expected=WORDS[0], words=WORDS)

        self.assertEqual(feedback.code, "retry")
        self.assertEqual(feedback.matched, WORDS[1])


class VoiceTutorServiceTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="mydictionary-voice-")
        self.store = DatabaseStore(
            f"sqlite:///{self.temporary.name}/test.sqlite3"
        )

    async def asyncTearDown(self):
        self.store.close()
        self.temporary.cleanup()

    def service(self, provider):
        return VoiceTutorService(
            store=self.store,
            provider=provider,
            settings=settings(),
        )

    async def test_turn_is_metered_persisted_and_advances_atomically(self):
        provider = FakeProvider(
            [
                TranscriptionResult(
                    text="しゅう",
                    response_id="transcription-1",
                    model="gpt-4o-transcribe",
                    usage=ProviderUsage(input_tokens=10, output_tokens=2, total_tokens=12),
                )
            ]
        )
        service = self.service(provider)
        state = service.start_session(
            user_id=101,
            pack_id="basic-ja-100",
            language="ja",
            topic="time",
            block_session_id="telegram-block",
            words=WORDS,
        )

        result = await service.process_turn(
            user_id=101,
            audio=b"not-persisted-ogg-audio",
            duration_seconds=3,
            words=WORDS,
        )

        self.assertEqual(result.feedback.code, "exact")
        self.assertEqual(result.next_position, 1)
        self.assertEqual(result.available_credits, 4)
        self.assertEqual(provider.requests[0].language, "ja")
        self.assertIn("週", provider.requests[0].prompt)
        turns = service.turns(user_id=101, session_id=state.session_id)
        self.assertEqual(turns[0]["transcript"], "しゅう")
        with self.store.Session() as session:
            usage = session.execute(select(AIUsage)).scalar_one()
            self.assertEqual(usage.action, "voice_transcription")
            self.assertEqual(usage.status, "completed")
            self.assertEqual(usage.cost_micro_usd, 300)
            turn = session.execute(select(VoiceTurn)).scalar_one()
            self.assertNotIn("audio", " ".join(column.name for column in VoiceTurn.__table__.columns))
            self.assertNotIn(b"not-persisted", str(turn.__dict__).encode("utf-8"))

    async def test_last_word_completes_session(self):
        provider = FakeProvider(
            [
                TranscriptionResult(
                    "しゅう", None, "gpt-4o-transcribe", ProviderUsage()
                ),
                TranscriptionResult(
                    "ほん", None, "gpt-4o-transcribe", ProviderUsage()
                ),
            ]
        )
        service = self.service(provider)
        service.start_session(
            user_id=202,
            pack_id="basic-ja-100",
            language="ja",
            topic=None,
            block_session_id=None,
            words=WORDS,
        )

        first = await service.process_turn(
            user_id=202, audio=b"first", duration_seconds=2, words=WORDS
        )
        second = await service.process_turn(
            user_id=202, audio=b"second", duration_seconds=2, words=WORDS
        )

        self.assertEqual(first.session_status, "active")
        self.assertEqual(second.session_status, "completed")
        self.assertIsNone(service.active_session(202))

    async def test_retry_is_persisted_without_advancing_expected_word(self):
        provider = FakeProvider(
            [
                TranscriptionResult(
                    "ほん", None, "gpt-4o-transcribe", ProviderUsage()
                ),
                TranscriptionResult(
                    "しゅう", None, "gpt-4o-transcribe", ProviderUsage()
                ),
            ]
        )
        service = self.service(provider)
        state = service.start_session(
            user_id=212,
            pack_id="basic-ja-100",
            language="ja",
            topic=None,
            block_session_id=None,
            words=WORDS,
        )

        retry = await service.process_turn(
            user_id=212, audio=b"wrong", duration_seconds=2, words=WORDS
        )
        accepted = await service.process_turn(
            user_id=212, audio=b"correct", duration_seconds=2, words=WORDS
        )

        self.assertEqual(retry.feedback.code, "retry")
        self.assertEqual(retry.next_position, 0)
        self.assertEqual(retry.session_status, "active")
        self.assertEqual(accepted.feedback.code, "exact")
        self.assertEqual(accepted.next_position, 1)
        turns = service.turns(user_id=212, session_id=state.session_id)
        self.assertEqual(
            [turn["expected_vocabulary_id"] for turn in turns],
            [WORDS[0].vocabulary_id, WORDS[0].vocabulary_id],
        )

    async def test_freeform_transcription_is_metered_once_without_audio_storage(self):
        provider = FakeProvider(
            [
                TranscriptionResult(
                    "Как мой прогресс?",
                    "groq-transcription-1",
                    "gpt-4o-transcribe",
                    ProviderUsage(input_tokens=8, output_tokens=3, total_tokens=11),
                    detected_language="ru",
                )
            ]
        )
        service = self.service(provider)

        result = await service.transcribe_message(
            user_id=220,
            audio=b"ephemeral-telegram-ogg",
            duration_seconds=3,
        )

        self.assertEqual(result.transcript, "Как мой прогресс?")
        self.assertEqual(result.detected_language, "ru")
        self.assertEqual(result.available_credits, 4)
        self.assertTrue(provider.requests[0].detect_language)
        with self.store.Session() as session:
            usage = session.execute(select(AIUsage)).scalar_one()
            self.assertEqual(usage.action, "voice_transcription")
            self.assertEqual(usage.status, "completed")
            self.assertEqual(usage.billed_credits, 1)
            self.assertEqual(usage.provider_attempts, 1)
            self.assertTrue(usage.provider_response_received)
            self.assertNotIn(
                b"ephemeral-telegram-ogg",
                str(usage.__dict__).encode("utf-8"),
            )

    async def test_freeform_provider_failure_releases_reserved_credit(self):
        service = self.service(FakeProvider([RuntimeError("provider down")]))

        with self.assertRaises(RuntimeError):
            await service.transcribe_message(
                user_id=221,
                audio=b"voice",
                duration_seconds=2,
            )

        summary = self.store.ai_usage_summary(221, initial_credits=5)
        self.assertEqual(summary["available_credits"], 5)
        self.assertEqual(summary["failed_requests"], 1)

    async def test_invalid_billable_transcript_keeps_provider_telemetry(self):
        provider = FakeProvider(
            [
                TranscriptionResult(
                    "",
                    "groq-invalid-1",
                    "gpt-4o-transcribe",
                    ProviderUsage(input_tokens=8, output_tokens=1, total_tokens=9),
                    detected_language="ru",
                )
            ]
        )
        service = self.service(provider)

        with self.assertRaises(VoiceProviderError):
            await service.transcribe_message(
                user_id=222,
                audio=b"voice",
                duration_seconds=2,
            )

        summary = self.store.ai_usage_summary(222, initial_credits=5)
        self.assertEqual(summary["available_credits"], 5)
        with self.store.Session() as session:
            usage = session.execute(select(AIUsage)).scalar_one()
            self.assertEqual(usage.status, "failed")
            self.assertTrue(usage.provider_response_received)
            self.assertEqual(usage.provider_response_id, "groq-invalid-1")
            self.assertEqual(usage.cost_micro_usd, 200)

    async def test_invalid_practice_transcript_keeps_provider_telemetry(self):
        provider = FakeProvider(
            [
                TranscriptionResult(
                    "",
                    "practice-invalid-1",
                    "gpt-4o-transcribe",
                    ProviderUsage(input_tokens=8, output_tokens=1, total_tokens=9),
                )
            ]
        )
        service = self.service(provider)
        service.start_session(
            user_id=223,
            pack_id="basic-ja-100",
            language="ja",
            topic=None,
            block_session_id=None,
            words=WORDS,
        )

        with self.assertRaises(VoiceProviderError):
            await service.process_turn(
                user_id=223,
                audio=b"voice",
                duration_seconds=2,
                words=WORDS,
            )

        summary = self.store.ai_usage_summary(223, initial_credits=5)
        self.assertEqual(summary["available_credits"], 5)
        with self.store.Session() as session:
            usage = session.execute(select(AIUsage)).scalar_one()
            self.assertEqual(usage.status, "failed")
            self.assertTrue(usage.provider_response_received)
            self.assertEqual(usage.provider_response_id, "practice-invalid-1")
            self.assertEqual(usage.cost_micro_usd, 200)

    async def test_provider_failure_releases_reserved_credit(self):
        service = self.service(FakeProvider([RuntimeError("provider down")]))
        service.start_session(
            user_id=303,
            pack_id="basic-ja-100",
            language="ja",
            topic=None,
            block_session_id=None,
            words=WORDS,
        )

        with self.assertRaises(RuntimeError):
            await service.process_turn(
                user_id=303, audio=b"voice", duration_seconds=2, words=WORDS
            )

        summary = self.store.ai_usage_summary(303, initial_credits=5)
        self.assertEqual(summary["available_credits"], 5)
        self.assertEqual(summary["failed_requests"], 1)
        with self.store.Session() as session:
            self.assertEqual(
                session.scalar(select(func.count()).select_from(VoiceTurn)), 0
            )

    async def test_audio_limits_are_checked_before_provider_or_reservation(self):
        provider = FakeProvider([])
        service = self.service(provider)
        service.start_session(
            user_id=404,
            pack_id="basic-ja-100",
            language="ja",
            topic=None,
            block_session_id=None,
            words=WORDS,
        )

        with self.assertRaises(ValueError):
            await service.process_turn(
                user_id=404,
                audio=b"voice",
                duration_seconds=31,
                words=WORDS,
            )

        self.assertEqual(provider.requests, [])
        self.assertEqual(self.store.ai_usage_summary(404)["requests"], 0)


class OpenAITranscriptionProviderTest(unittest.IsolatedAsyncioTestCase):
    async def test_adapter_sends_ogg_in_memory_and_normalizes_usage(self):
        create = AsyncMock(
            return_value=MagicMock(
                text="bonjour",
                id="tr-1",
                model="gpt-4o-transcribe",
                usage=MagicMock(
                    input_tokens=4,
                    output_tokens=1,
                    total_tokens=5,
                    input_token_details=MagicMock(cached_tokens=2),
                ),
            )
        )
        client = MagicMock()
        client.audio.transcriptions.create = create
        provider = OpenAITranscriptionProvider(
            api_key="test-key", model="gpt-4o-transcribe", client=client
        )

        result = await provider.transcribe(
            MagicMock(audio=b"ogg-bytes", language="fr", prompt="bonjour")
        )

        self.assertEqual(result.text, "bonjour")
        self.assertEqual(result.usage.total_tokens, 5)
        file_value = create.await_args.kwargs["file"]
        self.assertEqual(file_value, ("voice.ogg", b"ogg-bytes", "audio/ogg"))


class VoiceSettingsTest(unittest.TestCase):
    def test_feature_is_disabled_by_default(self):
        self.assertFalse(VoiceTutorSettings.from_env({}).enabled)

    def test_enabled_feature_requires_key_and_explicit_cost(self):
        with self.assertRaises(VoiceConfigurationError):
            VoiceTutorSettings.from_env({"VOICE_TUTOR_ENABLED": "true"})
        with self.assertRaises(VoiceConfigurationError):
            VoiceTutorSettings.from_env(
                {
                    "VOICE_TUTOR_ENABLED": "true",
                    "OPENAI_API_KEY": "key",
                }
            )

        configured = VoiceTutorSettings.from_env(
            {
                "VOICE_TUTOR_ENABLED": "true",
                "OPENAI_API_KEY": "key",
                "VOICE_COST_MICRO_USD_PER_MINUTE": "6000",
                "VOICE_CONSENT_VERSION": "voice-2026-08",
                "VOICE_PROCESSING_NOTICE": (
                    "Аудио передаётся OpenAI только для распознавания речи; "
                    "исходный файл не сохраняется, текст хранится ограниченно."
                ),
            }
        )
        self.assertTrue(configured.enabled)
        self.assertEqual(configured.consent_version, "voice-2026-08")
        self.assertEqual(
            configured.retrospective_breaker_micro_usd_per_response,
            5000,
        )
