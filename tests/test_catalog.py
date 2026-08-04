import unittest
from pathlib import Path

from mydictionary.catalog import load_catalog
from vocabulary_topics import transcription_for


ROOT = Path(__file__).resolve().parents[1]


class ContentCatalogTest(unittest.TestCase):
    def setUp(self):
        self.catalog = load_catalog(ROOT)

    def test_catalog_declares_private_owner_pack_and_public_free_packs(self):
        self.assertEqual(len(self.catalog.packs), 3)
        private_pack = self.catalog.require("pirajoke-en-personal")
        self.assertEqual(private_pack.visibility, "admin")
        self.assertFalse(private_pack.is_free)

        learner_ids = {
            pack.pack_id for pack in self.catalog.visible_packs("learner")
        }
        admin_ids = {pack.pack_id for pack in self.catalog.visible_packs("admin")}
        self.assertNotIn(private_pack.pack_id, learner_ids)
        self.assertIn(private_pack.pack_id, admin_ids)
        self.assertEqual(learner_ids, {"vi-basics-101", "ja-basics-100"})

    def test_public_packs_match_declared_counts_and_have_transcriptions(self):
        for pack in self.catalog.visible_packs("learner"):
            words = self.catalog.words(pack)
            with self.subTest(pack=pack.pack_id):
                self.assertEqual(len(words), pack.word_count)
                self.assertTrue(
                    all(transcription_for(word, pack.language) for word in words)
                )

    def test_storage_namespaces_are_unique_and_legacy_compatible(self):
        storage_keys = [pack.storage_key for pack in self.catalog.packs]
        self.assertEqual(len(storage_keys), len(set(storage_keys)))
        self.assertEqual(
            self.catalog.require("pirajoke-en-personal").storage_key,
            "en",
        )


if __name__ == "__main__":
    unittest.main()
