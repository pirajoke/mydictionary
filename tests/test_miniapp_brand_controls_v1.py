import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CSS = (ROOT / "mydictionary/static/miniapp.css").read_text(encoding="utf-8")
HTML = (ROOT / "mydictionary/templates/miniapp.html").read_text(encoding="utf-8")


class MiniAppBrandControlsV1Tests(unittest.TestCase):
    def test_controls_use_the_lexi_palette_and_friendly_local_font_stack(self) -> None:
        for token in (
            "--lexi-orange",
            "--lexi-gold",
            "--lexi-teal",
            "--lexi-blue",
            "--lexi-violet",
        ):
            self.assertIn(token, CSS)
        self.assertRegex(CSS, r"font-family:\s*ui-rounded,\s*\"SF Pro Rounded\"")

    def test_each_navigation_action_has_a_distinct_brand_role(self) -> None:
        expected = {
            "tab-profile": "--lexi-orange",
            "tab-words": "--lexi-teal",
            "tab-credits": "--lexi-gold",
            "tab-languages": "--lexi-blue",
            "tab-settings": "--lexi-violet",
        }
        for tab_id, token in expected.items():
            self.assertRegex(
                CSS,
                rf"#{re.escape(tab_id)}\s*\{{[^}}]*--nav-color:\s*var\({re.escape(token)}\)",
            )
        self.assertRegex(
            CSS,
            r"\.bottom-nav button\[aria-selected=\"true\"\] \.nav-icon\s*\{[^}]*background:\s*var\(--nav-color\)",
        )

    def test_dictionary_shortcut_and_primary_actions_have_tactile_states(self) -> None:
        self.assertRegex(
            CSS,
            r"\.dictionary-shortcut\s*\{[^}]*--control-accent:\s*var\(--lexi-teal\)",
        )
        self.assertIn("button:not(:disabled):active", CSS)
        self.assertIn("@media (hover: hover)", CSS)
        self.assertIn("@media (prefers-reduced-motion: reduce)", CSS)

    def test_stylesheet_url_is_versioned_for_telegram_webview_cache(self) -> None:
        self.assertIn("miniapp.css') }}?v=20260908-profile-hero-v1", HTML)


if __name__ == "__main__":
    unittest.main()
