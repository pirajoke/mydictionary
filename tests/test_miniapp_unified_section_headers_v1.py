from __future__ import annotations

from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
HTML = (ROOT / "mydictionary/templates/miniapp.html").read_text(encoding="utf-8")
CSS = (ROOT / "mydictionary/static/miniapp.css").read_text(encoding="utf-8")
TABS = ("profile", "words", "credits", "languages", "settings")


def css_rule(selector: str) -> str:
    match = re.search(rf"{re.escape(selector)}\s*\{{([^}}]*)\}}", CSS, re.DOTALL)
    if match is None:
        raise AssertionError(f"missing CSS rule: {selector}")
    return match.group(1)


class MiniAppUnifiedSectionHeadersV1ContractTest(unittest.TestCase):
    def test_all_five_tabs_use_the_same_title_and_landscape_art_header(self) -> None:
        violations: list[str] = []
        for tab in TABS:
            panel_start = HTML.index(f'id="panel-{tab}"')
            header = re.search(r"<header\b[^>]*>.*?</header>", HTML[panel_start:], re.DOTALL)
            self.assertIsNotNone(header, tab)
            source = header.group(0)
            classes = re.search(r'class="([^"]+)"', source).group(1).split()
            if "dashboard-header" not in classes or "section-hero" not in classes:
                violations.append(f"{tab}:shared-header")
            if f'data-i18n="{tab}"' not in source:
                violations.append(f"{tab}:title")
            if source.count('class="section-art"') != 1:
                violations.append(f"{tab}:art")

        self.assertEqual(violations, [])
        self.assertEqual(HTML.count('class="section-art"'), 5)

    def test_shared_header_keeps_title_at_top_and_art_fills_the_right_column(self) -> None:
        header = css_rule(".section-hero")
        title = css_rule(".section-hero h1")
        art = css_rule(".section-hero .section-art")

        self.assertIn("display: grid", header)
        self.assertRegex(header, r"grid-template-columns:\s*minmax\([^;]+\)\s+minmax\([^;]+\)")
        self.assertIn("align-items: start", header)
        self.assertIn("overflow: hidden", header)
        self.assertIn("align-self: start", title)
        self.assertIn("width: 100%", art)
        self.assertIn("aspect-ratio: 2 / 1", art)
        self.assertIn("object-fit: cover", art)

        self.assertNotRegex(CSS, r"\.profile-header\s*\{[^}]*min-height:\s*132px")
        self.assertNotRegex(CSS, r"\.section-art\s*\{[^}]*width:\s*(?:58|72)px")


if __name__ == "__main__":
    unittest.main()
