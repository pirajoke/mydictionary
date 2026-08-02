import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
JAPANESE_WORDS = ROOT / "words_ja.json"
REQUIRED_FIELDS = {
    "en",
    "ru",
    "reading",
    "example",
    "correct_count",
    "wrong_count",
    "last_seen",
    "interval",
    "next_review",
}


class JapaneseDictionaryTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.words = json.loads(JAPANESE_WORDS.read_text(encoding="utf-8"))

    def test_contains_exactly_100_words(self):
        self.assertEqual(len(self.words), 100)

    def test_terms_are_unique(self):
        terms = [word["en"] for word in self.words]
        self.assertEqual(len(terms), len(set(terms)))

    def test_entries_have_required_fields_and_initial_progress(self):
        for position, word in enumerate(self.words, start=1):
            with self.subTest(position=position, term=word.get("en")):
                self.assertEqual(set(word), REQUIRED_FIELDS)
                for field in ("en", "ru", "reading", "example"):
                    self.assertIsInstance(word[field], str)
                    self.assertTrue(word[field].strip())
                self.assertEqual(word["correct_count"], 0)
                self.assertEqual(word["wrong_count"], 0)
                self.assertEqual(word["interval"], 1)
                self.assertIsNone(word["last_seen"])
                self.assertIsNone(word["next_review"])


if __name__ == "__main__":
    unittest.main()
