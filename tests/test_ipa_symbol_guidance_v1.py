from __future__ import annotations

import os
import re
import unittest
from unittest.mock import patch


os.environ.setdefault("BOT_TOKEN", "123456:TESTTOKEN_ABCDEFGHIJKLMNOP")
os.environ.setdefault("ALLOWED_USER_ID", "1")
os.environ.setdefault("ALLOW_SQLITE_DEV", "true")

import bot
from mydictionary.localization import INTERFACE_LOCALES


class IPASymbolGuidanceV1Test(unittest.TestCase):
    pack = bot.CATALOG.require("de-basics-100")

    def render_cards(self, word: dict[str, str], locale: str) -> dict[str, str]:
        user_data = {
            "interface_locale": locale,
            "block_indices": [0],
            "block_pos": 0,
        }
        with (
            patch.object(bot, "W", return_value=[word]),
            patch.object(bot, "active_content_pack", return_value=self.pack),
            patch.object(bot, "active_meaning_flag", return_value="🇷🇺"),
            patch.object(bot, "meaning_display_for_word", return_value="грустный"),
            patch.object(bot, "card_topic_visual", return_value="🌧️"),
            patch.object(bot, "get_example", return_value=""),
        ):
            return {
                "front": bot.format_learning_card_front(user_data, 0),
                "revealed": bot.format_learning_card_back(user_data, 0),
            }

    @staticmethod
    def guidance_lines(rendered: str) -> list[str]:
        return [
            line.strip()
            for line in rendered.splitlines()
            if line.strip().startswith("ʁ")
        ]

    def test_repeated_throat_r_gets_one_localized_hint_on_normal_cards(self):
        word = {
            "target": "traurig",
            "meaning": "грустный",
            "transcription": "/ˈtʁaʊʁɪç/",
        }
        failures: list[str] = []
        hints_by_locale: dict[str, str] = {}

        for locale in sorted(INTERFACE_LOCALES):
            cards = self.render_cards(word, locale)
            surface_hints: list[str] = []
            for surface, rendered in cards.items():
                if rendered.count("*traurig*") != 1:
                    failures.append(f"{locale}/{surface}: target is not separately bold")
                if rendered.count("`/ˈtʁaʊʁɪç/`") != 1:
                    failures.append(f"{locale}/{surface}: exact IPA is not preserved once")
                hints = self.guidance_lines(rendered)
                if len(hints) != 1:
                    failures.append(
                        f"{locale}/{surface}: expected one ʁ hint, got {hints!r}"
                    )
                else:
                    surface_hints.append(hints[0])
            if len(surface_hints) == 2:
                if surface_hints[0] != surface_hints[1]:
                    failures.append(f"{locale}: front/revealed hints disagree")
                else:
                    hints_by_locale[locale] = surface_hints[0]

        self.assertEqual(failures, [])
        self.assertEqual(set(hints_by_locale), set(INTERFACE_LOCALES))
        self.assertEqual(
            len(set(hints_by_locale.values())),
            len(INTERFACE_LOCALES),
            "ʁ guidance silently falls back instead of localizing",
        )
        english_hint = hints_by_locale["en"].casefold()
        self.assertRegex(english_hint, r"throat")
        self.assertRegex(english_hint, r"\br\b")

    def test_card_without_throat_r_has_no_symbol_guidance(self):
        word = {
            "target": "bitte",
            "meaning": "пожалуйста",
            "transcription": "/ˈbɪtə/",
        }
        cards = self.render_cards(word, "en")

        for surface, rendered in cards.items():
            with self.subTest(surface=surface):
                self.assertEqual(rendered.count("*bitte*"), 1)
                self.assertEqual(rendered.count("`/ˈbɪtə/`"), 1)
                self.assertEqual(self.guidance_lines(rendered), [])
                self.assertNotRegex(rendered.casefold(), re.compile(r"throat(?:y)?\s+r"))


if __name__ == "__main__":
    unittest.main()
