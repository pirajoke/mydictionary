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


def direct_voice_update(*, entry_mode=None):
    message = SimpleNamespace(
        voice=SimpleNamespace(duration=3, file_size=3, file_id="voice"),
        reply_text=AsyncMock(),
    )
    user_data = {}
    if entry_mode is not None:
        user_data["voice_entry_mode"] = entry_mode
    telegram_file = SimpleNamespace(
        download_as_bytearray=AsyncMock(return_value=bytearray(b"ogg"))
    )
    context = SimpleNamespace(
        user_data=user_data,
        bot=SimpleNamespace(get_file=AsyncMock(return_value=telegram_file)),
    )
    update = SimpleNamespace(
        message=message,
        effective_message=message,
        effective_user=SimpleNamespace(id=55, first_name="Mark"),
        effective_chat=SimpleNamespace(id=55),
    )
    return update, context, message


class VoiceHandlerTest(unittest.IsolatedAsyncioTestCase):
    async def test_direct_voice_is_transcribed_once_and_routed_to_mirror(self):
        update, context, _ = direct_voice_update()
        store = MagicMock()
        store.product_profile.return_value = {
            "access_status": "active",
            "onboarding_completed_at": "2026-08-01T00:00:00Z",
        }
        store.has_consent.return_value = True
        practice = SimpleNamespace(
            active_session=MagicMock(return_value=None),
            transcribe_message=AsyncMock(
                return_value=SimpleNamespace(
                    transcript="Объясни разницу между bonjour и salut",
                    detected_language="ru",
                    available_credits=39,
                )
            ),
        )
        mirror = AsyncMock()

        with (
            patch.object(bot, "VOICE_SETTINGS", enabled_settings()),
            patch.object(
                bot,
                "VOICE_TRANSLATION_SETTINGS",
                SimpleNamespace(enabled=False),
            ),
            patch.object(
                bot,
                "AI_SETTINGS",
                SimpleNamespace(enabled=True, consent_version="ai-v1"),
            ),
            patch.object(bot, "get_store", return_value=store),
            patch.object(bot, "get_voice_tutor_service", return_value=practice),
            patch.object(bot, "handle_mirror_question", new=mirror, create=True),
            patch.object(bot, "record_product_event"),
        ):
            await bot.voice_message_handler.__wrapped__(update, context)

        context.bot.get_file.assert_awaited_once_with("voice")
        practice.transcribe_message.assert_awaited_once_with(
            user_id=55,
            audio=b"ogg",
            duration_seconds=3,
        )
        mirror.assert_awaited_once_with(
            update,
            context,
            question="Объясни разницу между bonjour и salut",
        )

    async def test_disabled_sticky_translation_falls_back_to_direct_voice(self):
        update, context, _ = direct_voice_update(entry_mode="translation")
        store = MagicMock()
        store.product_profile.return_value = {
            "access_status": "active",
            "onboarding_completed_at": "2026-08-01T00:00:00Z",
        }
        store.has_consent.return_value = True
        practice = SimpleNamespace(
            active_session=MagicMock(return_value=None),
            transcribe_message=AsyncMock(
                return_value=SimpleNamespace(
                    transcript="Как мой прогресс?",
                    detected_language="ru",
                    available_credits=39,
                )
            ),
        )
        mirror = AsyncMock()

        with (
            patch.object(bot, "VOICE_SETTINGS", enabled_settings()),
            patch.object(
                bot,
                "VOICE_TRANSLATION_SETTINGS",
                SimpleNamespace(enabled=False),
            ),
            patch.object(
                bot,
                "AI_SETTINGS",
                SimpleNamespace(enabled=True, consent_version="ai-v1"),
            ),
            patch.object(bot, "get_store", return_value=store),
            patch.object(bot, "get_voice_tutor_service", return_value=practice),
            patch.object(bot, "handle_mirror_question", new=mirror, create=True),
            patch.object(bot, "record_product_event"),
        ):
            await bot.voice_message_handler.__wrapped__(update, context)

        self.assertNotIn("voice_entry_mode", context.user_data)
        mirror.assert_awaited_once()

    async def test_direct_voice_missing_consent_offers_inline_accept_before_download(self):
        update, context, message = direct_voice_update()
        store = MagicMock()
        store.product_profile.return_value = {
            "access_status": "active",
            "onboarding_completed_at": "2026-08-01T00:00:00Z",
        }
        store.has_consent.return_value = False
        practice = SimpleNamespace(active_session=MagicMock(return_value=None))

        with (
            patch.object(bot, "VOICE_SETTINGS", enabled_settings()),
            patch.object(
                bot,
                "VOICE_TRANSLATION_SETTINGS",
                SimpleNamespace(enabled=False),
            ),
            patch.object(
                bot,
                "AI_SETTINGS",
                SimpleNamespace(enabled=True, consent_version="ai-v1"),
            ),
            patch.object(bot, "get_store", return_value=store),
            patch.object(bot, "get_voice_tutor_service", return_value=practice),
        ):
            await bot.voice_message_handler.__wrapped__(update, context)

        context.bot.get_file.assert_not_awaited()
        self.assertEqual(
            context.user_data["pending_voice_consent"]["mode"], "assistant"
        )
        markup = message.reply_text.await_args.kwargs["reply_markup"]
        callbacks = {
            button.callback_data
            for row in markup.inline_keyboard
            for button in row
        }
        self.assertIn("voiceconsent:accept", callbacks)

    async def test_direct_voice_missing_ai_consent_is_checked_before_download(self):
        update, context, message = direct_voice_update()
        store = MagicMock()
        store.product_profile.return_value = {
            "access_status": "active",
            "onboarding_completed_at": "2026-08-01T00:00:00Z",
        }
        store.has_consent.side_effect = lambda user_id, **values: (
            values["consent_type"] == "voice_processing"
        )
        practice = SimpleNamespace(active_session=MagicMock(return_value=None))

        with (
            patch.object(bot, "VOICE_SETTINGS", enabled_settings()),
            patch.object(
                bot,
                "VOICE_TRANSLATION_SETTINGS",
                SimpleNamespace(enabled=False),
            ),
            patch.object(
                bot,
                "AI_SETTINGS",
                SimpleNamespace(
                    enabled=True,
                    consent_version="ai-v1",
                    processing_notice="Текст передаётся AI для учебного ответа.",
                ),
            ),
            patch.object(bot, "get_store", return_value=store),
            patch.object(bot, "get_voice_tutor_service", return_value=practice),
        ):
            await bot.voice_message_handler.__wrapped__(update, context)

        context.bot.get_file.assert_not_awaited()
        self.assertEqual(
            context.user_data["pending_ai_consent"]["request_kind"],
            "voice_assistant",
        )
        markup = message.reply_text.await_args.kwargs["reply_markup"]
        callbacks = {
            button.callback_data
            for row in markup.inline_keyboard
            for button in row
        }
        self.assertIn("aiconsent:accept", callbacks)

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

    async def test_voice_assistant_consent_survives_block_change_and_requests_resend(self):
        reply_text = AsyncMock()
        query = SimpleNamespace(
            data="voiceconsent:accept",
            answer=AsyncMock(),
            edit_message_reply_markup=AsyncMock(),
            message=SimpleNamespace(reply_text=reply_text),
        )
        update = SimpleNamespace(
            callback_query=query,
            effective_user=SimpleNamespace(id=55),
        )
        context = SimpleNamespace(
            user_data={
                "block_session": "new-block",
                "pending_voice_consent": {
                    "mode": "assistant",
                    "block_session": "old-block",
                    "expires_at": 9999999999,
                },
            }
        )
        store = MagicMock()
        with (
            patch.object(bot, "get_store", return_value=store),
            patch.object(bot, "VOICE_SETTINGS", enabled_settings()),
            patch.object(bot, "record_product_event"),
            patch.object(bot, "launch_voice_mode", new=AsyncMock()) as launch,
        ):
            await bot.voice_consent_cb.__wrapped__(update, context)

        store.grant_consent.assert_called_once()
        launch.assert_not_awaited()
        self.assertIn("ещё раз", reply_text.await_args.args[0])

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
            user_data={
                bot.LAST_PRONUNCIATION_MESSAGES_KEY: {"9": 200},
            },
            bot=SimpleNamespace(
                send_message=AsyncMock(),
                send_voice=AsyncMock(
                    return_value=SimpleNamespace(message_id=201)
                ),
                send_audio=AsyncMock(),
                delete_message=AsyncMock(),
            ),
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
        context.bot.delete_message.assert_awaited_once_with(
            chat_id=9,
            message_id=200,
        )
        word_audio.assert_not_awaited()

    async def test_completed_success_does_not_repeat_reference_audio(self):
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
        pronunciation.assert_not_awaited()

    async def test_retry_keeps_same_word_and_replays_only_its_reference(self):
        update, context, message = direct_voice_update()
        feedback = PronunciationFeedback(
            transcript="ほん",
            expected=WORD,
            matched=VoiceWord("b" * 64, "本", "ほん", "hon", "книга"),
            code="retry",
            similarity_bps=0,
        )
        state = SimpleNamespace(
            next_position=0,
            mode="pronunciation",
            session_id="practice-session",
        )
        service = SimpleNamespace(
            active_session=MagicMock(return_value=state),
            process_turn=AsyncMock(
                return_value=VoiceTurnResult(feedback, "active", 0, 4)
            ),
        )
        pack = SimpleNamespace(
            pack_id="basic-ja-100", target_language="ja", flag="🇯🇵"
        )
        store = MagicMock()
        store.product_profile.return_value = {"access_status": "active"}
        store.has_consent.return_value = True

        with (
            patch.object(bot, "VOICE_SETTINGS", enabled_settings()),
            patch.object(bot, "get_store", return_value=store),
            patch.object(bot, "get_voice_tutor_service", return_value=service),
            patch.object(
                bot,
                "restore_voice_block",
                return_value=(pack, [(7, WORD), (8, feedback.matched)]),
            ),
            patch.object(bot, "send_voice_reference", new=AsyncMock()) as reference,
            patch.object(bot, "send_voice_prompt", new=AsyncMock()) as next_prompt,
            patch.object(bot, "record_product_event"),
        ):
            await bot.voice_message_handler.__wrapped__(update, context)

        self.assertIn("ещё раз", message.reply_text.await_args.args[0].casefold())
        reference.assert_awaited_once_with(
            chat_id=55,
            context=context,
            pack=pack,
            indexed_word=(7, WORD),
            mode="pronunciation",
        )
        next_prompt.assert_not_awaited()
