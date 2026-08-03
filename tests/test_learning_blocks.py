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
