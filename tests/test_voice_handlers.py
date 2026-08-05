import os
from decimal import Decimal
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, MagicMock, call, patch

os.environ.setdefault("BOT_TOKEN", "123456:TESTTOKEN")

import bot
from mydictionary.voice_tutor import (
    PronunciationFeedback,
    VoiceSessionState,
    VoiceTurnResult,
    VoiceTutorSettings,
    VoiceWord,
)


def enabled_settings(**overrides):
    values = {
        "enabled": True,
        "provider": "openai",
        "model": "gpt-4o-transcribe",
        "openai_api_key": "test",
        "credits_per_request": 1,
        "initial_credits": 5,
        "reservation_timeout_seconds": 300,
        "max_audio_bytes": 1024,
        "max_duration_seconds": 30,
        "session_ttl_minutes": 30,
        "transcript_retention_days": 30,
        "cost_micro_usd_per_minute": Decimal("6000"),
    }
    values.update(overrides)
    return VoiceTutorSettings(**values)


WORD = VoiceWord("a" * 64, "週", "しゅう", "shuu", "неделя")
STATE = VoiceSessionState(
    session_id="11111111-1111-1111-1111-111111111111",
    user_id=55,
    pack_id="basic-ja-100",
    language="ja",
    topic="time",
    mode="pronunciation",
    vocabulary_ids=(WORD.vocabulary_id,),
    status="active",
    next_position=0,
    turn_count=0,
    expires_at=SimpleNamespace(),
)


class VoiceHandlerTest(unittest.IsolatedAsyncioTestCase):
    async def test_voice_mode_requests_versioned_consent_before_session(self):
        message = SimpleNamespace(reply_text=AsyncMock())
        update = SimpleNamespace(
            effective_message=message,
            effective_user=SimpleNamespace(id=55),
            effective_chat=SimpleNamespace(id=55),
        )
        context = SimpleNamespace(
            user_data={"block_session": "block-1"},
            bot=SimpleNamespace(),
        )
        store = MagicMock()
        store.has_consent.return_value = False
        pack = SimpleNamespace(pack_id="basic-ja-100", target_language="ja")
        with (
            patch.object(bot, "VOICE_SETTINGS", enabled_settings()),
            patch.object(bot, "get_store", return_value=store),
            patch.object(bot, "active_voice_block", return_value=(pack, [(1, WORD)])),
            patch.object(bot, "get_voice_tutor_service") as service,
        ):
            await bot.start_voice_mode(update, context, mode="pronunciation")

        service.assert_not_called()
        self.assertEqual(
            context.user_data["pending_voice_consent"]["mode"], "pronunciation"
        )
        self.assertIn("Согласие", message.reply_text.await_args.args[0])

    async def test_voice_consent_callback_grants_and_resumes_pending_mode(self):
        query = SimpleNamespace(
            data="voiceconsent:accept",
            answer=AsyncMock(),
            edit_message_reply_markup=AsyncMock(),
        )
        update = SimpleNamespace(
            callback_query=query,
            effective_user=SimpleNamespace(id=55),
        )
        context = SimpleNamespace(
            user_data={
                "block_session": "block-1",
                "pending_voice_consent": {
                    "mode": "pronunciation",
                    "block_session": "block-1",
                    "expires_at": 9999999999,
                },
            }
        )
        store = MagicMock()
        store.grant_consent.return_value = True
        with (
            patch.object(bot, "get_store", return_value=store),
            patch.object(bot, "VOICE_SETTINGS", enabled_settings()),
            patch.object(bot, "record_product_event"),
            patch.object(bot, "launch_voice_mode", new=AsyncMock()) as launch,
        ):
            await bot.voice_consent_cb.__wrapped__(update, context)

        store.grant_consent.assert_called_once()
        launch.assert_awaited_once_with(update, context, mode="pronunciation")

    async def test_prompt_sends_russian_text_before_reference_audio(self):
        context = SimpleNamespace(bot=SimpleNamespace(send_message=AsyncMock()))
        pack = SimpleNamespace(direction="ltr", flag="🇯🇵")
        ordering = MagicMock()
        ordering.attach_mock(context.bot.send_message, "text")

        with patch.object(bot, "send_pronunciation", new=AsyncMock()) as audio:
            ordering.attach_mock(audio, "audio")
            await bot.send_voice_prompt(
                chat_id=1,
                context=context,
                pack=pack,
                indexed_word=(7, WORD),
                position=1,
                total=10,
            )

        self.assertEqual([item[0] for item in ordering.mock_calls], ["text", "audio"])
        text = context.bot.send_message.await_args.kwargs["text"]
        self.assertLess(text.index("неделя"), text.index("週"))
        self.assertIn("shuu", text)

    async def test_metadata_limit_rejects_before_telegram_download(self):
        message = SimpleNamespace(
            voice=SimpleNamespace(duration=31, file_size=100, file_id="voice"),
            reply_text=AsyncMock(),
        )
        context = SimpleNamespace(bot=SimpleNamespace(get_file=AsyncMock()))
        update = SimpleNamespace(message=message, effective_user=SimpleNamespace(id=55))
        store = MagicMock()
        store.has_consent.return_value = True

        with (
            patch.object(bot, "VOICE_SETTINGS", enabled_settings()),
            patch.object(bot, "get_store", return_value=store),
        ):
            await bot.voice_message_handler.__wrapped__(update, context)

        context.bot.get_file.assert_not_awaited()
        self.assertIn("не принято", message.reply_text.await_args.args[0])

    async def test_missing_voice_consent_rejects_before_telegram_download(self):
        message = SimpleNamespace(
            voice=SimpleNamespace(duration=3, file_size=100, file_id="voice"),
            reply_text=AsyncMock(),
        )
        context = SimpleNamespace(bot=SimpleNamespace(get_file=AsyncMock()))
        update = SimpleNamespace(message=message, effective_user=SimpleNamespace(id=55))
        store = MagicMock()
        store.has_consent.return_value = False

        with (
            patch.object(bot, "VOICE_SETTINGS", enabled_settings()),
            patch.object(bot, "get_store", return_value=store),
        ):
            await bot.voice_message_handler.__wrapped__(update, context)

        context.bot.get_file.assert_not_awaited()
        self.assertIn("Согласие", message.reply_text.await_args.args[0])

    async def test_conversation_mode_uses_block_phrase_and_phrase_tts(self):
        practice = bot._voice_word(
            {
                "target": "bonjour",
                "meaning": "привет",
                "transcription": "bon-zhoor",
                "example_target": "Bonjour, comment allez-vous ?",
                "example_meaning": "Здравствуйте, как вы поживаете?",
            },
            "fr",
            mode="conversation",
        )
        pack = SimpleNamespace(
            direction="ltr",
            flag="🇫🇷",
            pack_id="basic-fr-100",
            content_version=2,
            pronunciation=SimpleNamespace(tts_voice="fr-FR", tts_rate="-10%"),
        )
        context = SimpleNamespace(
            bot=SimpleNamespace(send_message=AsyncMock(), send_voice=AsyncMock())
        )

        with (
            patch.object(bot, "get_audio", new=AsyncMock(return_value="audio")) as get_audio,
            patch.object(bot, "send_pronunciation", new=AsyncMock()) as word_audio,
        ):
            await bot.send_voice_prompt(
                chat_id=9,
                context=context,
                pack=pack,
                indexed_word=(1, practice),
                position=1,
                total=10,
                mode="conversation",
            )

        text = context.bot.send_message.await_args.kwargs["text"]
        self.assertIn("Здравствуйте, как вы поживаете?", text)
        self.assertIn("Bonjour, comment allez-vous ?", text)
        self.assertIn("bonjour bon-zhoor", text)
        get_audio.assert_awaited_once()
        context.bot.send_voice.assert_awaited_once_with(chat_id=9, voice="audio")
        word_audio.assert_not_awaited()

    async def test_success_shows_transcript_then_reference_audio(self):
        telegram_file = SimpleNamespace(
            download_as_bytearray=AsyncMock(return_value=bytearray(b"ogg"))
        )
        message = SimpleNamespace(
            voice=SimpleNamespace(duration=3, file_size=3, file_id="voice"),
            reply_text=AsyncMock(),
        )
        context = SimpleNamespace(
            bot=SimpleNamespace(get_file=AsyncMock(return_value=telegram_file))
        )
        update = SimpleNamespace(
            message=message,
            effective_user=SimpleNamespace(id=55),
            effective_chat=SimpleNamespace(id=77),
        )
        feedback = PronunciationFeedback(
            transcript="しゅう",
            expected=WORD,
            matched=WORD,
            code="exact",
            similarity_bps=10000,
        )
        service = SimpleNamespace(
            active_session=MagicMock(return_value=STATE),
            process_turn=AsyncMock(
                return_value=VoiceTurnResult(feedback, "completed", 1, 4)
            ),
        )
        pack = SimpleNamespace(
            pack_id="basic-ja-100", target_language="ja", flag="🇯🇵"
        )
        store = MagicMock()
        store.has_consent.return_value = True

        with (
            patch.object(bot, "VOICE_SETTINGS", enabled_settings()),
            patch.object(bot, "get_store", return_value=store),
            patch.object(bot, "get_voice_tutor_service", return_value=service),
            patch.object(bot, "restore_voice_block", return_value=(pack, [(7, WORD)])),
            patch.object(bot, "send_pronunciation", new=AsyncMock()) as pronunciation,
            patch.object(bot, "record_product_event"),
        ):
            await bot.voice_message_handler.__wrapped__(update, context)

        service.process_turn.assert_awaited_once_with(
            user_id=55,
            audio=b"ogg",
            duration_seconds=3,
            words=[WORD],
        )
        first_reply = message.reply_text.await_args_list[0].args[0]
        self.assertIn("Распознано: しゅう", first_reply)
        self.assertIn("Значение: неделя", first_reply)
        self.assertIn("Транскрипция: shuu", first_reply)
        self.assertIn("не акустическая оценка", first_reply)
        pronunciation.assert_awaited_once_with(77, 7, context)
