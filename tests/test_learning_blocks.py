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


class LearningAudioTest(unittest.IsolatedAsyncioTestCase):
    async def test_audio_button_sends_text_card_before_voice(self):
        bot.PROGRESS["active_lang"] = "ja"
        events = []

        async def send_message(**kwargs):
            events.append(("text", kwargs))

        async def send_voice(*args, **kwargs):
            events.append(("voice", kwargs))

        query = SimpleNamespace(
            data="lplay:10",
            answer=AsyncMock(),
            message=SimpleNamespace(chat_id=123),
        )
        update = SimpleNamespace(
            callback_query=query,
            effective_user=SimpleNamespace(id=1),
        )
        context = SimpleNamespace(
            user_data={"block_lang": "ja"},
            bot=SimpleNamespace(send_message=send_message),
        )

        with patch.object(bot, "send_pronunciation", side_effect=send_voice):
            await bot.learn_play_cb(update, context)

        self.assertEqual([event[0] for event in events], ["text", "voice"])
        self.assertEqual(
            events[0][1]["text"],
            "🇷🇺 *я*\n🇯🇵 *watashi (私)*",
        )


if __name__ == "__main__":
    unittest.main()
