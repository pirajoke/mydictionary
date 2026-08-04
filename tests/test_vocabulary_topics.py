import json
import re
import unittest
from pathlib import Path

from mydictionary.catalog import load_catalog
from vocabulary_topics import (
    JA_ROMAJI,
    topic_counts,
    topics_for_word,
    transcription_for,
)


ROOT = Path(__file__).resolve().parents[1]
CATALOG = load_catalog(ROOT)
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
                    self.assertTrue(
                        set(topics).issubset(CATALOG.topic_labels)
                    )

    def test_each_language_offers_multiple_topics(self):
        for lang, words in self.dictionaries.items():
            counts = topic_counts(
                words,
                lang,
                topic_labels=CATALOG.topic_labels,
            )
            with self.subTest(lang=lang):
                self.assertGreaterEqual(len(counts), 8)
                self.assertTrue(all(count > 0 for count in counts.values()))

    def test_topic_callback_ids_fit_telegram_limit(self):
        for pack in CATALOG.packs:
            for topic in CATALOG.topic_labels:
                callback_data = f"ltopic:{pack.pack_id}:{topic}"
                self.assertLessEqual(len(callback_data.encode()), 64)


if __name__ == "__main__":
    unittest.main()
