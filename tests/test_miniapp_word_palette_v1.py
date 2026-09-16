from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
HTML = (ROOT / "mydictionary/templates/miniapp.html").read_text(encoding="utf-8")
CSS = (ROOT / "mydictionary/static/miniapp.css").read_text(encoding="utf-8")


class MiniAppWordPaletteV1ContractTest(unittest.TestCase):
    def test_words_panel_exposes_one_lexi_accent_system(self):
        self.assertIn("--words-accent: var(--lexi-orange);", CSS)
        self.assertIn("--words-accent-soft:", CSS)
        self.assertIn("--words-accent-line:", CSS)
        self.assertIn(".swipe-modes button[aria-pressed=\"true\"] { background: var(--words-accent);", CSS)
        self.assertIn(".word-library-tab[aria-selected=\"true\"]", CSS)
        self.assertIn("background: var(--words-accent-soft);", CSS)

    def test_primary_practice_action_precedes_secondary_add_action(self):
        practice = HTML.index('data-action="practice_custom"')
        add = HTML.index('data-action="add_words"')
        self.assertLess(practice, add)
        self.assertIn(".custom-vocabulary-practice {", CSS)
        self.assertIn("background: var(--words-accent);", CSS)

    def test_words_surface_avoids_competing_decorative_accents(self):
        self.assertNotIn("linear-gradient(145deg, #ffd166, #ff914d)", CSS)
        self.assertNotIn("linear-gradient(145deg, #83ead8, #46c4b3)", CSS)
        self.assertNotIn(".swipe-know { background: var(--lexi-teal)", CSS)
        self.assertNotIn(".custom-word-card { border-inline-start:", CSS)
        self.assertIn(".swipe-again { color: var(--danger);", CSS)


if __name__ == "__main__":
    unittest.main()
