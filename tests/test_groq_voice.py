import os
import tempfile
import unittest
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock


os.environ.setdefault("BOT_TOKEN", "123456:TESTTOKEN")
os.environ.setdefault("ALLOWED_USER_ID", "1")

from mydictionary.ai_tutor import ProviderUsage
from mydictionary.voice_tutor import (
    GroqTranscriptionProvider,
    TranscriptionRequest,
    VoiceConfigurationError,
    VoiceTranslationSettings,
    VoiceTutorSettings,
)


def groq_voice_env(**overrides):
    key = "gsk_" + "G" * 48
    values = {
        "VOICE_TUTOR_ENABLED": "true",
        "VOICE_PROVIDER": "groq",
        "GROQ_API_KEY": key,
        "VOICE_GROQ_ZDR_VERIFIED": "true",
        "VOICE_COST_MICRO_USD_PER_MINUTE": "1850",
        "VOICE_CONSENT_VERSION": "voice-groq-2026-08",
        "VOICE_PROCESSING_NOTICE": (
            "Голосовое сообщение передаётся Groq для распознавания; исходное "
            "аудио не сохраняется, а расшифровка хранится ограниченное время."
        ),
    }
    values.update(overrides)
    return values


class GroqVoiceSettingsContractTest(unittest.TestCase):
    def test_practice_selects_groq_model_key_and_minimum_billing(self):
        configured = VoiceTutorSettings.from_env(groq_voice_env())
        self.assertTrue(configured.enabled)
        self.assertEqual(configured.provider, "groq")
        self.assertEqual(configured.model, "whisper-large-v3")
        self.assertEqual(configured.groq_api_key, "gsk_" + "G" * 48)
        self.assertEqual(configured.minimum_billable_seconds, 10)
        self.assertEqual(configured.estimated_cost_micro_usd(3), 309)
        self.assertEqual(configured.estimated_cost_micro_usd(30), 925)

    def test_enabled_groq_fails_closed_without_its_key(self):
        with self.assertRaisesRegex(VoiceConfigurationError, "GROQ_API_KEY"):
            VoiceTutorSettings.from_env(groq_voice_env(GROQ_API_KEY=""))

    def test_enabled_groq_fails_closed_without_verified_zdr(self):
        with self.assertRaisesRegex(VoiceConfigurationError, "ZDR"):
            VoiceTutorSettings.from_env(
                groq_voice_env(VOICE_GROQ_ZDR_VERIFIED="false")
            )

    def test_disabled_voice_does_not_require_or_read_groq_key_file(self):
        configured = VoiceTutorSettings.from_env(
            {
                "VOICE_TUTOR_ENABLED": "false",
                "VOICE_PROVIDER": "groq",
                "GROQ_API_KEY_FILE": "/missing/disabled-groq.key",
            }
        )
        translated = VoiceTranslationSettings.from_env(
            {
                "VOICE_TRANSLATION_ENABLED": "false",
                "VOICE_TRANSLATION_PROVIDER": "groq",
                "GROQ_API_KEY_FILE": "/missing/disabled-groq.key",
            }
        )

        self.assertFalse(configured.enabled)
        self.assertIsNone(configured.groq_api_key)
        self.assertFalse(translated.enabled)

    def test_practice_and_translation_accept_private_key_file(self):
        with tempfile.TemporaryDirectory(prefix="mydictionary-groq-key-") as raw:
            root = Path(raw)
            os.chmod(root, 0o700)
            key_file = root / "groq.key"
            key_file.write_text("gsk_" + "F" * 48, encoding="ascii")
            os.chmod(key_file, 0o600)

            practice_values = groq_voice_env(
                GROQ_API_KEY="",
                GROQ_API_KEY_FILE=str(key_file),
            )
            practice = VoiceTutorSettings.from_env(practice_values)
            self.assertEqual(practice.groq_api_key, "gsk_" + "F" * 48)

            translation_values = {
                "VOICE_TRANSLATION_ENABLED": "true",
                "VOICE_TRANSLATION_PROVIDER": "groq",
                "GROQ_API_KEY_FILE": str(key_file),
                "VOICE_GROQ_ZDR_VERIFIED": "true",
                "OPENAI_API_KEY": "test-openai-key",
                "VOICE_TRANSLATION_CONSENT_VERSION": "voice-translation-groq-v1",
                "VOICE_TRANSLATION_PROCESSING_NOTICE": (
                    "Голос передаётся Groq для распознавания и OpenAI для "
                    "перевода; исходное аудио не сохраняется."
                ),
                "VOICE_TRANSLATION_STT_MICRO_USD_PER_MINUTE": "1850",
                "VOICE_TRANSLATION_INPUT_USD_PER_MILLION": "1",
                "VOICE_TRANSLATION_OUTPUT_USD_PER_MILLION": "1.25",
                "VOICE_TRANSLATION_PRICING_REVIEWED_ON": date.today().isoformat(),
            }
            translation = VoiceTranslationSettings.from_env(
                translation_values,
                existing_voice_consent_version="voice-practice-v1",
            )
            self.assertEqual(translation.groq_api_key, "gsk_" + "F" * 48)

    def test_translation_requires_groq_for_stt_and_openai_for_text(self):
        values = {
            "VOICE_TRANSLATION_ENABLED": "true",
            "VOICE_TRANSLATION_PROVIDER": "groq",
            "GROQ_API_KEY": "gsk_" + "G" * 48,
            "VOICE_GROQ_ZDR_VERIFIED": "true",
            "OPENAI_API_KEY": "test-openai-key",
            "VOICE_TRANSLATION_CONSENT_VERSION": "voice-translation-groq-v1",
            "VOICE_TRANSLATION_PROCESSING_NOTICE": (
                "Голос передаётся Groq для распознавания и OpenAI для перевода; "
                "исходное аудио не сохраняется."
            ),
            "VOICE_TRANSLATION_STT_MICRO_USD_PER_MINUTE": "1850",
            "VOICE_TRANSLATION_INPUT_USD_PER_MILLION": "1",
            "VOICE_TRANSLATION_OUTPUT_USD_PER_MILLION": "1.25",
            "VOICE_TRANSLATION_PRICING_REVIEWED_ON": date.today().isoformat(),
        }
        configured = VoiceTranslationSettings.from_env(
            values,
            existing_voice_consent_version="voice-practice-v1",
        )
        self.assertEqual(configured.provider, "groq")
        self.assertEqual(configured.transcription_model, "whisper-large-v3")
        self.assertEqual(configured.groq_api_key, "gsk_" + "G" * 48)
        self.assertEqual(configured.openai_api_key, "test-openai-key")
        self.assertEqual(configured.stt_minimum_billable_seconds, 10)
        self.assertTrue(configured.groq_zdr_verified)


class GroqTranscriptionAdapterTest(unittest.IsolatedAsyncioTestCase):
    async def test_adapter_uses_one_openai_compatible_transcription_attempt(self):
        response = SimpleNamespace(
            text="bonjour",
            language="fr",
            model="whisper-large-v3",
            x_groq=SimpleNamespace(id="groq-response-1"),
            usage=ProviderUsage(input_tokens=0, output_tokens=0, total_tokens=0),
        )
        create = AsyncMock(return_value=response)
        client = SimpleNamespace(
            audio=SimpleNamespace(transcriptions=SimpleNamespace(create=create))
        )
        provider = GroqTranscriptionProvider(
            api_key="test-groq-key",
            model="whisper-large-v3",
            client=client,
        )

        result = await provider.transcribe(
            TranscriptionRequest(
                audio=b"ogg",
                language="",
                prompt="",
                detect_language=True,
            )
        )

        self.assertEqual(result.text, "bonjour")
        self.assertEqual(result.detected_language, "fr")
        self.assertEqual(result.response_id, "groq-response-1")
        self.assertEqual(create.await_count, 1)
        self.assertEqual(create.await_args.kwargs["model"], "whisper-large-v3")
        self.assertNotIn("language", create.await_args.kwargs)


if __name__ == "__main__":
    unittest.main()
