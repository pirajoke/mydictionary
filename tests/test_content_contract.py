import json
from pathlib import Path
import tempfile
import unittest

from mydictionary.catalog import CatalogError, load_catalog
from mydictionary.content import (
    content_progress_id,
    legacy_progress_id,
    meaning_text,
    speech_text,
    target_text,
    vocabulary_progress_id,
)
from vocabulary_topics import topics_for_word, transcription_for


ROOT = Path(__file__).resolve().parents[1]


def pack_metadata(**overrides):
    values = {
        "pack_id": "ar-basics-100",
        "target_language": "ar",
        "meaning_language": "ru",
        "direction": "rtl",
        "flag": "🇸🇦",
        "meaning_flag": "🇷🇺",
        "label": "🇸🇦 العربية",
        "title": "Арабский: базовые слова",
        "description": "Проверочный универсальный набор.",
        "filename": "words_ar.json",
        "storage_key": "ar",
        "visibility": "public",
        "is_free": True,
        "status": "published",
        "content_schema": 2,
        "content_version": 1,
        "entry_count": 1,
        "pronunciation": {
            "transcription_system": "learner-latin",
            "transcription_position": "before",
            "tts_locale": "ar-SA",
            "tts_voice": "ar-SA-ZariyahNeural",
            "tts_rate": "-25%",
        },
    }
    values.update(overrides)
    return values


def arabic_entry(**overrides):
    values = {
        "entry_id": "hello",
        "target": "مرحبا",
        "meaning": "привет",
        "transcription": "marhaban",
        "speech": "مَرْحَبًا",
        "topics": ["greetings"],
        "example": {
            "target": "مرحبا يا صديقي",
            "meaning": "привет, мой друг",
        },
    }
    values.update(overrides)
    return values


class TemporaryCatalog:
    def __init__(self):
        self.temp_dir = tempfile.TemporaryDirectory(
            prefix="mydictionary-content-contract-"
        )
        self.root = Path(self.temp_dir.name)
        (self.root / "content").mkdir()

    def close(self):
        self.temp_dir.cleanup()

    def write(self, *, pack=None, entry=None):
        pack = pack or pack_metadata()
        entry = entry or arabic_entry()
        catalog = {
            "schema_version": 2,
            "topics": [
                {"topic_id": "greetings", "label": "Приветствия"},
                {"topic_id": "general", "label": "Разное"},
            ],
            "packs": [pack],
        }
        (self.root / "content" / "catalog.json").write_text(
            json.dumps(catalog, ensure_ascii=False), encoding="utf-8"
        )
        (self.root / pack["filename"]).write_text(
            json.dumps(
                {"schema_version": 2, "entries": [entry]},
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        return load_catalog(self.root)


class ContentContractV2Test(unittest.TestCase):
    def setUp(self):
        self.fixture = TemporaryCatalog()

    def tearDown(self):
        self.fixture.close()

    def test_generic_rtl_entry_exposes_canonical_content_and_pack_tts(self):
        catalog = self.fixture.write()
        pack = catalog.require("ar-basics-100")
        word = catalog.words(pack)[0]

        self.assertEqual(pack.target_language, "ar")
        self.assertEqual(pack.meaning_language, "ru")
        self.assertEqual(pack.direction, "rtl")
        self.assertEqual(pack.pronunciation.tts_voice, "ar-SA-ZariyahNeural")
        self.assertEqual(target_text(word), "مرحبا")
        self.assertEqual(meaning_text(word), "привет")
        self.assertEqual(transcription_for(word, "ar"), "marhaban")
        self.assertEqual(speech_text(word), "مَرْحَبًا")
        self.assertEqual(topics_for_word(word, "ar"), ("greetings",))

    def test_v2_progress_identity_survives_text_corrections(self):
        first = self.fixture.write()
        original_id = vocabulary_progress_id(
            first.words(first.require("ar-basics-100"))[0]
        )

        revised = self.fixture.write(
            entry=arabic_entry(
                target="مَرْحَبًا",
                meaning="здравствуйте",
            )
        )
        revised_id = vocabulary_progress_id(
            revised.words(revised.require("ar-basics-100"))[0]
        )

        self.assertEqual(
            original_id,
            content_progress_id("ar-basics-100", "hello"),
        )
        self.assertEqual(revised_id, original_id)

    def test_migrated_v2_entry_can_keep_legacy_progress_identity(self):
        old_id = legacy_progress_id("こんにちは", "привет")
        catalog = self.fixture.write(
            entry=arabic_entry(legacy_progress_id=old_id)
        )
        word = catalog.words(catalog.require("ar-basics-100"))[0]

        self.assertEqual(vocabulary_progress_id(word), old_id)

    def test_examples_are_explicitly_optional(self):
        catalog = self.fixture.write(entry=arabic_entry(example=None))
        word = catalog.words(catalog.require("ar-basics-100"))[0]

        self.assertEqual(word["example_target"], "")
        self.assertEqual(word["example_meaning"], "")

    def test_loader_returns_copies_of_immutable_catalog_entries(self):
        catalog = self.fixture.write()
        pack = catalog.require("ar-basics-100")
        words = catalog.words(pack)
        words[0]["target"] = "изменено"

        self.assertEqual(target_text(catalog.words(pack)[0]), "مرحبا")

    def test_contract_rejects_missing_transcription(self):
        with self.assertRaisesRegex(CatalogError, "requires transcription"):
            self.fixture.write(entry=arabic_entry(transcription=""))

    def test_contract_rejects_unknown_topic(self):
        with self.assertRaisesRegex(CatalogError, "invalid topics"):
            self.fixture.write(entry=arabic_entry(topics=["unknown"]))

    def test_contract_rejects_control_characters(self):
        with self.assertRaisesRegex(CatalogError, "invalid text field target"):
            self.fixture.write(entry=arabic_entry(target="مرحبا\u202e"))

    def test_contract_rejects_unknown_pack_fields(self):
        pack = pack_metadata(unexpected=True)
        with self.assertRaisesRegex(CatalogError, "pack contract"):
            self.fixture.write(pack=pack)

    def test_checked_in_legacy_packs_keep_historical_progress_ids(self):
        catalog = load_catalog(ROOT)
        for pack in (
            candidate for candidate in catalog.packs if candidate.content_schema == 1
        ):
            raw_words = json.loads((ROOT / pack.filename).read_text(encoding="utf-8"))
            normalized = catalog.words(pack)
            for raw, word in zip(raw_words, normalized, strict=True):
                with self.subTest(pack=pack.pack_id, target=raw["en"]):
                    self.assertEqual(
                        vocabulary_progress_id(word),
                        legacy_progress_id(raw["en"], raw["ru"]),
                    )


if __name__ == "__main__":
    unittest.main()
