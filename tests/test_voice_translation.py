import inspect as python_inspect
import json
import os
import tempfile
import unittest
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from sqlalchemy import select

os.environ.setdefault("BOT_TOKEN", "123456:TESTTOKEN")
os.environ.setdefault("ALLOWED_USER_ID", "1")
os.environ.setdefault("ALLOW_SQLITE_DEV", "true")

import bot
from mydictionary import voice_tutor
from mydictionary.ai_tutor import ProviderUsage
from mydictionary.storage import AIUsage, DatabaseStore, UserConsent


def required_public(testcase, owner, name):
    owner_name = getattr(owner, "__name__", owner.__class__.__name__)
    testcase.assertTrue(
        hasattr(owner, name),
        f"missing voice-translation public behavior: {owner_name}.{name}",
    )
    return getattr(owner, name)


def voice_update(user_id=701, *, duration=3, file_size=256):
    message = SimpleNamespace(
        voice=SimpleNamespace(
            duration=duration,
            file_size=file_size,
            file_id="telegram-voice-id",
        ),
        reply_text=AsyncMock(),
        reply_voice=AsyncMock(),
    )
    update = SimpleNamespace(
        message=message,
        effective_message=message,
        effective_user=SimpleNamespace(id=user_id),
        effective_chat=SimpleNamespace(id=user_id),
    )
    context = SimpleNamespace(
        user_data={"voice_entry_mode": "translation"},
        bot=SimpleNamespace(get_file=AsyncMock()),
    )
    return update, context, message


def translation_env(**overrides):
    values = {
        "VOICE_TRANSLATION_ENABLED": "true",
        "OPENAI_API_KEY": "test-key",
        "VOICE_TRANSLATION_MODEL": "gpt-5.6-luna",
        "VOICE_TRANSLATION_CONSENT_VERSION": "voice-translation-2026-08-11",
        "VOICE_TRANSLATION_PROCESSING_NOTICE": (
            "Голос передаётся для распознавания и перевода; исходное аудио "
            "не сохраняется, а операции учитываются раздельно."
        ),
        "VOICE_TRANSLATION_STT_MICRO_USD_PER_MINUTE": "6000",
        "VOICE_TRANSLATION_INPUT_USD_PER_MILLION": "1.25",
        "VOICE_TRANSLATION_OUTPUT_USD_PER_MILLION": "10.00",
        "VOICE_TRANSLATION_PRICING_REVIEWED_ON": date.today().isoformat(),
        "VOICE_TRANSLATION_MAX_AUDIO_BYTES": "1048576",
        "VOICE_TRANSLATION_MAX_DURATION_SECONDS": "30",
    }
    values.update(overrides)
    return values


class VoiceTranslationSettingsContractTest(unittest.TestCase):
    def test_ac_09_translation_is_disabled_by_default(self):
        settings_class = required_public(
            self, voice_tutor, "VoiceTranslationSettings"
        )
        self.assertFalse(settings_class.from_env({}).enabled)

    def test_ac_09_requires_new_notice_and_positive_reviewed_costs(self):
        settings_class = required_public(
            self, voice_tutor, "VoiceTranslationSettings"
        )
        with self.assertRaises(ValueError):
            settings_class.from_env(
                translation_env(
                    VOICE_TRANSLATION_CONSENT_VERSION="voice-practice-2026-08",
                    VOICE_TRANSLATION_PROCESSING_NOTICE=(
                        "Аудио используется только для проверки произношения."
                    ),
                ),
                existing_voice_consent_version="voice-practice-2026-08",
            )
        with self.assertRaises(ValueError):
            settings_class.from_env(
                translation_env(VOICE_TRANSLATION_INPUT_USD_PER_MILLION="0"),
                existing_voice_consent_version="voice-practice-2026-08",
            )

        configured = settings_class.from_env(
            translation_env(),
            existing_voice_consent_version="voice-practice-2026-08",
        )
        self.assertTrue(configured.enabled)
        self.assertEqual(
            configured.consent_version, "voice-translation-2026-08-11"
        )
        self.assertGreater(configured.stt_cost_micro_usd_per_minute, 0)
        self.assertGreater(configured.input_usd_per_million, 0)
        self.assertGreater(configured.output_usd_per_million, 0)
        self.assertRegex(configured.economics_snapshot_sha256, r"^[0-9a-f]{64}$")

        with self.assertRaises(ValueError):
            settings_class.from_env(
                translation_env(
                    AI_MAX_PROJECT_COST_MICRO_USD_PER_DAY="20000",
                    AI_MAX_PROJECT_COST_MICRO_USD_PER_MONTH="10000",
                ),
                existing_voice_consent_version="voice-practice-2026-08",
            )


class VoiceEntryPointContractTest(unittest.IsolatedAsyncioTestCase):
    async def test_voice_entry_explains_direct_notes_and_hides_disabled_translation(self):
        update, context, message = voice_update()
        update.message.voice = None
        update.message.text = "/voice"
        with (
            patch.object(bot, "VOICE_SETTINGS", SimpleNamespace(enabled=True)),
            patch.object(
                bot,
                "VOICE_TRANSLATION_SETTINGS",
                SimpleNamespace(enabled=False),
            ),
            patch.object(bot, "start_voice_mode", new=AsyncMock()) as start,
        ):
            await getattr(bot.cmd_voice, "__wrapped__", bot.cmd_voice)(update, context)

        start.assert_not_awaited()
        message.reply_text.assert_awaited_once()
        markup = message.reply_text.await_args.kwargs["reply_markup"]
        callbacks = {
            button.callback_data
            for row in markup.inline_keyboard
            for button in row
        }
        self.assertEqual(
            callbacks,
            {
                "voice-mode:pronunciation",
                "voice-mode:guided-phrase",
            },
        )
        self.assertIn("голосовое", message.reply_text.await_args.args[0].casefold())
        self.assertIn("одно слово", message.reply_text.await_args.args[0].casefold())
        commands = {item.command for item in bot.build_bot_commands(ai_enabled=True)}
        self.assertNotIn("voice_translate", commands)
        self.assertNotIn("guided_phrase", commands)

    async def test_voice_entry_keeps_translation_when_feature_is_enabled(self):
        update, context, message = voice_update()
        update.message.voice = None
        update.message.text = "/voice"
        with (
            patch.object(bot, "VOICE_SETTINGS", SimpleNamespace(enabled=True)),
            patch.object(
                bot,
                "VOICE_TRANSLATION_SETTINGS",
                SimpleNamespace(enabled=True),
            ),
        ):
            await getattr(bot.cmd_voice, "__wrapped__", bot.cmd_voice)(update, context)

        callbacks = {
            button.callback_data
            for row in message.reply_text.await_args.kwargs[
                "reply_markup"
            ].inline_keyboard
            for button in row
        }
        self.assertIn("voice-mode:translation", callbacks)

    async def test_ac_07_new_reference_retires_previous_replaceable_audio(self):
        sender = required_public(self, bot, "send_voice_translation_reference")
        context = SimpleNamespace(
            user_data={bot.LAST_PRONUNCIATION_MESSAGES_KEY: {"777": 41}},
            bot=SimpleNamespace(
                send_voice=AsyncMock(return_value=SimpleNamespace(message_id=42)),
                delete_message=AsyncMock(),
            ),
        )
        renderer = AsyncMock(return_value=b"reference-audio")
        await sender(
            chat_id=777,
            context=context,
            target_text="Bonjour",
            target_language="fr",
            renderer=renderer,
        )

        renderer.assert_awaited_once_with("Bonjour", language="fr")
        context.bot.send_voice.assert_awaited_once_with(
            chat_id=777, voice=b"reference-audio"
        )
        context.bot.delete_message.assert_awaited_once_with(
            chat_id=777, message_id=41
        )
        self.assertEqual(
            context.user_data[bot.LAST_PRONUNCIATION_MESSAGES_KEY]["777"], 42
        )


class VoiceTranslationHandlerGateTest(unittest.IsolatedAsyncioTestCase):
    async def test_err_03_missing_translation_consent_rejects_before_download(self):
        update, context, message = voice_update()
        store = MagicMock()
        store.product_profile.return_value = {"access_status": "active"}
        store.has_consent.return_value = False
        settings = SimpleNamespace(
            enabled=True,
            consent_version="voice-translation-2026-08-11",
            max_duration_seconds=30,
            max_audio_bytes=1024,
        )
        with (
            patch.object(bot, "get_store", return_value=store),
            patch.object(bot, "VOICE_TRANSLATION_SETTINGS", settings, create=True),
        ):
            await getattr(
                bot.voice_message_handler, "__wrapped__", bot.voice_message_handler
            )(update, context)

        store.has_consent.assert_called_with(
            701,
            consent_type="voice_translation_processing",
            document_version="voice-translation-2026-08-11",
        )
        context.bot.get_file.assert_not_awaited()
        self.assertRegex(
            message.reply_text.await_args.args[0].casefold(), r"соглас|услов"
        )

    async def test_err_03_disabled_inactive_and_oversized_reject_before_download(self):
        cases = (
            (False, "active", 3, 256),
            (True, "blocked", 3, 256),
            (True, "active", 31, 256),
            (True, "active", 3, 2048),
        )
        for enabled, access, duration, size in cases:
            with self.subTest(
                enabled=enabled, access=access, duration=duration, size=size
            ):
                update, context, message = voice_update(
                    duration=duration, file_size=size
                )
                store = MagicMock()
                store.product_profile.return_value = {"access_status": access}
                store.has_consent.return_value = True
                settings = SimpleNamespace(
                    enabled=enabled,
                    consent_version="voice-translation-2026-08-11",
                    max_duration_seconds=30,
                    max_audio_bytes=1024,
                )
                with (
                    patch.object(bot, "get_store", return_value=store),
                    patch.object(
                        bot, "VOICE_TRANSLATION_SETTINGS", settings, create=True
                    ),
                ):
                    await getattr(
                        bot.voice_message_handler,
                        "__wrapped__",
                        bot.voice_message_handler,
                    )(update, context)

                context.bot.get_file.assert_not_awaited()
                message.reply_text.assert_awaited()

    async def test_ac_08_active_practice_session_keeps_practice_precedence(self):
        update, context, message = voice_update()
        telegram_file = SimpleNamespace(
            download_as_bytearray=AsyncMock(return_value=bytearray(b"ogg"))
        )
        context.bot.get_file.return_value = telegram_file
        store = MagicMock()
        store.product_profile.return_value = {"access_status": "active"}
        store.has_consent.return_value = True
        word = voice_tutor.VoiceWord("a" * 64, "週", "しゅう", "shuu", "неделя")
        state = SimpleNamespace(
            next_position=0,
            mode="pronunciation",
            session_id="practice-session",
        )
        result = SimpleNamespace(
            feedback=SimpleNamespace(code="exact"),
            session_status="completed",
            next_position=1,
        )
        practice = SimpleNamespace(
            active_session=MagicMock(return_value=state),
            process_turn=AsyncMock(return_value=result),
        )
        translation = SimpleNamespace(translate_note=AsyncMock())
        practice_settings = SimpleNamespace(
            enabled=True,
            consent_version="voice-practice-v1",
            max_duration_seconds=30,
            max_audio_bytes=1024,
        )
        with (
            patch.object(bot, "get_store", return_value=store),
            patch.object(bot, "get_voice_tutor_service", return_value=practice),
            patch.object(
                bot, "get_voice_translation_service", return_value=translation, create=True
            ),
            patch.object(bot, "VOICE_SETTINGS", practice_settings),
            patch.object(
                bot,
                "restore_voice_block",
                return_value=(
                    SimpleNamespace(pack_id="ja-basics-100", target_language="ja"),
                    [(7, word)],
                ),
            ),
            patch.object(bot, "voice_feedback_text", return_value="practice feedback"),
            patch.object(bot, "send_voice_reference", new=AsyncMock()),
            patch.object(bot, "record_product_event"),
        ):
            await getattr(
                bot.voice_message_handler, "__wrapped__", bot.voice_message_handler
            )(update, context)

        practice.process_turn.assert_awaited_once()
        translation.translate_note.assert_not_awaited()
        self.assertIn("practice feedback", message.reply_text.await_args_list[0].args[0])


class FakeTranscriptionProvider:
    def __init__(self, *, text, language):
        self.text = text
        self.language = language
        self.requests = []

    async def transcribe(self, request):
        self.requests.append(request)
        return SimpleNamespace(
            text=self.text,
            detected_language=self.language,
            response_id="stt-response-1",
            model="gpt-4o-transcribe",
            service_tier="default",
            status="completed",
            usage=ProviderUsage(input_tokens=4, output_tokens=2, total_tokens=6),
        )


class FakeTranslationProvider:
    def __init__(self, result=None, failure=None):
        self.result = result
        self.failure = failure
        self.requests = []

    async def translate(self, request):
        self.requests.append(request)
        if self.failure is not None:
            raise self.failure
        return self.result


class VoiceTranslationServiceContractTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="voice-translation-red-")
        self.store = DatabaseStore(
            f"sqlite:///{Path(self.temporary.name) / 'test.sqlite3'}"
        )
        self.store.ensure_user_id(801)

    async def asyncTearDown(self):
        self.store.close()
        self.temporary.cleanup()

    def settings(self):
        return SimpleNamespace(
            enabled=True,
            provider="openai",
            transcription_model="gpt-4o-transcribe",
            translation_model="gpt-5.6-luna",
            requested_service_tier="default",
            initial_credits=10,
            stt_credits_per_request=1,
            translation_credits_per_request=1,
            reservation_timeout_seconds=300,
            max_audio_bytes=1024,
            max_duration_seconds=30,
            stt_cost_micro_usd_per_minute=6000,
            input_usd_per_million=1.25,
            output_usd_per_million=10.00,
            max_preflight_cost_micro_usd=5000,
            retrospective_breaker_micro_usd_per_response=5000,
            max_daily_requests_per_user=5,
            max_project_cost_micro_usd_per_day=25000,
            max_project_cost_micro_usd_per_month=100000,
            max_in_flight_cost_micro_usd=5000,
            economics_snapshot_id="voice-translation-test",
            economics_snapshot_sha256="1" * 64,
            metering_journal_path=str(Path(self.temporary.name) / "metering.jsonl"),
        )

    def service(self, stt, translator):
        service_class = required_public(
            self, voice_tutor, "VoiceTranslationService"
        )
        return service_class(
            store=self.store,
            transcription_provider=stt,
            translation_provider=translator,
            settings=self.settings(),
        )

    async def test_ac_08_russian_source_routes_to_active_language_and_meters_twice(self):
        stt = FakeTranscriptionProvider(text="Добрый день", language="ru")
        translator = FakeTranslationProvider(
            SimpleNamespace(
                translation="Bonjour",
                latin_transcription="bon-zhoor",
                response_id="translation-response-1",
                model="gpt-5.6-luna",
                service_tier="default",
                status="completed",
                usage=ProviderUsage(input_tokens=12, output_tokens=8, total_tokens=20),
                cost_micro_usd=300,
            )
        )
        service = self.service(stt, translator)
        raw_audio = b"private-raw-telegram-voice"

        result = await service.translate_note(
            user_id=801,
            audio=raw_audio,
            duration_seconds=3,
            active_language="fr",
        )

        self.assertEqual(result.detected_language, "ru")
        self.assertEqual(result.source_transcript, "Добрый день")
        self.assertEqual(result.target_language, "fr")
        self.assertEqual(result.translation, "Bonjour")
        self.assertEqual(result.latin_transcription, "bon-zhoor")
        self.assertFalse(result.partial)
        self.assertEqual(len(stt.requests), 1)
        self.assertEqual(len(translator.requests), 1)
        self.assertEqual(translator.requests[0].source_language, "ru")
        self.assertEqual(translator.requests[0].target_language, "fr")

        with self.store.Session() as session:
            usage = session.execute(
                select(AIUsage).order_by(AIUsage.created_at)
            ).scalars().all()
        self.assertEqual(
            [(item.action, item.status) for item in usage],
            [("voice_transcription", "completed"), ("voice_translation", "completed")],
        )
        telemetry = json.dumps(
            [
                {column.name: getattr(item, column.name) for column in AIUsage.__table__.columns}
                for item in usage
            ],
            default=str,
            ensure_ascii=False,
        ).encode("utf-8")
        self.assertNotIn(raw_audio, telemetry)
        self.assertNotIn("Добрый день".encode("utf-8"), telemetry)
        self.assertNotIn(b"Bonjour", telemetry)

    async def test_ac_08_non_russian_source_routes_to_russian(self):
        stt = FakeTranscriptionProvider(text="Bonjour", language="fr")
        translator = FakeTranslationProvider(
            SimpleNamespace(
                translation="Здравствуйте; добрый день",
                latin_transcription="zdravstvuyte; dobryy den",
                response_id="translation-response-2",
                model="gpt-5.6-luna",
                service_tier="default",
                status="completed",
                usage=ProviderUsage(input_tokens=10, output_tokens=6, total_tokens=16),
                cost_micro_usd=250,
            )
        )
        result = await self.service(stt, translator).translate_note(
            user_id=801,
            audio=b"voice",
            duration_seconds=2,
            active_language="fr",
        )

        self.assertEqual(result.target_language, "ru")
        self.assertEqual(translator.requests[0].target_language, "ru")
        self.assertIn("добрый день", result.translation)

    async def test_ac_08_err_02_billable_stt_then_translation_failure_is_partial(self):
        stt = FakeTranscriptionProvider(text="Bonjour", language="fr")
        translator = FakeTranslationProvider(
            failure=RuntimeError("private translation provider detail")
        )
        result = await self.service(stt, translator).translate_note(
            user_id=801,
            audio=b"voice",
            duration_seconds=2,
            active_language="fr",
        )

        self.assertTrue(result.partial)
        self.assertEqual(result.source_transcript, "Bonjour")
        self.assertEqual(result.translation, "")
        self.assertRegex(result.notice_ru.casefold(), r"перевод.*не (заверш|получ)")
        self.assertNotIn("private translation provider detail", result.notice_ru)
        self.assertEqual(len(stt.requests), 1)
        self.assertEqual(len(translator.requests), 1)
        with self.store.Session() as session:
            usage = session.execute(
                select(AIUsage).order_by(AIUsage.created_at)
            ).scalars().all()
        self.assertEqual(
            [(item.action, item.status) for item in usage],
            [("voice_transcription", "completed"), ("voice_translation", "failed")],
        )

    async def test_err_02_invalid_billable_response_keeps_cost_and_attempt_audit(self):
        stt = FakeTranscriptionProvider(text="Bonjour", language="fr")
        translator = FakeTranslationProvider(
            SimpleNamespace(
                translation="",
                latin_transcription="",
                response_id="translation-invalid-1",
                model="gpt-5.6-luna",
                service_tier="default",
                status="completed",
                usage=ProviderUsage(input_tokens=10, output_tokens=2, total_tokens=12),
                cost_micro_usd=275,
            )
        )

        result = await self.service(stt, translator).translate_note(
            user_id=801,
            audio=b"voice",
            duration_seconds=2,
            active_language="fr",
        )

        self.assertTrue(result.partial)
        with self.store.Session() as session:
            usage = session.execute(
                select(AIUsage).where(AIUsage.action == "voice_translation")
            ).scalar_one()
        self.assertEqual(usage.status, "failed")
        self.assertEqual(usage.provider_attempts, 1)
        self.assertTrue(usage.provider_response_received)
        self.assertEqual(usage.cost_micro_usd, 275)
        self.assertFalse(usage.cost_is_estimate)
        self.assertEqual(
            self.store.ai_budget_status()["spent_today_micro_usd"],
            475,
        )


class VoiceTranslationRenderingContractTest(unittest.TestCase):
    def test_ac_08_ac_10_russian_first_contract_for_eight_languages(self):
        renderer = required_public(self, bot, "voice_translation_result_text")
        cases = (
            ("en", "hello", "hello"),
            ("fr", "bonjour", "bon-zhoor"),
            ("de", "Guten Tag", "goo-ten tahk"),
            ("ja", "こんにちは", "konnichiwa"),
            ("ar", "مرحبا", "marhaban"),
            ("zh", "你好", "ni hao"),
            ("ru", "Здравствуйте", "zdravstvuyte"),
            ("es", "buenos días", "bwenos dias"),
        )
        for language, target, transcription in cases:
            with self.subTest(language=language):
                rendered = renderer(
                    SimpleNamespace(
                        detected_language="ru",
                        source_transcript="Добрый день",
                        target_language=language,
                        translation=target,
                        latin_transcription=transcription,
                        partial=False,
                        notice_ru="",
                    )
                )
                lines = [line for line in rendered.splitlines() if line.strip()]
                self.assertTrue(lines[0].startswith("🇷🇺"))
                self.assertLess(rendered.index("Добрый день"), rendered.index(target))
                self.assertIn(target, rendered)
                if language in {"ja", "ar", "zh", "ru"}:
                    self.assertIn(transcription, rendered)
                self.assertRegex(
                    rendered.casefold(), r"определ|язык|распознан"
                )

    def test_ec_01_renderer_and_payload_reject_unbounded_content(self):
        renderer = required_public(self, bot, "voice_translation_result_text")
        with self.assertRaises(ValueError):
            renderer(
                SimpleNamespace(
                    detected_language="fr",
                    source_transcript="x" * 5001,
                    target_language="ru",
                    translation="перевод",
                    latin_transcription="perevod",
                    partial=False,
                    notice_ru="",
                )
            )


class VoiceTranslationPrivacyContractTest(unittest.TestCase):
    def test_ac_09_existing_pronunciation_consent_is_not_translation_consent(self):
        with tempfile.TemporaryDirectory(prefix="voice-consent-red-") as root:
            store = DatabaseStore(f"sqlite:///{Path(root) / 'test.sqlite3'}")
            try:
                store.ensure_user_id(901)
                store.grant_consent(
                    901,
                    consent_type="voice_processing",
                    document_version="voice-practice-2026-08",
                    source="test",
                )
                try:
                    existing_authorizes_translation = store.has_consent(
                        901,
                        consent_type="voice_translation_processing",
                        document_version="voice-translation-2026-08-11",
                    )
                except ValueError as exc:
                    self.fail(
                        "voice_translation_processing consent contract is missing: "
                        f"{exc}"
                    )
                self.assertFalse(existing_authorizes_translation)
                store.grant_consent(
                    901,
                    consent_type="voice_translation_processing",
                    document_version="voice-translation-2026-08-11",
                    source="test",
                )
                self.assertTrue(
                    store.has_consent(
                        901,
                        consent_type="voice_translation_processing",
                        document_version="voice-translation-2026-08-11",
                    )
                )
                with store.Session() as session:
                    consents = session.execute(select(UserConsent)).scalars().all()
                self.assertEqual(len(consents), 2)
            finally:
                store.close()


if __name__ == "__main__":
    unittest.main()
