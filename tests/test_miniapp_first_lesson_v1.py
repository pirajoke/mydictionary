from __future__ import annotations

import ast
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

import bot


ROOT = Path(__file__).resolve().parents[1]
HTML = (ROOT / "mydictionary/templates/miniapp.html").read_text(encoding="utf-8")
JS = (ROOT / "mydictionary/static/miniapp.js").read_text(encoding="utf-8")
MINIAPP_SOURCE = (ROOT / "mydictionary/miniapp.py").read_text(encoding="utf-8")


def miniapp_copy() -> dict[str, dict[str, str]]:
    tree = ast.parse(MINIAPP_SOURCE)
    for statement in tree.body:
        if (
            isinstance(statement, ast.AnnAssign)
            and isinstance(statement.target, ast.Name)
            and statement.target.id == "MINIAPP_COPY"
        ):
            return ast.literal_eval(statement.value)
    raise AssertionError("MINIAPP_COPY is missing")


class MiniAppFirstLessonEntryContractTest(unittest.IsolatedAsyncioTestCase):
    def test_ac1_profile_leads_with_one_real_lesson_action(self):
        daily_quest = HTML.index('id="daily-quest"')
        level = HTML.index('id="profile-game-progress"')
        achievements = HTML.index('id="profile-achievements"')
        self.assertLess(daily_quest, level)
        self.assertLess(daily_quest, achievements)
        self.assertIn('id="daily-quest-action"', HTML)
        self.assertIn('data-action="continue"', HTML)
        self.assertIn('id="first-lesson-hint"', HTML)

    def test_ac2_zero_session_profile_uses_first_lesson_copy_then_continue_copy(self):
        self.assertIn('progress.sessions === 0', JS)
        self.assertIn('copy.start_first_lesson', JS)
        self.assertIn('copy.first_lesson_hint', JS)
        self.assertIn('copy.continue_lesson', JS)
        self.assertIn('node("daily-quest-action")', JS)
        self.assertIn('node("first-lesson-hint")', JS)

        copy = miniapp_copy()
        self.assertEqual(set(copy), {"en", "fr", "de", "ja", "ar", "zh", "ru", "es"})
        for locale, values in copy.items():
            with self.subTest(locale=locale):
                self.assertTrue(str(values.get("start_first_lesson", "")).strip())
                self.assertTrue(str(values.get("first_lesson_hint", "")).strip())
                self.assertNotEqual(
                    values["start_first_lesson"].casefold(),
                    values["continue_lesson"].casefold(),
                )

    def test_ac3_all_lesson_ctas_use_continue_not_topic_picker(self):
        self.assertNotIn('data-action="learn" data-i18n="continue_lesson"', HTML)
        self.assertNotIn('data-action="learn" data-i18n="start_lesson"', HTML)
        self.assertIn('data-action="continue" data-i18n="continue_lesson"', HTML)
        self.assertIn('data-action="continue" data-i18n="start_lesson"', HTML)
        self.assertIn('"continue": "miniapp_continue"', MINIAPP_SOURCE)

    def test_ac4_continue_deep_link_is_bounded_and_routes_to_real_lesson(self):
        self.assertEqual(bot.miniapp_start_action("miniapp_continue"), "continue")
        self.assertIsNone(bot.miniapp_start_action("miniapp_continue_extra"))

    async def test_ac4_continue_route_clears_payload_and_calls_continue_only(self):
        continue_call = AsyncMock()
        learn_call = AsyncMock()
        continue_handler = SimpleNamespace(__wrapped__=continue_call)
        learn_handler = SimpleNamespace(__wrapped__=learn_call)
        message = SimpleNamespace(reply_text=AsyncMock())
        update = SimpleNamespace(effective_message=message)
        context = SimpleNamespace(args=["miniapp_continue"], user_data={})
        runtime = SimpleNamespace(role="learner", user_id=7001, store=object())
        token = bot._ACTIVE_RUNTIME.set(runtime)
        try:
            with (
                patch.object(bot, "cmd_continue", continue_handler),
                patch.object(bot, "cmd_learn", learn_handler),
                patch.object(bot, "SAFETY_SETTINGS", SimpleNamespace(enabled=False)),
            ):
                await bot.route_miniapp_start_action("continue", update, context)
        finally:
            bot._ACTIVE_RUNTIME.reset(token)

        continue_call.assert_awaited_once_with(update, context)
        learn_call.assert_not_awaited()
        self.assertEqual(context.args, ["miniapp_continue"])


if __name__ == "__main__":
    unittest.main()
