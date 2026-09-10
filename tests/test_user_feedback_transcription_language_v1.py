from __future__ import annotations

import os
from pathlib import Path
import re
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch


os.environ.setdefault("BOT_TOKEN", "123456:TESTTOKEN_ABCDEFGHIJKLMNOP")
os.environ.setdefault("ALLOWED_USER_ID", "1")
os.environ.setdefault("ALLOW_SQLITE_DEV", "true")

import bot
from mydictionary.localization import INTERFACE_LOCALES, translate


ROOT = Path(__file__).resolve().parents[1]
MINIAPP_CSS = (ROOT / "mydictionary/static/miniapp.css").read_text(encoding="utf-8")


def keyboard_labels(markup) -> list[str]:
    return [button.text for row in markup.keyboard for button in row]


class LearningCardTranscriptionFeedbackTest(unittest.TestCase):
    def test_telegram_card_separates_bold_target_from_monospace_ipa(self):
        word = {
            "target": "Herr",
            "meaning": "господин",
            "transcription": "/hɛʁ/",
        }
        pack = bot.CATALOG.require("de-basics-100")
        with (
            patch.object(bot, "W", return_value=[word]),
            patch.object(bot, "active_content_pack", return_value=pack),
            patch.object(bot, "active_meaning_flag", return_value="🇷🇺"),
            patch.object(bot, "meaning_display_for_word", return_value="господин"),
        ):
            rendered_cards = {
                "front": bot.format_word_label(0),
                "revealed": bot.format_word_details(0),
            }

        for surface, rendered in rendered_cards.items():
            with self.subTest(surface=surface):
                target = "*Herr*"
                transcription = "`/hɛʁ/`"
                self.assertIn(target, rendered)
                self.assertIn(transcription, rendered)
                separation = rendered[
                    rendered.index(target) + len(target):rendered.index(transcription)
                ]
                self.assertIn("\n", separation)
                self.assertNotRegex(rendered, r"\*[^*\n]*/hɛʁ/[^*\n]*\*")

    def test_miniapp_transcription_uses_readable_ipa_sans_typography(self):
        match = re.search(
            r"\.custom-word-transcription\s*\{(?P<body>[^}]*)\}",
            MINIAPP_CSS,
            re.DOTALL,
        )
        self.assertIsNotNone(match, "missing Mini App transcription style")
        declarations = {
            name.strip(): value.strip()
            for name, value in re.findall(
                r"([a-z-]+)\s*:\s*([^;]+);",
                match.group("body"),
            )
        }

        font_family = declarations.get("font-family", "")
        self.assertIn("sans-serif", font_family)
        self.assertRegex(
            font_family,
            r"(?:Noto Sans|DejaVu Sans|Segoe UI|Helvetica Neue|Arial)",
        )
        self.assertGreaterEqual(
            float(declarations.get("font-size", "0rem").removesuffix("rem")),
            0.8,
        )
        self.assertGreaterEqual(float(declarations.get("line-height", "0")), 1.3)
        self.assertGreaterEqual(
            float(declarations.get("margin-top", "0px").removesuffix("px")),
            4.0,
        )


class PersistentLanguageQuickActionFeedbackTest(unittest.IsolatedAsyncioTestCase):
    async def test_start_keyboard_includes_localized_language_action_in_every_locale(self):
        missing = []
        unrouted = []
        with (
            patch.object(bot, "WELCOME_BANNER_PATH") as banner,
            patch.object(bot, "get_bot_profile", return_value={}),
            patch.object(bot, "render_start_text", return_value="welcome"),
        ):
            banner.exists.return_value = False
            for locale in sorted(INTERFACE_LOCALES):
                message = SimpleNamespace(reply_text=AsyncMock())
                await bot.send_start_message(
                    message,
                    SimpleNamespace(),
                    first_name="Learner",
                    locale=locale,
                )
                labels = keyboard_labels(
                    message.reply_text.await_args.kwargs["reply_markup"]
                )
                expected = f"🌍 {translate('command_lang', locale)}"
                if labels.count(expected) != 1:
                    missing.append((locale, expected, labels))
                if bot.quick_action_for_text(expected) not in {"lang", "language"}:
                    unrouted.append((locale, expected))

        self.assertEqual({"missing": missing, "unrouted": unrouted}, {
            "missing": [],
            "unrouted": [],
        })

    async def test_language_quick_action_dispatches_cmd_lang_without_ai_fallthrough(self):
        label = f"🌍 {translate('command_lang', 'de')}"
        message = SimpleNamespace(text=label, chat_id=123, reply_text=AsyncMock())
        update = SimpleNamespace(
            message=message,
            effective_message=message,
            effective_user=SimpleNamespace(id=7, language_code="de"),
        )
        context = SimpleNamespace(user_data={"interface_locale": "de"})
        language_handler = SimpleNamespace(__wrapped__=AsyncMock())

        with (
            patch.object(bot, "cmd_lang", language_handler),
            patch.object(bot, "AI_SETTINGS", SimpleNamespace(enabled=True)),
            patch.object(bot, "send_ai_tutor_menu", new=AsyncMock()) as ai_menu,
        ):
            await bot.handle_quick_action.__wrapped__(update, context)

        language_handler.__wrapped__.assert_awaited_once_with(update, context)
        ai_menu.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
