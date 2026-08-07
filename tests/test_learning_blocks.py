import asyncio
import os
from io import BytesIO
from datetime import datetime, timedelta
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch


TEST_DATA_DIR = tempfile.mkdtemp(prefix="mydictionary-tests-")
os.environ["BOT_TOKEN"] = "123456:TESTTOKEN"
os.environ["ALLOWED_USER_ID"] = "1"
os.environ["DATA_DIR"] = TEST_DATA_DIR
os.environ["ALLOW_SQLITE_DEV"] = "true"

import bot
from mydictionary.catalog import ContentPack, PronunciationConfig
from mydictionary.content import meaning_text, target_text, transcription_text
from vocabulary_topics import topics_for_word


class LearningBlocksTest(unittest.TestCase):
    def setUp(self):
        bot.PROGRESS["active_lang"] = "ja"

    def test_revealed_card_starts_with_russian_and_has_romaji(self):
        details = bot.format_word_details(10)
        self.assertEqual(details.splitlines()[0], "🇷🇺 *я*")
        self.assertEqual(details.splitlines()[1], "🇯🇵 *watashi (私)*")

    def test_question_prompt_hides_russian_answer(self):
        prompt = bot.format_word_label(10)
        self.assertNotIn("🇷🇺", prompt)
        self.assertNotIn("*я*", prompt)
        self.assertEqual(prompt, "🇯🇵 *watashi (私)*")

    def test_visual_card_uses_topic_emoji_progress_and_hides_meaning(self):
        user_data = {}
        bot.reset_block_state(user_data, [10, 21, 22, 23, 24], "ja", None)
        bot.start_block_attempt(user_data, "flash")

        card = bot.format_learning_card_front(user_data, 10)

        self.assertTrue(card.startswith("👥"))
        self.assertIn("Карточка 1 из 5", card)
        self.assertIn("▰▱▱▱▱", card)
        self.assertIn("watashi (私)", card)
        self.assertNotIn("🇷🇺 *я*", card)

    def test_due_words_only_returns_reviews_that_have_arrived(self):
        now = datetime.now()
        words = [
            {"next_review": (now - timedelta(days=2)).isoformat()},
            {"next_review": None},
            {"next_review": (now + timedelta(days=2)).isoformat()},
            {"next_review": (now - timedelta(hours=1)).isoformat()},
        ]
        with patch.object(bot, "W", return_value=words):
            self.assertEqual(bot.due_word_indices(), [0, 3])

    def test_japanese_study_list_uses_romaji_with_kanji_in_parentheses(self):
        study_list = bot.format_study_list([10])
        self.assertEqual(study_list, "1. *watashi (私)* — я")

    def test_vietnamese_study_list_keeps_ipa_format(self):
        bot.PROGRESS["active_lang"] = "vi"
        idx = next(
            i
            for i, word in enumerate(bot.W())
            if target_text(word) == "thích"
        )
        word = bot.W()[idx]
        self.assertEqual(
            bot.format_study_list([idx]),
            f"1. *{target_text(word)} {transcription_text(word)}* — "
            f"{meaning_text(word)}",
        )

    def test_french_study_list_shows_curated_bonjour_meanings(self):
        bot.PROGRESS["active_lang"] = "fr"
        idx = next(
            i for i, word in enumerate(bot.W())
            if target_text(word) == "bonjour"
        )

        self.assertIn(
            "здравствуйте / добрый день / доброе утро",
            bot.format_study_list([idx]),
        )

    def test_rtl_pack_uses_configured_transcription_order_and_isolation(self):
        pack = ContentPack(
            pack_id="ar-basics-100",
            target_language="ar",
            meaning_language="ru",
            direction="rtl",
            flag="🇸🇦",
            meaning_flag="🇷🇺",
            label="Arabic",
            title="Arabic basics",
            description="Test pack",
            filename="words_ar.json",
            storage_key="ar",
            visibility="public",
            is_free=True,
            status="published",
            content_schema=2,
            content_version=1,
            entry_count=1,
            pronunciation=PronunciationConfig(
                transcription_system="learner-latin",
                transcription_position="before",
                tts_locale="ar-SA",
                tts_voice="ar-SA-ZariyahNeural",
                tts_rate="-20%",
            ),
        )
        word = {"target": "مرحبا", "transcription": "marhaban"}

        self.assertEqual(
            bot.format_target_word(word, pack),
            "marhaban (\u2067مرحبا\u2069)",
        )

    def test_pick_block_only_returns_selected_topic(self):
        indices = bot.pick_block(topic="food")
        self.assertTrue(indices)
        self.assertLessEqual(len(indices), 10)
        for idx in indices:
            self.assertIn("food", topics_for_word(bot.W()[idx], "ja"))

    def test_next_block_avoids_previous_words_when_topic_is_large_enough(self):
        first = bot.pick_block(topic="time")
        second = bot.pick_block(topic="time", exclude_indices=set(first))
        self.assertEqual(len(first), 10)
        self.assertEqual(len(second), 10)
        self.assertFalse(set(first) & set(second))

    def test_topic_keyboard_contains_all_words_and_japanese_topics(self):
        keyboard = bot.build_topic_keyboard("ja").inline_keyboard
        callback_ids = {
            button.callback_data
            for row in keyboard
            for button in row
        }
        self.assertIn("ltopic:ja-basics-100:all", callback_ids)
        self.assertIn("ltopic:ja-basics-100:food", callback_ids)
        self.assertIn("ltopic:ja-basics-100:time", callback_ids)

    def test_ai_context_is_limited_to_current_valid_block(self):
        user_data = {}
        bot.reset_block_state(user_data, [10, 21], "ja", "people")

        context = bot.active_tutor_context(user_data)

        self.assertEqual(context.language, "ja")
        self.assertEqual(context.topic, "people")
        self.assertEqual([word.term for word in context.words], ["私", "先生"])
        self.assertEqual(
            [word.transcription for word in context.words],
            ["watashi", "sensei"],
        )
        bot.invalidate_block_session(user_data)
        self.assertIsNone(bot.active_tutor_context(user_data))

    def test_ai_button_is_feature_flagged_and_session_bound(self):
        with patch.object(
            bot, "AI_SETTINGS", SimpleNamespace(enabled=True)
        ):
            keyboard = bot.build_study_buttons([10], "session1")

        callbacks = [
            button.callback_data
            for row in keyboard.inline_keyboard
            for button in row
        ]
        self.assertIn("bai:session1", callbacks)

    def test_quiz_options_only_use_words_from_active_block(self):
        indices = list(range(10))
        allowed_translations = {meaning_text(bot.W()[idx]) for idx in indices}

        for idx in indices:
            options = bot.build_block_quiz_options(indices, idx)
            self.assertIn(meaning_text(bot.W()[idx]), options)
            self.assertEqual(len(options), 4)
            self.assertEqual(len(options), len(set(options)))
            self.assertTrue(set(options).issubset(allowed_translations))

    def test_block_study_keyboard_has_only_quiz_and_written_modes(self):
        keyboard = bot.build_study_buttons(list(range(10)), "session1")
        mode_buttons = [
            button
            for row in keyboard.inline_keyboard
            for button in row
            if button.callback_data and button.callback_data.startswith("bmode:")
        ]

        self.assertEqual(
            [button.callback_data for button in mode_buttons],
            ["bmode:session1:quiz", "bmode:session1:type"],
        )
        self.assertEqual(
            [button.text for button in mode_buttons],
            ["Тест · 4 варианта", "Письменно"],
        )

    def test_quiz_callbacks_are_bound_to_active_session(self):
        indices = list(range(10))
        user_data = {}
        bot.reset_block_state(user_data, indices, "ja", "food")
        bot.start_block_attempt(user_data, "quiz")

        keyboard = bot.build_block_quiz_keyboard(user_data, indices[0])
        prefix = f"bquiz:{user_data['block_session']}:{indices[0]}:"
        for row in keyboard.inline_keyboard:
            self.assertTrue(row[0].callback_data.startswith(prefix))
            self.assertLessEqual(len(row[0].callback_data.encode()), 64)

    def test_retry_attempt_keeps_original_block_and_rotates_session(self):
        indices = list(range(10))
        user_data = {}
        bot.reset_block_state(user_data, indices, "ja", "food")
        bot.start_block_attempt(user_data, "quiz")
        previous_session = user_data["block_session"]

        bot.start_block_attempt(user_data, "quiz", [indices[1], indices[4]])

        self.assertEqual(user_data["block_all_indices"], indices)
        self.assertEqual(user_data["block_indices"], [indices[1], indices[4]])
        self.assertNotEqual(user_data["block_session"], previous_session)

        keyboard = bot.build_block_quiz_keyboard(user_data, indices[1])
        self.assertEqual(len(keyboard.inline_keyboard), 4)

    def test_global_mode_invalidation_leaves_no_active_block_answer(self):
        user_data = {}
        bot.reset_block_state(user_data, list(range(10)), "ja", "food")
        bot.start_block_attempt(user_data, "type")
        user_data["block_typing"] = True
        user_data["type_idx"] = 0

        bot.invalidate_block_session(user_data)

        self.assertIsNone(user_data["block_session"])
        self.assertIsNone(user_data["block_mode"])
        self.assertFalse(user_data["block_typing"])
        self.assertIsNone(user_data["type_idx"])


class LearningAudioTest(unittest.IsolatedAsyncioTestCase):
    async def test_audio_button_sends_text_card_before_voice(self):
        bot.PROGRESS["active_lang"] = "ja"
        events = []
        user_data = {}
        bot.reset_block_state(user_data, [10], "ja", "people")

        async def send_message(**kwargs):
            events.append(("text", kwargs))

        async def send_voice(*args, **kwargs):
            events.append(("voice", kwargs))

        query = SimpleNamespace(
            data=f"lplay:{user_data['block_session']}:10",
            answer=AsyncMock(),
            message=SimpleNamespace(chat_id=123),
        )
        update = SimpleNamespace(
            callback_query=query,
            effective_user=SimpleNamespace(id=1),
        )
        context = SimpleNamespace(
            user_data=user_data,
            bot=SimpleNamespace(send_message=send_message),
        )

        with patch.object(bot, "send_pronunciation", side_effect=send_voice):
            await bot.learn_play_cb(update, context)

        self.assertEqual([event[0] for event in events], ["text", "voice"])
        self.assertEqual(
            events[0][1]["text"],
            "🇷🇺 *я*\n🇯🇵 *watashi (私)*",
        )

    async def test_pronunciation_uses_pack_speech_voice_rate_and_version(self):
        pack = bot.CATALOG.require("ja-basics-100")
        word = {"target": "今日", "speech": "きょう"}
        audio = BytesIO(b"mp3")
        send_voice = AsyncMock()
        context = SimpleNamespace(bot=SimpleNamespace(send_voice=send_voice))

        with (
            patch.object(bot, "W", return_value=[word]),
            patch.object(bot, "active_content_pack", return_value=pack),
            patch.object(bot, "get_audio", new=AsyncMock(return_value=audio)) as get,
        ):
            await bot.send_pronunciation(123, 0, context)

        get.assert_awaited_once_with(
            "きょう",
            voice="ja-JP-NanamiNeural",
            rate="-25%",
            cache_namespace="ja-basics-100:v1",
        )
        send_voice.assert_awaited_once_with(chat_id=123, voice=audio)

    async def test_new_pronunciation_deletes_previous_message_in_same_chat(self):
        client = SimpleNamespace(
            send_voice=AsyncMock(
                side_effect=[
                    SimpleNamespace(message_id=101),
                    SimpleNamespace(message_id=102),
                ]
            ),
            send_audio=AsyncMock(),
            delete_message=AsyncMock(),
        )
        context = SimpleNamespace(bot=client, user_data={})

        await bot.send_pronunciation_audio(
            chat_id=123,
            audio=BytesIO(b"first"),
            title="first",
            context=context,
        )
        await bot.send_pronunciation_audio(
            chat_id=123,
            audio=BytesIO(b"second"),
            title="second",
            context=context,
        )

        client.delete_message.assert_awaited_once_with(
            chat_id=123,
            message_id=101,
        )
        self.assertEqual(
            context.user_data[bot.LAST_PRONUNCIATION_MESSAGES_KEY],
            {"123": 102},
        )

    async def test_concurrent_pronunciations_keep_newest_message(self):
        first_send_started = asyncio.Event()
        release_first_send = asyncio.Event()
        send_count = 0

        async def send_voice(**kwargs):
            nonlocal send_count
            send_count += 1
            if send_count == 1:
                first_send_started.set()
                await release_first_send.wait()
                return SimpleNamespace(message_id=101)
            return SimpleNamespace(message_id=102)

        client = SimpleNamespace(
            send_voice=AsyncMock(side_effect=send_voice),
            send_audio=AsyncMock(),
            delete_message=AsyncMock(),
        )
        context = SimpleNamespace(bot=client, user_data={})

        first = asyncio.create_task(
            bot.send_pronunciation_audio(
                chat_id=123,
                audio=BytesIO(b"first"),
                title="first",
                context=context,
            )
        )
        await first_send_started.wait()
        await bot.send_pronunciation_audio(
            chat_id=123,
            audio=BytesIO(b"second"),
            title="second",
            context=context,
        )
        release_first_send.set()
        await first

        self.assertEqual(
            context.user_data[bot.LAST_PRONUNCIATION_MESSAGES_KEY],
            {"123": 102},
        )
        client.delete_message.assert_awaited_once_with(
            chat_id=123,
            message_id=101,
        )

    async def test_pronunciation_tracking_is_isolated_by_chat_and_user(self):
        client = SimpleNamespace(delete_message=AsyncMock())
        first_user = SimpleNamespace(bot=client, user_data={})
        second_user = SimpleNamespace(bot=client, user_data={})

        await bot.replace_previous_pronunciation(
            123, SimpleNamespace(message_id=101), first_user
        )
        await bot.replace_previous_pronunciation(
            456, SimpleNamespace(message_id=201), first_user
        )
        await bot.replace_previous_pronunciation(
            123, SimpleNamespace(message_id=301), second_user
        )

        client.delete_message.assert_not_awaited()
        self.assertEqual(
            first_user.user_data[bot.LAST_PRONUNCIATION_MESSAGES_KEY],
            {"123": 101, "456": 201},
        )
        self.assertEqual(
            second_user.user_data[bot.LAST_PRONUNCIATION_MESSAGES_KEY],
            {"123": 301},
        )

    async def test_delete_failure_keeps_new_voice_and_does_not_send_audio(self):
        client = SimpleNamespace(
            send_voice=AsyncMock(
                side_effect=[
                    SimpleNamespace(message_id=101),
                    SimpleNamespace(message_id=102),
                ]
            ),
            send_audio=AsyncMock(),
            delete_message=AsyncMock(
                side_effect=bot.TelegramError("message cannot be deleted")
            ),
        )
        context = SimpleNamespace(bot=client, user_data={})

        await bot.send_pronunciation_audio(
            chat_id=123,
            audio=BytesIO(b"first"),
            title="first",
            context=context,
        )
        await bot.send_pronunciation_audio(
            chat_id=123,
            audio=BytesIO(b"second"),
            title="second",
            context=context,
        )

        client.delete_message.assert_awaited_once()
        client.send_audio.assert_not_awaited()
        self.assertEqual(
            context.user_data[bot.LAST_PRONUNCIATION_MESSAGES_KEY]["123"],
            102,
        )

    async def test_voice_send_fallback_replaces_previous_with_audio_message(self):
        audio = BytesIO(b"audio")
        audio.seek(3)
        client = SimpleNamespace(
            send_voice=AsyncMock(side_effect=bot.TelegramError("voice failed")),
            send_audio=AsyncMock(return_value=SimpleNamespace(message_id=102)),
            delete_message=AsyncMock(),
        )
        context = SimpleNamespace(
            bot=client,
            user_data={bot.LAST_PRONUNCIATION_MESSAGES_KEY: {"123": 101}},
        )

        await bot.send_pronunciation_audio(
            chat_id=123,
            audio=audio,
            title="bonjour",
            context=context,
        )

        self.assertEqual(client.send_audio.await_args.kwargs["audio"].tell(), 0)
        client.delete_message.assert_awaited_once_with(
            chat_id=123,
            message_id=101,
        )


class DailyLessonTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        bot.PROGRESS["active_lang"] = "ja"

    async def test_home_lesson_starts_directly_in_flashcard_mode(self):
        message = SimpleNamespace(chat_id=123, reply_text=AsyncMock())
        query = SimpleNamespace(message=message)
        context = SimpleNamespace(
            user_data={},
            bot=SimpleNamespace(send_message=AsyncMock()),
        )
        pack = bot.CATALOG.require("ja-basics-100")
        with (
            patch.object(bot, "active_content_pack", return_value=pack),
            patch.object(bot, "daily_lesson_size", return_value=5),
            patch.object(bot, "pick_block", return_value=[10, 21, 22, 23, 24]),
            patch.object(bot, "block_send_question_msg", new=AsyncMock()) as send,
        ):
            await bot.start_home_lesson(query, context, lesson_kind="daily")

        self.assertEqual(context.user_data["block_mode"], "flash")
        self.assertEqual(context.user_data["lesson_kind"], "daily")
        self.assertEqual(len(context.user_data["block_indices"]), 5)
        send.assert_awaited_once_with(message, context)

    async def test_empty_review_offers_a_new_lesson(self):
        message = SimpleNamespace(chat_id=123)
        context = SimpleNamespace(
            user_data={},
            bot=SimpleNamespace(send_message=AsyncMock()),
        )
        pack = bot.CATALOG.require("ja-basics-100")
        with (
            patch.object(bot, "active_content_pack", return_value=pack),
            patch.object(bot, "daily_lesson_size", return_value=5),
            patch.object(bot, "due_word_indices", return_value=[]),
        ):
            await bot.start_home_lesson(
                SimpleNamespace(message=message),
                context,
                lesson_kind="review",
            )

        payload = context.bot.send_message.await_args.kwargs
        self.assertIn("всё повторено", payload["text"])
        self.assertEqual(
            payload["reply_markup"].inline_keyboard[0][0].callback_data,
            "start:daily",
        )

    async def test_flash_card_reveal_has_replay_and_simple_rating_buttons(self):
        user_data = {}
        bot.reset_block_state(user_data, [10], "ja", "people")
        bot.start_block_attempt(user_data, "flash")
        session_id = user_data["block_session"]
        query = SimpleNamespace(
            data=f"bflash_show:{session_id}:10",
            answer=AsyncMock(),
            edit_message_text=AsyncMock(),
            message=SimpleNamespace(chat_id=123),
        )
        update = SimpleNamespace(
            callback_query=query,
            effective_user=SimpleNamespace(id=1),
        )
        context = SimpleNamespace(user_data=user_data, bot=SimpleNamespace())
        with patch.object(bot, "record_product_event") as record:
            await bot.block_flash_show_cb.__wrapped__(update, context)

        payload = query.edit_message_text.await_args
        self.assertIn("🇷🇺 *я*", payload.args[0])
        buttons = payload.kwargs["reply_markup"].inline_keyboard
        self.assertEqual(buttons[0][0].callback_data, f"bplay:{session_id}:10")
        self.assertEqual([button.text for button in buttons[1]], ["😵 Не знаю", "✅ Знаю"])
        record.assert_called_once()
        self.assertEqual(record.call_args.args[0], "card_revealed")


class GlobalCallbackIsolationTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        bot.PROGRESS["active_lang"] = "ja"
        self.indices = list(range(10))

    def make_active_block(self):
        user_data = {}
        bot.reset_block_state(user_data, self.indices, "ja", "food")
        bot.start_block_attempt(user_data, "type")
        user_data["block_typing"] = True
        user_data["type_idx"] = self.indices[0]
        return user_data

    def make_callback_update(self, data, user_data):
        query = SimpleNamespace(
            data=data,
            answer=AsyncMock(),
            edit_message_text=AsyncMock(),
            message=SimpleNamespace(chat_id=123),
        )
        update = SimpleNamespace(
            callback_query=query,
            effective_user=SimpleNamespace(id=1),
        )
        context = SimpleNamespace(user_data=user_data, bot=SimpleNamespace())
        return update, context, query

    async def test_global_callbacks_exit_active_block(self):
        cases = [
            ("quiz answer", bot.quiz_callback, "quiz:0:1:answer"),
            ("next quiz", bot.next_quiz, "next_quiz"),
            ("next type", bot.next_type, "next_type"),
            ("show flashcard", bot.flash_show, "flash_show:0"),
            ("known flashcard", bot.flash_knew, "flash_knew:0"),
            ("missed flashcard", bot.flash_didnt, "flash_didnt:0"),
            ("smart answer", bot.smart_quiz_cb, "smart:0:1"),
            ("next smart", bot.next_smart_cb, "next_smart"),
        ]

        for label, handler, callback_data in cases:
            with self.subTest(callback=label):
                user_data = self.make_active_block()
                update, context, query = self.make_callback_update(
                    callback_data, user_data
                )
                with (
                    patch.object(bot, "send_pronunciation", new=AsyncMock()),
                    patch.object(bot, "mark_correct", return_value=(10, 0)),
                    patch.object(bot, "mark_wrong", return_value=(2, 0)),
                    patch.object(bot, "pick_word", return_value=1),
                    patch.object(bot, "adaptive_mode", return_value="quiz"),
                ):
                    await handler(update, context)

                query.answer.assert_awaited_once_with()
                self.assertIsNone(user_data["block_session"])
                self.assertIsNone(user_data["block_mode"])
                self.assertFalse(user_data["block_typing"])

                if handler is bot.next_type:
                    self.assertEqual(user_data["type_idx"], 1)

    async def test_poll_answer_exits_active_block(self):
        user_data = self.make_active_block()
        answer = SimpleNamespace(
            user=SimpleNamespace(id=1),
            poll_id="poll-1",
            option_ids=[0],
        )
        update = SimpleNamespace(poll_answer=answer)
        send_poll = AsyncMock(
            return_value=SimpleNamespace(poll=SimpleNamespace(id="poll-2"))
        )
        context = SimpleNamespace(
            user_data=user_data,
            bot_data={"poll_map": {"poll-1": (0, 0)}},
            bot=SimpleNamespace(send_poll=send_poll),
        )

        with (
            patch.object(bot, "mark_correct"),
            patch.object(bot, "pick_word", return_value=1),
            patch.object(bot, "build_quiz_options", return_value=(["a", "b"], 0)),
        ):
            await bot.poll_answer_handler(update, context)

        self.assertIsNone(user_data["block_session"])
        self.assertIsNone(user_data["block_mode"])
        self.assertFalse(user_data["block_typing"])


class BlockCallbackTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        bot.PROGRESS["active_lang"] = "ja"
        self.indices = list(range(10))
        self.user_data = {}
        bot.reset_block_state(self.user_data, self.indices, "ja", "food")
        bot.start_block_attempt(self.user_data, "quiz")

    def make_update(self, data):
        query = SimpleNamespace(
            data=data,
            answer=AsyncMock(),
            edit_message_text=AsyncMock(),
            message=SimpleNamespace(chat_id=123),
        )
        update = SimpleNamespace(
            callback_query=query,
            effective_user=SimpleNamespace(id=1),
        )
        context = SimpleNamespace(user_data=self.user_data, bot=SimpleNamespace())
        return update, context, query

    async def test_block_question_and_options_use_current_block(self):
        update, context, query = self.make_update("unused")

        with patch.object(bot, "send_pronunciation", new=AsyncMock()):
            await bot.block_send_question(query, context)

        call = query.edit_message_text.await_args
        kwargs = call.kwargs
        expected_idx = self.indices[0]
        self.assertIn(bot.format_word_label(expected_idx), call.args[0])
        option_texts = {
            row[0].text for row in kwargs["reply_markup"].inline_keyboard
        }
        allowed_translations = {
            meaning_text(bot.W()[idx]) for idx in self.indices
        }
        self.assertTrue(option_texts.issubset(allowed_translations))

    async def test_ai_callback_answers_once_and_uses_active_session(self):
        session_id = self.user_data["block_session"]
        update, context, query = self.make_update(f"bai:{session_id}")

        with patch.object(
            bot, "send_ai_tutor_answer", new=AsyncMock()
        ) as send_answer:
            await bot.block_ai_cb(update, context)

        self.assertEqual(query.answer.await_count, 1)
        send_answer.assert_awaited_once()
        self.assertEqual(send_answer.await_args.kwargs["user_id"], 1)

    async def test_stale_session_callback_is_rejected(self):
        idx = self.indices[0]
        update, context, query = self.make_update(f"bquiz:stale123:{idx}:1")

        with patch.object(bot, "block_advance", new=AsyncMock()) as advance:
            await bot.block_quiz_cb(update, context)

        query.answer.assert_awaited_once_with(bot.BLOCK_STALE_TEXT, show_alert=True)
        advance.assert_not_awaited()

    async def test_callback_for_noncurrent_word_is_rejected(self):
        idx = self.indices[1]
        session_id = self.user_data["block_session"]
        update, context, query = self.make_update(
            f"bquiz:{session_id}:{idx}:1"
        )

        with patch.object(bot, "block_advance", new=AsyncMock()) as advance:
            await bot.block_quiz_cb(update, context)

        query.answer.assert_awaited_once_with(bot.BLOCK_STALE_TEXT, show_alert=True)
        advance.assert_not_awaited()

    async def test_current_quiz_callback_advances_once(self):
        idx = self.indices[0]
        session_id = self.user_data["block_session"]
        update, context, query = self.make_update(
            f"bquiz:{session_id}:{idx}:1"
        )

        with patch.object(bot, "block_advance", new=AsyncMock()) as advance:
            await bot.block_quiz_cb(update, context)

        query.answer.assert_awaited_once_with()
        advance.assert_awaited_once_with(query, context, idx, True)

    async def test_starting_mode_invalidates_study_buttons(self):
        user_data = {}
        bot.reset_block_state(user_data, self.indices, "ja", "food")
        previous_session = user_data["block_session"]
        self.user_data = user_data
        update, context, query = self.make_update(
            f"bmode:{previous_session}:quiz"
        )

        with patch.object(bot, "block_send_question", new=AsyncMock()) as send:
            await bot.block_mode_cb(update, context)

        query.answer.assert_awaited_once_with()
        self.assertNotEqual(user_data["block_session"], previous_session)
        self.assertEqual(user_data["block_indices"], self.indices)
        send.assert_awaited_once_with(query, context)

    async def test_retry_uses_only_wrong_words_and_invalidates_summary(self):
        self.user_data["block_pos"] = len(self.indices)
        self.user_data["block_wrong"] = [self.indices[2], self.indices[7]]
        previous_session = self.user_data["block_session"]
        update, context, query = self.make_update(f"bretry:{previous_session}")

        with patch.object(bot, "block_send_question", new=AsyncMock()) as send:
            await bot.block_retry_cb(update, context)

        query.answer.assert_awaited_once_with()
        self.assertEqual(
            self.user_data["block_indices"],
            [self.indices[2], self.indices[7]],
        )
        self.assertEqual(self.user_data["block_all_indices"], self.indices)
        self.assertNotEqual(self.user_data["block_session"], previous_session)
        send.assert_awaited_once_with(query, context)


if __name__ == "__main__":
    unittest.main()
