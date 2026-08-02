import json
import re
import unittest
from pathlib import Path

from vocabulary_topics import (
    JA_ROMAJI,
    TOPIC_LABELS,
    topic_counts,
    topics_for_word,
    transcription_for,
)


ROOT = Path(__file__).resolve().parents[1]
LANG_FILES = {
    "en": "words.json",
    "vi": "words_vi.json",
    "ja": "words_ja.json",
}


class VocabularyTopicsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dictionaries = {
            lang: json.loads((ROOT / filename).read_text(encoding="utf-8"))
            for lang, filename in LANG_FILES.items()
        }

    def test_every_japanese_word_has_ascii_romaji(self):
        japanese_terms = {word["en"] for word in self.dictionaries["ja"]}
        self.assertEqual(set(JA_ROMAJI), japanese_terms)
        for word in self.dictionaries["ja"]:
            romaji = transcription_for(word, "ja")
            with self.subTest(term=word["en"]):
                self.assertRegex(romaji, r"^[a-z ]+$")

    def test_every_word_has_valid_topic(self):
        for lang, words in self.dictionaries.items():
            for word in words:
                topics = topics_for_word(word, lang)
                with self.subTest(lang=lang, term=word["en"]):
                    self.assertTrue(topics)
                    self.assertTrue(set(topics).issubset(TOPIC_LABELS))

    def test_each_language_offers_multiple_topics(self):
        for lang, words in self.dictionaries.items():
            counts = topic_counts(words, lang)
            with self.subTest(lang=lang):
                self.assertGreaterEqual(len(counts), 8)
                self.assertTrue(all(count > 0 for count in counts.values()))

    def test_topic_callback_ids_fit_telegram_limit(self):
        for lang in LANG_FILES:
            for topic in TOPIC_LABELS:
                callback_data = f"ltopic:{lang}:{topic}"
                self.assertLessEqual(len(callback_data.encode()), 64)


if __name__ == "__main__":
    unittest.main()
