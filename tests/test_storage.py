import json
import logging
import os
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import Barrier
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, text

from mydictionary.legacy import import_legacy_user
from mydictionary.storage import (
    AIQuotaExceeded,
    AIUsage,
    AnalyticsEvent,
    DatabaseStore,
    UserPackEnrollment,
    vocabulary_id_for,
)


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
    "active_pack_id": None,
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
        inspector = inspect(self.store.engine)
        tables = set(inspector.get_table_names())
        self.assertTrue(
            {
                "alembic_version",
                "users",
                "user_progress",
                "word_progress",
                "data_imports",
                "ai_allowances",
                "ai_usage",
                "app_settings",
                "admin_credentials",
                "admin_audit_log",
                "ai_credit_ledger",
                "user_pack_enrollments",
                "analytics_events",
            }.issubset(tables)
        )
        user_columns = {column["name"] for column in inspector.get_columns("users")}
        self.assertTrue(
            {
                "role",
                "native_language",
                "learning_goal",
                "daily_word_goal",
                "onboarding_completed_at",
                "acquisition_source",
                "access_status",
                "access_status_updated_at",
            }.issubset(user_columns)
        )
        progress_columns = {
            column["name"] for column in inspector.get_columns("user_progress")
        }
        self.assertIn("active_pack_id", progress_columns)
        with self.store.engine.connect() as connection:
            revision = connection.execute(
                text("select version_num from alembic_version")
            ).scalar_one()
        self.assertEqual(revision, "0005_pilot_access")

    def test_programmatic_migrations_preserve_application_logging(self):
        root_logger = logging.getLogger()
        previous_level = root_logger.level
        sentinel = logging.NullHandler()
        root_logger.addHandler(sentinel)
        root_logger.setLevel(logging.INFO)
        secondary_store = None
        try:
            secondary_store = DatabaseStore(
                f"sqlite:///{Path(self.temp_dir.name) / 'logging.db'}"
            )
            self.assertIn(sentinel, root_logger.handlers)
            self.assertEqual(root_logger.level, logging.INFO)
        finally:
            if secondary_store is not None:
                secondary_store.close()
            root_logger.removeHandler(sentinel)
            root_logger.setLevel(previous_level)

    def test_role_promotion_never_downgrades_owner(self):
        user = SimpleNamespace(id=210, username="owner")
        self.store.ensure_user(user)
        self.assertEqual(self.store.product_profile(210)["role"], "learner")
        self.store.ensure_user(user, role="admin")
        self.store.ensure_user(user, role="learner")
        profile = self.store.product_profile(210)
        self.assertEqual(profile["role"], "admin")
        self.assertEqual(profile["access_status"], "active")

    def test_new_learners_are_pending_until_access_is_activated(self):
        self.assertIsNone(self.store.access_profile(219))
        self.store.ensure_user_id(219)
        self.assertEqual(
            self.store.access_profile(219)["access_status"], "pending"
        )
        self.store.activate_user_access(219)
        self.assertEqual(
            self.store.access_profile(219)["access_status"], "active"
        )

    def test_pilot_migration_preserves_every_existing_account(self):
        user_id = 220
        self.store.ensure_user_id(user_id)
        self.store.close()
        root = Path(__file__).resolve().parents[1]
        config = Config(str(root / "alembic.ini"))
        config.attributes["configure_logging"] = False
        config.set_main_option("script_location", str(root / "migrations"))
        config.set_main_option(
            "sqlalchemy.url", f"sqlite:///{self.database_path}"
        )
        command.downgrade(config, "0004_product_foundation")
        self.store = DatabaseStore(f"sqlite:///{self.database_path}")

        self.assertEqual(
            self.store.access_profile(user_id)["access_status"], "active"
        )

    def test_onboarding_pack_and_preferences_are_persisted(self):
        self.store.ensure_user_id(211)
        self.store.activate_pack(
            211,
            pack_id="ja-basics-100",
            language="ja",
            source="onboarding",
        )
        profile = self.store.update_product_profile(
            211,
            native_language="ru",
            learning_goal="travel",
            daily_word_goal=20,
            acquisition_source="telegram-ad",
            complete_onboarding=True,
        )
        self.assertEqual(profile["active_pack_id"], "ja-basics-100")
        self.assertEqual(profile["active_lang"], "ja")
        self.assertEqual(profile["daily_word_goal"], 20)
        self.assertIsNotNone(profile["onboarding_completed_at"])
        self.assertEqual(self.store.enrolled_pack_ids(211), {"ja-basics-100"})
        with self.store.Session() as session:
            enrollment = session.get(UserPackEnrollment, (211, "ja-basics-100"))
            self.assertTrue(enrollment.active)

    def test_analytics_accepts_dimensions_but_rejects_private_text(self):
        event_id = self.store.record_event(
            212,
            "block_started",
            properties={"pack_id": "ja-basics-100", "word_count": 10},
            session_id="session-1",
        )
        with self.store.Session() as session:
            event = session.get(AnalyticsEvent, event_id)
            self.assertEqual(
                event.properties_json,
                '{"pack_id":"ja-basics-100","word_count":10}',
            )
        with self.assertRaisesRegex(ValueError, "forbidden"):
            self.store.record_event(
                212,
                "ai_answered",
                properties={"prompt_text": "private learner content"},
            )

    def test_profiles_and_words_are_isolated_by_telegram_user(self):
        user_one = dict(PROFILE_DEFAULTS, active_lang="ja", xp=25, total_correct=1)
        word_one = {
            "en": "私",
            "ru": "я",
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
            self.store.load_word_progress(101, "ja")[
                vocabulary_id_for(word_one)
            ]["correct_count"],
            1,
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
                "ru": "я",
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
            self.store.load_word_progress(303, "ja")[
                vocabulary_id_for(legacy_words[0])
            ]["correct_count"],
            3,
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

    def test_vocabulary_identity_distinguishes_duplicate_target_terms(self):
        first = {"en": "Extend", "ru": "расширять"}
        second = {"en": "Extend", "ru": "продлевать"}

        self.assertNotEqual(vocabulary_id_for(first), vocabulary_id_for(second))

    def test_stale_recovery_does_not_release_fresh_ai_reservation(self):
        request_id = self.store.reserve_ai_usage(
            305,
            action="block_tutor",
            provider="test",
            model="test-model",
            credits=1,
            initial_credits=2,
            context_fingerprint="d" * 64,
        )

        recovered = self.store.recover_stale_ai_usage(timeout_seconds=300)

        self.assertEqual(recovered, 0)
        self.assertEqual(self.store.get_ai_usage(request_id)["status"], "reserved")
        summary = self.store.ai_usage_summary(305)
        self.assertEqual(summary["available_credits"], 1)
        self.assertEqual(summary["reserved_credits"], 1)


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

    def test_configured_admin_keeps_legacy_english_pack_and_progress(self):
        user_id = 1000
        self.store.save_profile(
            user_id, dict(PROFILE_DEFAULTS, active_lang="en", xp=140)
        )
        with (
            patch.object(self.bot, "_STORE", self.store),
            patch.object(self.bot, "LEGACY_USER_ID", None),
            patch.object(self.bot, "ADMIN_USER_IDS", {user_id}),
            self.bot.learner_scope(SimpleNamespace(id=user_id)) as runtime,
        ):
            self.assertEqual(runtime.role, "admin")
            self.assertTrue(runtime.onboarding_completed)
            self.assertEqual(
                self.bot.PROGRESS["active_pack_id"], "pirajoke-en-personal"
            )
            self.assertEqual(self.bot.PROGRESS["xp"], 140)
            self.assertEqual(len(self.bot.W()), 661)

    def test_new_users_do_not_inherit_progress_from_dictionary_json(self):
        with (
            patch.object(self.bot, "_STORE", self.store),
            patch.object(self.bot, "LEGACY_USER_ID", None),
            self.bot.learner_scope(SimpleNamespace(id=1003)),
        ):
            with self.assertRaises(PermissionError):
                self.bot.W("en")
            for language in ("vi", "ja"):
                for word in self.bot.W(language):
                    with self.subTest(language=language, term=word["en"]):
                        self.assertEqual(word["correct_count"], 0)
                        self.assertEqual(word["wrong_count"], 0)
                        self.assertIsNone(word["last_seen"])
                        self.assertEqual(word["interval"], 1)
                        self.assertIsNone(word["next_review"])

    def test_word_progress_follows_vocabulary_when_dictionary_is_reordered(self):
        user = SimpleNamespace(id=1004)
        original_words = self.bot.DICTS["ja"]
        learned_term = original_words[0]["en"]

        with (
            patch.object(self.bot, "_STORE", self.store),
            patch.object(self.bot, "LEGACY_USER_ID", None),
            self.bot.learner_scope(user),
        ):
            self.bot.PROGRESS["active_lang"] = "ja"
            self.bot.mark_correct(0)

        reordered = [original_words[1], original_words[0], *original_words[2:]]
        with (
            patch.object(self.bot, "_STORE", self.store),
            patch.object(self.bot, "LEGACY_USER_ID", None),
            patch.dict(self.bot.PACK_DICTS, {"ja-basics-100": reordered}),
            self.bot.learner_scope(user),
        ):
            self.assertEqual(self.bot.W("ja")[1]["en"], learned_term)
            self.assertEqual(self.bot.W("ja")[1]["correct_count"], 1)
            self.assertEqual(self.bot.W("ja")[0]["correct_count"], 0)

    def test_access_mode_is_fail_closed_and_validated(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(self.bot._configured_access_mode(), "allowlist")
        with patch.dict(os.environ, {"BOT_ACCESS_MODE": "public"}, clear=True):
            self.assertEqual(self.bot._configured_access_mode(), "public")
        with patch.dict(os.environ, {"BOT_ACCESS_MODE": "pilot"}, clear=True):
            self.assertEqual(self.bot._configured_access_mode(), "pilot")
        with patch.dict(os.environ, {"BOT_ACCESS_MODE": "typo"}, clear=True):
            with self.assertRaises(RuntimeError):
                self.bot._configured_access_mode()

    def test_access_decision_matrix_blocks_before_public_admission(self):
        decide = self.bot.access_decision
        self.assertEqual(
            decide(
                mode="pilot",
                configured=False,
                stored_role=None,
                stored_status=None,
                is_start=True,
            ),
            "waitlist",
        )
        self.assertEqual(
            decide(
                mode="pilot",
                configured=False,
                stored_role="learner",
                stored_status="active",
                is_start=False,
            ),
            "allow",
        )
        self.assertEqual(
            decide(
                mode="public",
                configured=True,
                stored_role="learner",
                stored_status="blocked",
                is_start=True,
            ),
            "blocked",
        )
        self.assertEqual(
            decide(
                mode="allowlist",
                configured=False,
                stored_role="admin",
                stored_status="active",
                is_start=False,
            ),
            "allow",
        )

    def test_database_url_requires_explicit_sqlite_development_opt_in(self):
        with (
            patch.dict(os.environ, {}, clear=True),
            patch.object(self.bot, "DATA_DIR", Path(self.temp_dir.name)),
        ):
            with self.assertRaises(RuntimeError):
                self.bot.database_url()

        with (
            patch.dict(
                os.environ, {"ALLOW_SQLITE_DEV": "true"}, clear=True
            ),
            patch.object(self.bot, "DATA_DIR", Path(self.temp_dir.name)),
        ):
            self.assertTrue(self.bot.database_url().startswith("sqlite:///"))


@unittest.skipUnless(os.environ.get("TEST_POSTGRES_URL"), "PostgreSQL URL not set")
class PostgresStoreTest(unittest.TestCase):
    def test_concurrent_first_reservations_do_not_double_grant(self):
        store = DatabaseStore(os.environ["TEST_POSTGRES_URL"])
        user_id = 1_000_000 + (uuid4().int % 1_000_000_000)
        store.ensure_user_id(user_id)
        barrier = Barrier(2)

        def reserve():
            barrier.wait()
            try:
                return store.reserve_ai_usage(
                    user_id,
                    action="block_tutor",
                    provider="test",
                    model="test-model",
                    credits=1,
                    initial_credits=1,
                    context_fingerprint="b" * 64,
                )
            except AIQuotaExceeded:
                return None

        try:
            with ThreadPoolExecutor(max_workers=2) as executor:
                request_ids = list(executor.map(lambda _: reserve(), range(2)))

            self.assertEqual(sum(item is not None for item in request_ids), 1)
            summary = store.ai_usage_summary(user_id)
            self.assertEqual(summary["available_credits"], 0)
            self.assertEqual(summary["reserved_credits"], 1)
        finally:
            store.close()

    def test_migrations_and_isolated_round_trip(self):
        store = DatabaseStore(os.environ["TEST_POSTGRES_URL"])
        try:
            profile = dict(PROFILE_DEFAULTS, xp=55, active_lang="vi")
            word = {
                "en": "xin chào",
                "ru": "привет",
                "correct_count": 2,
                "wrong_count": 0,
                "last_seen": "2026-08-03T12:00:00",
                "interval": 3,
                "next_review": "2026-08-06T12:00:00",
            }
            store.save_learning_state(900001, profile, "vi", 0, word)
            self.assertEqual(store.load_profile(900001, PROFILE_DEFAULTS)["xp"], 55)
            self.assertEqual(
                store.load_word_progress(900001, "vi")[
                    vocabulary_id_for(word)
                ]["correct_count"],
                2,
            )
            request_id = store.reserve_ai_usage(
                900001,
                action="block_tutor",
                provider="test",
                model="test-model",
                credits=1,
                initial_credits=2,
                context_fingerprint="a" * 64,
            )
            store.complete_ai_usage(
                request_id,
                billed_credits=1,
                provider_response_id="response-1",
                model="test-model",
                usage={"input_tokens": 5, "output_tokens": 3, "total_tokens": 8},
                cost_micro_usd=7,
                latency_ms=10,
            )
            summary = store.ai_usage_summary(900001)
            self.assertEqual(summary["available_credits"], 1)
            self.assertEqual(summary["total_tokens"], 8)

            stale_request_id = store.reserve_ai_usage(
                900001,
                action="block_tutor",
                provider="test",
                model="test-model",
                credits=1,
                initial_credits=2,
                context_fingerprint="e" * 64,
            )
            with store.Session.begin() as session:
                stale_row = session.get(AIUsage, stale_request_id)
                stale_row.created_at = datetime.now(timezone.utc) - timedelta(
                    seconds=600
                )
            self.assertEqual(
                store.recover_stale_ai_usage(
                    timeout_seconds=300, user_id=900001
                ),
                1,
            )
            recovered = store.ai_usage_summary(900001)
            self.assertEqual(recovered["available_credits"], 1)
            self.assertEqual(recovered["reserved_credits"], 0)
            self.assertEqual(recovered["failed_requests"], 1)
        finally:
            store.close()


if __name__ == "__main__":
    unittest.main()
