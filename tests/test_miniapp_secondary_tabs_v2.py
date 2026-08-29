from pathlib import Path
import unittest

from mydictionary.miniapp import MINIAPP_COPY


ROOT = Path(__file__).resolve().parents[1]
HTML_PATH = ROOT / "mydictionary/templates/miniapp.html"
CSS_PATH = ROOT / "mydictionary/static/miniapp.css"
JS_PATH = ROOT / "mydictionary/static/miniapp.js"


class MiniAppSecondaryTabsV2ContractTest(unittest.TestCase):
    def setUp(self):
        self.html = HTML_PATH.read_text(encoding="utf-8")
        self.css = CSS_PATH.read_text(encoding="utf-8")
        self.js = JS_PATH.read_text(encoding="utf-8")

    def test_ac1_words_have_bounded_overview_and_structured_rows(self):
        for token in (
            'id="word-summary"',
            'class="word-overview"',
            'main.className = "word-card-main"',
            'attempts.className = "word-attempts"',
            'data.words.filter((word) => word.learned).length',
            'data.words.filter((word) => word.due).length',
            'summaryStat(copy.metric_tracked_words',
            'summaryStat(copy.metric_learned_words',
            'summaryStat(copy.word_review',
        ):
            with self.subTest(token=token):
                self.assertIn(token, f"{self.html}\n{self.js}")

    def test_ac2_ac3_credits_use_wallet_hierarchy_and_honest_packages(self):
        for token in (
            'class="wallet-card"',
            'id="wallet-available"',
            'id="credit-summary" class="wallet-secondary"',
            'class="credit-contract"',
            'class="checkout-state dashboard-state disabled"',
            'button.className = "product-card"',
            'product-card-copy',
            'product-card-price',
            'button.disabled = !data.features.stars_checkout',
            'node("checkout-disabled").hidden = data.features.stars_checkout',
        ):
            with self.subTest(token=token):
                self.assertIn(token, f"{self.html}\n{self.js}")
        self.assertNotIn("window.location", self.js)

    def test_ac4_current_language_is_spotlighted_without_losing_direction_or_count(self):
        for token in (
            'id="language-current"',
            'class="language-spotlight"',
            'data.languages.find((language) => language.current)',
            'data.languages.filter((language) => !language.current)',
            'card.dir = language.direction',
            'languageDisplayLabel(language)',
            r'.replace(/\s*·\s*\d+\s*$/u, "")',
            'language.word_count',
            'copy.language_current',
        ):
            with self.subTest(token=token):
                self.assertIn(token, f"{self.html}\n{self.js}")

    def test_ac5_settings_are_grouped_and_group_copy_is_complete(self):
        groups = (
            ("learning", "settings_group_learning"),
            ("tutor", "settings_group_tutor"),
            ("features", "settings_group_features"),
        )
        for group, copy_key in groups:
            with self.subTest(group=group):
                self.assertIn(f'id="settings-{group}"', self.html)
                self.assertIn(f'data-i18n="{copy_key}"', self.html)
                self.assertIn(f'node("settings-{group}")', self.js)
                for locale, copy in MINIAPP_COPY.items():
                    self.assertIn(copy_key, copy, f"{locale} missing {copy_key}")
                    self.assertTrue(copy[copy_key].strip())

    def test_ac6_design_is_compact_local_responsive_and_motion_safe(self):
        for selector in (
            ".word-overview",
            ".wallet-card",
            ".product-card",
            ".language-spotlight",
            ".settings-group",
            "@media (max-width: 359px)",
            "@media (prefers-reduced-motion: reduce)",
            "min-height: 44px",
        ):
            with self.subTest(selector=selector):
                self.assertIn(selector, self.css)
        self.assertEqual(self.html.count('class="section-art"'), 3)
        self.assertNotIn("http://", f"{self.html}\n{self.css}\n{self.js}")
        self.assertEqual(
            self.html.count("https://"),
            1,
            "only the pinned Telegram Web App SDK may be remote",
        )


if __name__ == "__main__":
    unittest.main()
