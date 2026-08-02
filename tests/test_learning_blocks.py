import os
import tempfile
import unittest


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
        self.assertIn("🇯🇵 *私*", details)
        self.assertIn("🔤 watashi", details)

    def test_question_prompt_hides_russian_answer(self):
        prompt = bot.format_word_label(10)
        self.assertNotIn("🇷🇺", prompt)
        self.assertNotIn("*я*", prompt)
        self.assertIn("🔤 watashi", prompt)

    def test_study_list_uses_russian_first_order(self):
        study_list = bot.format_study_list([10])
        self.assertEqual(
            study_list.splitlines(),
            ["1. 🇷🇺 *я*", "   🇯🇵 *私*", "   🔤 watashi"],
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


if __name__ == "__main__":
    unittest.main()
