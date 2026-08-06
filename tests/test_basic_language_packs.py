from collections import Counter
from pathlib import Path
import re
import subprocess
import sys
import unittest
import unicodedata

from mydictionary.catalog import load_catalog
from mydictionary.content import (
    accepted_meanings,
    meaning_text,
    speech_text,
    target_text,
    transcription_text,
)
from vocabulary_topics import topics_for_word, transcription_for


ROOT = Path(__file__).resolve().parents[1]
BASIC_PACKS = {
    "en-basics-100": "en",
    "fr-basics-100": "fr",
    "de-basics-100": "de",
    "ja-basics-100": "ja",
    "ar-basics-100": "ar",
    "zh-basics-100": "zh",
    "ru-basics-100": "ru",
    "es-basics-100": "es",
}
GENERATED_PACKS = BASIC_PACKS.keys() - {"ja-basics-100"}
EXPECTED_TOPICS = {
    "greetings",
    "people",
    "food",
    "home",
    "travel",
    "time",
    "work",
    "health",
    "actions",
    "descriptions",
}
EXPECTED_VOICES = {
    "en-basics-100": ("en-US", "en-US-AriaNeural"),
    "fr-basics-100": ("fr-FR", "fr-FR-DeniseNeural"),
    "de-basics-100": ("de-DE", "de-DE-KatjaNeural"),
    "ja-basics-100": ("ja-JP", "ja-JP-NanamiNeural"),
    "ar-basics-100": ("ar-SA", "ar-SA-ZariyahNeural"),
    "zh-basics-100": ("zh-CN", "zh-CN-XiaoxiaoNeural"),
    "ru-basics-100": ("ru-RU", "ru-RU-SvetlanaNeural"),
    "es-basics-100": ("es-ES", "es-ES-ElviraNeural"),
}
IPA_PACKS = {"en-basics-100", "fr-basics-100", "de-basics-100", "es-basics-100"}
ARABIC_RE = re.compile(r"[\u0600-\u06ff\u0750-\u077f\u08a0-\u08ff]")
HAN_RE = re.compile(r"[\u3400-\u9fff]")
CYRILLIC_RE = re.compile(r"[\u0400-\u052f]")


def has_latin_letter(value: str) -> bool:
    return any(
        character.isalpha()
        and unicodedata.name(character, "").startswith("LATIN")
        for character in value
    )


class BasicLanguagePacksTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = load_catalog(ROOT)

    def test_exactly_eight_free_basic_languages_are_published(self):
        basic_100_ids = {
            pack.pack_id
            for pack in self.catalog.visible_packs("learner")
            if pack.pack_id.endswith("-basics-100")
        }
        self.assertEqual(basic_100_ids, set(BASIC_PACKS))
        actual = {
            pack.pack_id: pack.target_language
            for pack in self.catalog.visible_packs("learner")
            if pack.pack_id in BASIC_PACKS
        }
        self.assertEqual(actual, BASIC_PACKS)
        for pack_id in BASIC_PACKS:
            pack = self.catalog.require(pack_id)
            with self.subTest(pack=pack_id):
                self.assertEqual(pack.visibility, "public")
                self.assertTrue(pack.is_free)
                self.assertEqual(pack.status, "published")
                self.assertEqual(pack.entry_count, 100)
        self.assertEqual(
            len({self.catalog.require(pack_id).label for pack_id in BASIC_PACKS}),
            8,
        )

    def test_every_entry_has_complete_learning_and_audio_content(self):
        for pack_id, language in BASIC_PACKS.items():
            pack = self.catalog.require(pack_id)
            words = self.catalog.words(pack)
            self.assertEqual(len(words), 100)
            targets = set()
            entry_ids = set()
            for word in words:
                with self.subTest(pack=pack_id, entry=word["entry_id"]):
                    self.assertTrue(target_text(word))
                    self.assertTrue(meaning_text(word))
                    self.assertTrue(transcription_for(word, language))
                    self.assertTrue(speech_text(word))
                    self.assertTrue(topics_for_word(word, language))
                    targets.add(target_text(word).casefold())
                    entry_ids.add(word["entry_id"])
            self.assertEqual(len(targets), 100)
            self.assertEqual(len(entry_ids), 100)

    def test_aligned_generated_packs_have_ten_entries_per_topic(self):
        expected_counts = Counter({topic: 10 for topic in EXPECTED_TOPICS})
        expected_entry_ids = None
        for pack_id in GENERATED_PACKS:
            pack = self.catalog.require(pack_id)
            words = self.catalog.words(pack)
            counts = Counter(topic for word in words for topic in word["topics"])
            entry_ids = [word["entry_id"] for word in words]
            with self.subTest(pack=pack_id):
                self.assertEqual(counts, expected_counts)
                if expected_entry_ids is None:
                    expected_entry_ids = entry_ids
                else:
                    self.assertEqual(entry_ids, expected_entry_ids)

    def test_meanings_are_russian_and_not_copies_of_targets(self):
        for pack_id in BASIC_PACKS:
            pack = self.catalog.require(pack_id)
            for word in self.catalog.words(pack):
                meaning = meaning_text(word)
                with self.subTest(pack=pack_id, entry=word["entry_id"]):
                    self.assertRegex(meaning, CYRILLIC_RE)
                    self.assertNotEqual(target_text(word).casefold(), meaning.casefold())

    def test_transcription_systems_match_each_script(self):
        for pack_id in IPA_PACKS:
            pack = self.catalog.require(pack_id)
            for word in self.catalog.words(pack):
                transcription = transcription_text(word)
                with self.subTest(pack=pack_id, entry=word["entry_id"]):
                    self.assertTrue(transcription.startswith("/"))
                    self.assertTrue(transcription.endswith("/"))

        script_checks = {
            "ar-basics-100": ARABIC_RE,
            "zh-basics-100": HAN_RE,
            "ru-basics-100": CYRILLIC_RE,
        }
        for pack_id, forbidden_script in script_checks.items():
            pack = self.catalog.require(pack_id)
            for word in self.catalog.words(pack):
                transcription = transcription_text(word)
                with self.subTest(pack=pack_id, entry=word["entry_id"]):
                    self.assertFalse(forbidden_script.search(transcription))
                    self.assertTrue(has_latin_letter(transcription))

    def test_each_basic_pack_has_the_declared_tts_voice(self):
        for pack_id, (locale, voice) in EXPECTED_VOICES.items():
            pronunciation = self.catalog.require(pack_id).pronunciation
            with self.subTest(pack=pack_id):
                self.assertEqual(pronunciation.tts_locale, locale)
                self.assertEqual(pronunciation.tts_voice, voice)
                self.assertEqual(pronunciation.tts_rate, "-25%")

    def test_french_bonjour_has_a_clear_primary_and_curated_answers(self):
        pack = self.catalog.require("fr-basics-100")
        word = next(
            word for word in self.catalog.words(pack)
            if target_text(word) == "bonjour"
        )

        self.assertEqual(meaning_text(word), "здравствуйте")
        self.assertEqual(
            accepted_meanings(word),
            ("здравствуйте", "добрый день", "доброе утро"),
        )

    def test_generated_pack_files_match_the_source_matrix(self):
        result = subprocess.run(
            [sys.executable, "scripts/build_basic_packs.py", "--check"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
