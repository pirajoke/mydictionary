"""Behavior contract for interactive AI-chat quizzes in native Telegram."""

from copy import deepcopy
import os
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, MagicMock, patch


os.environ.setdefault("BOT_TOKEN", "123456:TESTTOKEN_ABCDEFGHIJKLMNOP")
os.environ.setdefault("ALLOWED_USER_ID", "1")
os.environ.setdefault("ALLOW_SQLITE_DEV", "true")

import bot
from mydictionary import ai_tutor
from mydictionary import mirror_assistant
from mydictionary.localization import INTERFACE_LOCALES, translate


USER_ID = 882701
ROOT = Path(__file__).resolve().parents[1]


def flattened(markup):
    return [button for row in markup.inline_keyboard for button in row]


class InteractiveQuizContractTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.pack = bot.CATALOG.require("en-basics-100")
        self.words = deepcopy(bot.CATALOG.words(self.pack))
        for word in self.words:
            word.setdefault("correct_count", 0)
            word.setdefault("wrong_count", 0)
            word.setdefault("last_seen", None)
            word.setdefault("next_review", None)

    def surface(self, *, locale="ru"):
        message = SimpleNamespace(
            chat_id=USER_ID,
            text="",
            reply_text=AsyncMock(),
        )
        query = SimpleNamespace(
            data="aitutor:quiz",
            answer=AsyncMock(),
            message=message,
        )
        update = SimpleNamespace(
            callback_query=query,
            message=message,
            effective_message=message,
            effective_user=SimpleNamespace(
                id=USER_ID,
                language_code=locale,
                first_name="Learner",
            ),
            effective_chat=SimpleNamespace(id=USER_ID),
        )
        context = SimpleNamespace(
            user_data={"interface_locale": locale},
            bot=SimpleNamespace(),
        )
        return update, context, query, message

    async def test_ac1_quiz_starter_opens_native_test_without_ai_generation(self):
        update, context, query, _message = self.surface()
        starter = AsyncMock()
        mirror = AsyncMock()
        with (
            patch.object(bot, "start_ai_chat_quiz", new=starter),
            patch.object(bot, "handle_mirror_question", new=mirror),
            patch.object(bot, "AI_SETTINGS", SimpleNamespace(enabled=True)),
        ):
            await bot.ai_tutor_entry_cb.__wrapped__(update, context)

        query.answer.assert_awaited_once_with()
        starter.assert_awaited_once_with(query.message, context, source="ai_starter")
        mirror.assert_not_awaited()

    def test_ac2_explicit_quiz_intent_is_narrow_and_multilingual(self):
        requests = {
            "en": "quiz me",
            "fr": "fais-moi un quiz",
            "de": "mach einen test mit mir",
            "ja": "クイズを出して",
            "ar": "اختبرني",
            "zh": "考考我",
            "ru": "давай тест",
            "es": "hazme un quiz",
        }
        self.assertEqual(set(requests), set(INTERFACE_LOCALES))
        for locale, text in requests.items():
            with self.subTest(locale=locale):
                self.assertEqual(
                    mirror_assistant.direct_mirror_quiz_locale(text), locale
                )
        for ordinary in (
            "объясни порядок прилагательных",
            "what is spaced repetition?",
            "как мой прогресс",
        ):
            self.assertIsNone(mirror_assistant.direct_mirror_quiz_locale(ordinary))

    async def test_ac3_ec1_native_quiz_prefers_active_due_then_fills_to_five(self):
        update, context, _query, message = self.surface()
        bot.reset_block_state(
            context.user_data,
            [8, 9],
            self.pack.target_language,
            None,
            self.pack.pack_id,
        )
        with (
            patch.object(bot, "W", return_value=self.words),
            patch.object(bot, "active_content_pack", return_value=self.pack),
            patch.object(bot, "due_word_indices", return_value=[9, 2, 3]),
            patch.object(bot, "pick_block", return_value=[3, 4, 5, 6, 7]),
            patch.object(bot, "persist_native_block", return_value=True),
            patch.object(bot, "record_product_event"),
            patch.object(bot, "send_pronunciation", new=AsyncMock()),
        ):
            await bot.start_ai_chat_quiz(message, context, source="natural_request")

        self.assertEqual(context.user_data["block_indices"], [8, 9, 2, 3, 4])
        self.assertEqual(context.user_data["block_mode"], "quiz")
        self.assertEqual(context.user_data["lesson_kind"], "ai_quiz")
        self.assertEqual(message.reply_text.await_count, 2)
        intro = message.reply_text.await_args_list[0]
        self.assertEqual(
            intro.args[0],
            translate("ai_quiz_intro", "ru", count=5),
        )
        question = message.reply_text.await_args_list[1]
        answers = [
            button
            for button in flattened(question.kwargs["reply_markup"])
            if str(button.callback_data or "").startswith("bquiz:")
        ]
        self.assertEqual(len(answers), 4)

    def test_ac4_questions_alternate_meaning_and_target_recall(self):
        state = {"interface_locale": "ru"}
        indices = [0, 1, 2, 3, 4]
        bot.reset_block_state(
            state,
            indices,
            self.pack.target_language,
            None,
            self.pack.pack_id,
            lesson_kind="ai_quiz",
        )
        bot.start_block_attempt(state, "quiz")
        with (
            patch.object(bot, "W", return_value=self.words),
            patch.object(bot, "active_content_pack", return_value=self.pack),
        ):
            first_prompt = bot.format_block_quiz_question(state, indices[0])
            first_buttons = flattened(
                bot.build_block_quiz_keyboard(state, indices[0])
            )
            state["block_pos"] = 1
            second_prompt = bot.format_block_quiz_question(state, indices[1])
            second_buttons = flattened(
                bot.build_block_quiz_keyboard(state, indices[1])
            )

        self.assertIn(bot.target_text(self.words[indices[0]]), first_prompt)
        self.assertIn(
            bot.primary_meaning_for_word(self.words[indices[1]]), second_prompt
        )
        self.assertIn(translate("ai_quiz_choose_word", "ru"), second_prompt)
        self.assertIn(
            bot.target_text(self.words[indices[1]]),
            [button.text for button in second_buttons],
        )
        self.assertIn(
            bot.primary_meaning_for_word(self.words[indices[0]]),
            [button.text for button in first_buttons],
        )

    def test_ac6_result_card_lists_every_answer_and_next_actions(self):
        state = {"interface_locale": "ru"}
        indices = [0, 1, 2, 3, 4]
        bot.reset_block_state(
            state,
            indices,
            self.pack.target_language,
            None,
            self.pack.pack_id,
            lesson_kind="ai_quiz",
        )
        bot.start_block_attempt(state, "quiz")
        state.update(block_pos=5, block_correct=3, block_wrong=[1, 3])
        progress = {
            "xp": 0,
            "today_xp": 0,
            "sessions": 0,
            "streak": 0,
            "active_lang": "en",
            "active_pack_id": self.pack.pack_id,
        }
        with (
            patch.object(bot, "W", return_value=self.words),
            patch.object(bot, "PROGRESS", progress),
            patch.object(bot, "active_content_pack", return_value=self.pack),
            patch.object(bot, "save_progress"),
        ):
            rendered = bot.format_block_summary(state)
            buttons = flattened(bot.build_block_summary_keyboard(state))

        self.assertIn(translate("ai_quiz_review_title", "ru"), rendered)
        self.assertEqual(rendered.count("\n✅"), 3)
        self.assertEqual(rendered.count("\n❌"), 2)
        for index in indices:
            self.assertIn(bot.target_text(self.words[index]), rendered)
            self.assertIn(bot.primary_meaning_for_word(self.words[index]), rendered)
        callbacks = {button.callback_data for button in buttons}
        self.assertIn(f"bretry:{state['block_session']}", callbacks)
        self.assertIn("aitutor:quiz", callbacks)
        self.assertIn("aitutor:ask", callbacks)

    def test_localized_interactive_quiz_copy_is_complete(self):
        keys = (
            "ai_quiz_intro",
            "ai_quiz_choose_word",
            "ai_quiz_review_title",
            "ai_quiz_new",
            "ai_quiz_discuss",
        )
        for locale in INTERFACE_LOCALES:
            for key in keys:
                with self.subTest(locale=locale, key=key):
                    values = {"count": 5} if key == "ai_quiz_intro" else {}
                    self.assertNotEqual(translate(key, locale, **values), key)

    def test_ac8_active_prompt_requires_non_repeating_exercise_variety(self):
        active = ROOT / "prompts" / "mirror-v10.txt"
        historical = ROOT / "prompts" / "mirror-v9.txt"
        self.assertTrue(active.is_file())
        self.assertTrue(historical.is_file())
        reviewed = active.read_text(encoding="utf-8").removesuffix("\n")
        self.assertEqual(ai_tutor.MIRROR_INSTRUCTIONS, reviewed)
        normalized = " ".join(reviewed.casefold().split())
        for required in (
            "short dialogue",
            "multiple choice",
            "cloze",
            "word ordering",
            "correction",
            "free response",
            "do not repeat the immediately preceding exercise form",
        ):
            self.assertIn(required, normalized)


if __name__ == "__main__":
    unittest.main()
