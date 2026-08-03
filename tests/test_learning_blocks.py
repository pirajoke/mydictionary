import os
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch


TEST_DATA_DIR = tempfile.mkdtemp(prefix="mydictionary-tests-")
os.environ["BOT_TOKEN"] = "123456:TESTTOKEN"
os.environ["ALLOWED_USER_ID"] = "1"
os.environ["DATA_DIR"] = TEST_DATA_DIR

import bot
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

    def test_japanese_study_list_uses_romaji_with_kanji_in_parentheses(self):
        study_list = bot.format_study_list([10])
        self.assertEqual(study_list, "1. *watashi (私)* — я")

    def test_vietnamese_study_list_keeps_ipa_format(self):
        bot.PROGRESS["active_lang"] = "vi"
        idx = next(i for i, word in enumerate(bot.W()) if word["en"] == "thích")
        word = bot.W()[idx]
        self.assertEqual(
            bot.format_study_list([idx]),
            f"1. *{word['en']} {word['ipa']}* — {word['ru']}",
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
        self.assertIn("ltopic:ja:all", callback_ids)
        self.assertIn("ltopic:ja:food", callback_ids)
        self.assertIn("ltopic:ja:time", callback_ids)

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
        allowed_translations = {bot.W()[idx]["ru"] for idx in indices}

        for idx in indices:
            options = bot.build_block_quiz_options(indices, idx)
            self.assertIn(bot.W()[idx]["ru"], options)
            self.assertLessEqual(len(options), 4)
            self.assertEqual(len(options), len(set(options)))
            self.assertTrue(set(options).issubset(allowed_translations))

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
        allowed_translations = {bot.W()[idx]["ru"] for idx in self.indices}
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
