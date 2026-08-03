import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from sqlalchemy import inspect, text

from mydictionary.legacy import import_legacy_user
from mydictionary.storage import DatabaseStore


PROFILE_DEFAULTS = {
    "total_correct": 0,
    "total_wrong": 0,
    "sessions": 0,
    "xp": 0,
    "level": 1,
    "streak": 0,
    "streak_best": 0,
    "last_activity_date": None,
    "today_xp": 0,
    "today_date": None,
    "active_lang": "en",
}


class DatabaseStoreTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory(prefix="mydictionary-storage-")
        self.database_path = Path(self.temp_dir.name) / "test.db"
        self.store = DatabaseStore(f"sqlite:///{self.database_path}")

    def tearDown(self):
        self.store.close()
        self.temp_dir.cleanup()

    def test_migration_creates_versioned_multiuser_schema(self):
        tables = set(inspect(self.store.engine).get_table_names())
        self.assertTrue(
            {
                "alembic_version",
                "users",
                "user_progress",
                "word_progress",
                "data_imports",
            }.issubset(tables)
        )
        with self.store.engine.connect() as connection:
            revision = connection.execute(
                text("select version_num from alembic_version")
            ).scalar_one()
        self.assertEqual(revision, "0001_multiuser_learning")

    def test_profiles_and_words_are_isolated_by_telegram_user(self):
        user_one = dict(PROFILE_DEFAULTS, active_lang="ja", xp=25, total_correct=1)
        word_one = {
            "en": "私",
            "correct_count": 1,
            "wrong_count": 0,
            "last_seen": "2026-08-03T12:00:00",
            "interval": 1,
            "next_review": "2026-08-04T12:00:00",
        }
        self.store.save_learning_state(101, user_one, "ja", 10, word_one)
        self.store.ensure_user_id(202)

        loaded_one = self.store.load_profile(101, PROFILE_DEFAULTS)
        loaded_two = self.store.load_profile(202, PROFILE_DEFAULTS)
        self.assertEqual(loaded_one["xp"], 25)
        self.assertEqual(loaded_one["active_lang"], "ja")
        self.assertEqual(loaded_two, PROFILE_DEFAULTS)
        self.assertEqual(
            self.store.load_word_progress(101, "ja")[10]["correct_count"], 1
        )
        self.assertEqual(self.store.load_word_progress(202, "ja"), {})

    def test_legacy_import_is_idempotent(self):
        data_dir = Path(self.temp_dir.name) / "legacy"
        base_dir = Path(self.temp_dir.name) / "base"
        data_dir.mkdir()
        base_dir.mkdir()
        (data_dir / "progress.json").write_text(
            json.dumps(dict(PROFILE_DEFAULTS, xp=140, active_lang="ja")),
            encoding="utf-8",
        )
        legacy_words = [
            {
                "en": "私",
                "correct_count": 3,
                "wrong_count": 1,
                "last_seen": "2026-08-02T10:00:00",
                "interval": 7,
                "next_review": "2026-08-09T10:00:00",
            }
        ]
        (data_dir / "words_ja.json").write_text(
            json.dumps(legacy_words), encoding="utf-8"
        )

        first = import_legacy_user(
            self.store,
            303,
            data_dir,
            base_dir,
            {"ja": "words_ja.json"},
            PROFILE_DEFAULTS,
        )
        (data_dir / "progress.json").write_text(
            json.dumps(dict(PROFILE_DEFAULTS, xp=999)), encoding="utf-8"
        )
        second = import_legacy_user(
            self.store,
            303,
            data_dir,
            base_dir,
            {"ja": "words_ja.json"},
            PROFILE_DEFAULTS,
        )

        self.assertTrue(first)
        self.assertFalse(second)
        self.assertEqual(self.store.load_profile(303, PROFILE_DEFAULTS)["xp"], 140)
        self.assertEqual(
            self.store.load_word_progress(303, "ja")[0]["correct_count"], 3
        )

    def test_legacy_import_accepts_words_without_progress_fields(self):
        data_dir = Path(self.temp_dir.name) / "legacy-minimal"
        base_dir = Path(self.temp_dir.name) / "base-minimal"
        data_dir.mkdir()
        base_dir.mkdir()
        (data_dir / "progress.json").write_text(
            json.dumps(dict(PROFILE_DEFAULTS, xp=5)), encoding="utf-8"
        )
        (data_dir / "words_ja.json").write_text(
            json.dumps([{"en": "私", "ru": "я"}]), encoding="utf-8"
        )

        imported = import_legacy_user(
            self.store,
            304,
            data_dir,
            base_dir,
            {"ja": "words_ja.json"},
            PROFILE_DEFAULTS,
        )

        self.assertTrue(imported)
        self.assertEqual(self.store.load_profile(304, PROFILE_DEFAULTS)["xp"], 5)
        self.assertEqual(self.store.load_word_progress(304, "ja"), {})


class BotRuntimeIsolationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.setdefault("BOT_TOKEN", "123456:TESTTOKEN")
        os.environ.setdefault("ALLOWED_USER_ID", "1")
        import bot

        cls.bot = bot

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory(prefix="mydictionary-runtime-")
        path = Path(self.temp_dir.name) / "runtime.db"
        self.store = DatabaseStore(f"sqlite:///{path}")

    def tearDown(self):
        self.store.close()
        self.temp_dir.cleanup()

    def test_runtime_progress_is_isolated_and_content_is_not_rewritten(self):
        dictionary_path = Path(self.bot.__file__).parent / "words_ja.json"
        original_content = dictionary_path.read_bytes()
        user_one = SimpleNamespace(id=1001)
        user_two = SimpleNamespace(id=1002)

        with (
            patch.object(self.bot, "_STORE", self.store),
            patch.object(self.bot, "LEGACY_USER_ID", None),
        ):
            with self.bot.learner_scope(user_one):
                self.bot.PROGRESS["active_lang"] = "ja"
                self.bot.mark_correct(10)
                self.assertEqual(self.bot.W()[10]["correct_count"], 1)

            with self.bot.learner_scope(user_two):
                self.assertEqual(self.bot.PROGRESS["active_lang"], "en")
                self.assertEqual(self.bot.W("ja")[10]["correct_count"], 0)

            with self.bot.learner_scope(user_one):
                self.assertEqual(self.bot.PROGRESS["active_lang"], "ja")
                self.assertEqual(self.bot.W()[10]["correct_count"], 1)
                self.assertGreater(self.bot.PROGRESS["xp"], 0)

        self.assertEqual(dictionary_path.read_bytes(), original_content)

    def test_access_mode_is_fail_closed_and_validated(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(self.bot._configured_access_mode(), "allowlist")
        with patch.dict(os.environ, {"BOT_ACCESS_MODE": "public"}, clear=True):
            self.assertEqual(self.bot._configured_access_mode(), "public")
        with patch.dict(os.environ, {"BOT_ACCESS_MODE": "typo"}, clear=True):
            with self.assertRaises(RuntimeError):
                self.bot._configured_access_mode()


@unittest.skipUnless(os.environ.get("TEST_POSTGRES_URL"), "PostgreSQL URL not set")
class PostgresStoreTest(unittest.TestCase):
    def test_migrations_and_isolated_round_trip(self):
        store = DatabaseStore(os.environ["TEST_POSTGRES_URL"])
        try:
            profile = dict(PROFILE_DEFAULTS, xp=55, active_lang="vi")
            word = {
                "en": "xin chào",
                "correct_count": 2,
                "wrong_count": 0,
                "last_seen": "2026-08-03T12:00:00",
                "interval": 3,
                "next_review": "2026-08-06T12:00:00",
            }
            store.save_learning_state(900001, profile, "vi", 0, word)
            self.assertEqual(store.load_profile(900001, PROFILE_DEFAULTS)["xp"], 55)
            self.assertEqual(
                store.load_word_progress(900001, "vi")[0]["correct_count"], 2
            )
        finally:
            store.close()


if __name__ == "__main__":
    unittest.main()
