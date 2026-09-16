"""Post-lesson reinforcement keeps learners moving without another chooser."""

import os
import unittest

os.environ.setdefault("BOT_TOKEN", "123456:TESTTOKEN_ABCDEFGHIJKLMNOP")
os.environ.setdefault("ALLOWED_USER_ID", "1")
os.environ.setdefault("ALLOW_SQLITE_DEV", "true")

import bot
from mydictionary.localization import INTERFACE_LOCALES, translate


def buttons(markup):
    return [button for row in markup.inline_keyboard for button in row]


class PostLessonReinforcementTest(unittest.TestCase):
    def completed(self, mode: str, *, wrong: list[int] | None = None, locale: str = "en"):
        state = {"interface_locale": locale}
        bot.reset_block_state(
            state,
            [0, 1, 2],
            "ja",
            None,
            "ja-basics-100",
            lesson_kind="daily",
        )
        bot.start_block_attempt(state, mode)
        mistakes = list(wrong or [])
        state.update(
            block_pos=3,
            block_correct=3 - len(mistakes),
            block_wrong=mistakes,
        )
        return state

    def test_perfect_cards_offer_quiz_on_the_same_words(self):
        state = self.completed("flash")

        inline = buttons(bot.build_block_summary_keyboard(state))

        self.assertLessEqual(len(inline), 3)
        self.assertEqual(
            inline[0].callback_data,
            f"bmode:{state['block_session']}:quiz",
        )
        self.assertEqual(inline[0].text, translate("block_reinforce_quiz", "en"))

    def test_perfect_quiz_offers_written_recall_on_the_same_words(self):
        state = self.completed("quiz", locale="ru")

        inline = buttons(bot.build_block_summary_keyboard(state))

        self.assertLessEqual(len(inline), 3)
        self.assertEqual(
            inline[0].callback_data,
            f"bmode:{state['block_session']}:type",
        )
        self.assertEqual(inline[0].text, translate("block_reinforce_written", "ru"))

    def test_perfect_written_practice_still_offers_another_lesson(self):
        state = self.completed("type")

        inline = buttons(bot.build_block_summary_keyboard(state))

        self.assertEqual(inline[0].callback_data, "start:daily")
        self.assertEqual(inline[0].text, translate("block_another_lesson", "en"))

    def test_errors_keep_retry_first_in_every_mode(self):
        for mode in ("flash", "quiz", "type"):
            with self.subTest(mode=mode):
                state = self.completed(mode, wrong=[1])
                inline = buttons(bot.build_block_summary_keyboard(state))
                self.assertLessEqual(len(inline), 3)
                self.assertEqual(
                    inline[0].callback_data,
                    f"bretry:{state['block_session']}",
                )

    def test_reinforcement_copy_exists_for_every_interface_locale(self):
        for locale in INTERFACE_LOCALES:
            with self.subTest(locale=locale):
                self.assertTrue(translate("block_reinforce_quiz", locale).strip())
                self.assertTrue(translate("block_reinforce_written", locale).strip())


if __name__ == "__main__":
    unittest.main()
