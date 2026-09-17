from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
HTML = (ROOT / "mydictionary/templates/miniapp.html").read_text(encoding="utf-8")
CSS = (ROOT / "mydictionary/static/miniapp.css").read_text(encoding="utf-8")
JS = (ROOT / "mydictionary/static/miniapp-swipe.js").read_text(encoding="utf-8")


class MiniAppWordsClarityV1ContractTest(unittest.TestCase):
    def test_ac1_card_modes_are_the_first_words_task(self):
        words = HTML.split('id="panel-words"', 1)[1].split('id="panel-credits"', 1)[0]
        trainer = words.index('id="swipe-trainer"')
        self.assertLess(trainer, words.index('id="custom-vocabulary-actions"'))
        self.assertLess(trainer, words.index("dictionary-entry"))
        self.assertLess(trainer, words.index("word-library"))
        self.assertEqual(words.count("data-swipe-mode="), 3)
        self.assertIn('id="swipe-mode-label"', words)
        self.assertIn('aria-labelledby="swipe-mode-label"', words)
        self.assertIn('aria-describedby="swipe-mode-help"', words)
        self.assertIn('#panel-words > header[class~="section-hero"] { display: none; }', CSS)
        self.assertIn("lexi-section-words-v1.webp') }}\" alt=\"\" loading=\"eager\"", words)

    def test_ac2_one_start_action_explains_the_selected_mode(self):
        words = HTML.split('id="panel-words"', 1)[1].split('id="panel-credits"', 1)[0]
        self.assertEqual(words.count('id="swipe-start"'), 1)
        self.assertIn('id="swipe-mode-help"', words)
        self.assertIn('copy[`${mode}_start`]', JS)
        self.assertIn('copy[`${mode}_hint`]', JS)
        self.assertIn('setText("mode-help"', JS)

    def test_ac3_secondary_tools_are_collapsed_native_disclosures(self):
        words = HTML.split('id="panel-words"', 1)[1].split('id="panel-credits"', 1)[0]
        self.assertRegex(words, r'<details\b[^>]*id="custom-vocabulary-actions"[^>]*>')
        self.assertRegex(words, r'<details\b[^>]*class="[^"]*\bdictionary-entry\b[^"]*"[^>]*>')
        self.assertRegex(words, r'<details\b[^>]*class="[^"]*\bword-library\b[^"]*"[^>]*>')
        self.assertNotRegex(words, r'<details\b[^>]*(?:\sopen(?:\s|=|>))')
        self.assertEqual(words.count("data-open-dictionary"), 1)
        self.assertEqual(words.count("data-download-dictionary"), 1)
        self.assertEqual(words.count('data-action="add_words"'), 1)
        self.assertEqual(words.count('data-action="practice_custom"'), 1)

    def test_ac4_disclosures_and_mode_state_share_words_tokens(self):
        self.assertIn(".words-disclosure", CSS)
        self.assertIn("var(--words-accent)", CSS)
        self.assertIn(".swipe-mode-help", CSS)
        self.assertIn('@media (max-width: 359px)', CSS)
        self.assertIn('[dir="rtl"]', CSS)


if __name__ == "__main__":
    unittest.main()
