"""AC8: deterministic German editorial content and safe catalog projection."""

import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from mydictionary.catalog import load_catalog
from mydictionary.content import answer_matches, content_progress_id, vocabulary_progress_id
from scripts.build_basic_packs import SourceError, build_documents, render


ROOT = Path(__file__).resolve().parents[1]
EDITORIAL = ROOT / "content" / "german_editorial.json"

# Captured from base 990cfcd0e985894c5ae9699dd1ce1efeaa41220a. German hashes
# identity/display fields only; other packs must remain entirely unchanged.
BASE_FINGERPRINTS = {
    "words_en_basic.json": "bd7af8de4b0d39e4070d4a0752f2e1f6f40c645b50a0285ea77929a4c9300010",
    "words_fr_basic.json": "4992f429b94b57fd45ca6bed40d44922799aa0752ba40709b16f38e44495cbe4",
    "words_de_basic.json": "3d19780149d75f27ccbac661ae1ff6e84079ce82b546637978007a6d5321f740",
    "words_ar_basic.json": "a0e43306d7595df316a97dc041a0b622786ebf0480cb54f3c2ee0755284787e2",
    "words_zh_basic.json": "cd3b205ba984338fa357ca0dc4d4e0b8c3f7ae6179780261b3f7c00c640aafde",
    "words_ru_basic.json": "c7498db61a837a699b035401de6018b1491d948947696c4de02c379abd70a2e4",
    "words_es_basic.json": "164d483ed908de46c6f9786a90997e563fe280e3fdda3052518937fb019fc57e",
}


def book_overlay():
    return {
        "schema_version": 1,
        "entries": {
            "book": {
                "example": {"target": "Das Buch ist neu.", "meaning": "Книга новая."},
                "part_of_speech": "noun",
                "grammar": {"article": "das", "plural": "Bücher"},
                "accepted_meanings": ["книга", "книжка"],
            }
        },
    }


class GermanEditorialV2Test(unittest.TestCase):
    def editorial(self):
        self.assertTrue(EDITORIAL.is_file(), "AC8 requires a canonical German editorial source")
        return json.loads(EDITORIAL.read_text(encoding="utf-8"))

    def build_with_overlay(self, overlay):
        with tempfile.TemporaryDirectory(prefix="german-editorial-test-") as directory:
            path = Path(directory) / "german_editorial.json"
            path.write_text(json.dumps(overlay, ensure_ascii=False), encoding="utf-8")
            return build_documents(editorial_path=path)

    def test_ac8_all100_have_short_bilingual_examples_and_relevant_grammar(self):
        entries = build_documents()["words_de_basic.json"]["entries"]
        self.assertEqual(len(entries), 100)
        self.assertEqual(
            sum(isinstance(entry["example"], dict) for entry in entries), 100,
            "all German starter entries require bilingual examples",
        )
        for entry in entries:
            with self.subTest(entry=entry["entry_id"]):
                self.assertIsInstance(entry["example"], dict)
                for language in ("target", "meaning"):
                    sentence = entry["example"][language]
                    self.assertIsInstance(sentence, str)
                    self.assertTrue(sentence.strip())
                    self.assertLessEqual(len(sentence), 180)
                self.assertRegex(entry["example"]["meaning"], "[А-Яа-яЁё]")
                self.assertTrue(entry.get("part_of_speech"))
                grammar = entry.get("grammar")
                self.assertIsInstance(grammar, dict)
                if entry["part_of_speech"] == "noun":
                    self.assertIn(grammar.get("article"), {"der", "die", "das"})
                    self.assertIsInstance(grammar.get("plural"), str)
                    self.assertTrue(grammar["plural"].strip())
                elif entry["part_of_speech"] == "verb":
                    self.assertTrue(grammar, "verbs need at least one useful form")
                # Other parts of speech can legitimately have no inflection.
                self.assertNotIn("cefr", entry)
                self.assertNotIn("cefr", grammar)
                self.assertNotIn("level", entry)

    def test_ac8_at_least30_entries_accept_alternatives_without_replacing_primary(self):
        catalog = load_catalog(ROOT)
        words = catalog.words(catalog.require("de-basics-100"))
        enriched = [word for word in words if len(word["accepted_meanings"]) > 1]
        self.assertGreaterEqual(len(enriched), 30)
        for word in enriched:
            with self.subTest(entry=word["entry_id"]):
                self.assertIn(word["meaning"], word["accepted_meanings"])
                for answer in word["accepted_meanings"]:
                    self.assertTrue(answer_matches(word, answer))
                self.assertFalse(answer_matches(word, "это заведомо другой ответ"))

    def test_ac8_preserves_base_identity_meanings_progress_and_other_packs(self):
        for filename, document in build_documents().items():
            original = document
            if filename == "words_de_basic.json":
                original = [[entry[field] for field in ("entry_id", "target", "meaning")]
                            for entry in document["entries"]]
            fingerprint = hashlib.sha256(
                json.dumps(original, sort_keys=True, ensure_ascii=False).encode()
            ).hexdigest()
            self.assertEqual(fingerprint, BASE_FINGERPRINTS[filename], filename)
        catalog = load_catalog(ROOT)
        pack = catalog.require("de-basics-100")
        for word in catalog.words(pack):
            self.assertEqual(vocabulary_progress_id(word), content_progress_id(pack.pack_id, word["entry_id"]))

    def test_ac8_canonical_overlay_merges_and_checked_in_build_is_reproducible(self):
        overlay = self.editorial()
        self.assertEqual(overlay["schema_version"], 1)
        documents = build_documents()
        entries = {entry["entry_id"]: entry for entry in documents["words_de_basic.json"]["entries"]}
        self.assertEqual(set(overlay["entries"]), set(entries))
        for entry_id, addition in overlay["entries"].items():
            for field, value in addition.items():
                self.assertEqual(entries[entry_id][field], value)
        for filename, document in documents.items():
            self.assertEqual((ROOT / filename).read_text(encoding="utf-8"), render(document))
        result = subprocess.run(
            [sys.executable, "scripts/build_basic_packs.py", "--check"],
            cwd=ROOT, capture_output=True, text=True, check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        revised = copy.deepcopy(overlay)
        revised["entries"]["book"]["example"]["target"] = "Hier ist mein Buch."
        changed = self.build_with_overlay(revised)
        changed_book = next(entry for entry in changed["words_de_basic.json"]["entries"] if entry["entry_id"] == "book")
        self.assertEqual(changed_book["example"]["target"], "Hier ist mein Buch.")

    def test_ac8_catalog_projects_examples_and_grammar_without_mutable_aliases(self):
        catalog = load_catalog(ROOT)
        pack = catalog.require("de-basics-100")
        words = {word["entry_id"]: word for word in catalog.words(pack)}
        for entry_id, addition in self.editorial()["entries"].items():
            self.assertEqual(words[entry_id]["example_target"], addition["example"]["target"])
            self.assertEqual(words[entry_id]["example_meaning"], addition["example"]["meaning"])
            self.assertEqual(words[entry_id]["part_of_speech"], addition["part_of_speech"])
            self.assertEqual(words[entry_id]["grammar"], addition["grammar"])
        original = copy.deepcopy(words["book"]["grammar"])
        words["book"]["grammar"]["article"] = "corrupted"
        fresh = next(word for word in catalog.words(pack) if word["entry_id"] == "book")
        self.assertEqual(fresh["grammar"], original)

    def test_ac8_generator_rejects_unknown_editorial_ids(self):
        overlay = book_overlay()
        overlay["entries"]["unknown-not-in-starter-pack"] = overlay["entries"].pop("book")
        with self.assertRaisesRegex(SourceError, "unknown|entry_id"):
            self.build_with_overlay(overlay)

    def test_ac8_generator_rejects_malformed_or_unsafe_grammar(self):
        for grammar in (None, [], {"article": "banana", "plural": "Bücher"},
                        {"article": "das"}, {"article": "das", "plural": 3},
                        {"article": "das", "plural": "Bücher\u202e"}):
            with self.subTest(grammar=grammar):
                overlay = book_overlay()
                overlay["entries"]["book"]["grammar"] = grammar
                with self.assertRaisesRegex(SourceError, "grammar|article|plural"):
                    self.build_with_overlay(overlay)


if __name__ == "__main__":
    unittest.main()
