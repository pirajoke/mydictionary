from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]


class MiniAppNavigationIllustrationsV2ContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = (ROOT / "mydictionary/templates/miniapp.html").read_text(
            encoding="utf-8"
        )
        cls.css = (ROOT / "mydictionary/static/miniapp.css").read_text(
            encoding="utf-8"
        )

    def test_ac1_each_tab_has_one_named_vector_illustration(self):
        icons = re.findall(
            r'<svg class="nav-glyph" data-icon="([a-z-]+)"[^>]*>',
            self.html,
        )
        self.assertEqual(
            icons,
            ["profile", "words", "credits", "languages", "settings"],
        )
        self.assertEqual(self.html.count('viewBox="0 0 24 24"'), 5)
        navigation = self.html.split('<nav class="bottom-nav"', 1)[1]
        for legacy_glyph in (">●</span>", ">◆</span>", ">★</span>", ">◎</span>", ">✦</span>"):
            with self.subTest(legacy_glyph=legacy_glyph):
                self.assertNotIn(legacy_glyph, navigation)

    def test_ac2_icons_share_a_richer_two_tone_badge_language(self):
        self.assertGreaterEqual(self.html.count('class="icon-soft"'), 5)
        for contract in (
            ".nav-glyph",
            ".icon-soft",
            "inset 0 1px 0 rgba(255, 255, 255, .34)",
            ".bottom-nav button[aria-selected=\"true\"]::after",
        ):
            with self.subTest(contract=contract):
                self.assertIn(contract, self.css)

    def test_ac3_vectors_are_decorative_and_existing_tab_contract_survives(self):
        self.assertEqual(self.html.count('aria-hidden="true" focusable="false"'), 5)
        self.assertEqual(self.html.count('role="tab"'), 5)
        self.assertGreaterEqual(self.html.count('data-i18n="'), 32)
        self.assertIn("min-height: 58px", self.css)
        self.assertIn("@media (prefers-reduced-motion: reduce)", self.css)


if __name__ == "__main__":
    unittest.main()
