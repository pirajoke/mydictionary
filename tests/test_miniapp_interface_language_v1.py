from __future__ import annotations

import json
import os
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from sqlalchemy import inspect, text


os.environ.setdefault("BOT_TOKEN", "123456:TESTTOKEN_ABCDEFGHIJKLMNOP")
os.environ.setdefault("ALLOWED_USER_ID", "1")
os.environ.setdefault("ALLOW_SQLITE_DEV", "true")

import bot
from mydictionary import miniapp
from mydictionary.admin import create_app
from mydictionary.privacy import erase_user_learning_data
from mydictionary.storage import DatabaseStore, User


ROOT = Path(__file__).resolve().parents[1]
LOCALES = ("en", "fr", "de", "ja", "ar", "zh", "ru", "es")
TOKEN = "123456:TESTTOKEN_ABCDEFGHIJKLMNOP"
USER_ID = 731_001


class MiniAppInterfaceLanguageContractTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="miniapp-locale-")
        self.store = DatabaseStore(
            f"sqlite:///{Path(self.temporary.name) / 'locale.sqlite3'}"
        )
        self.store.ensure_user(
            SimpleNamespace(
                id=USER_ID,
                username="learner",
                first_name="Mila",
                last_name=None,
                language_code="fr",
            )
        )
        with self.store.Session.begin() as session:
            learner = session.get(User, USER_ID)
            learner.access_status = "active"
            learner.privacy_status = "active"
            learner.native_language = "ru"
        self.store.activate_pack(
            USER_ID,
            pack_id="en-basics-100",
            language="en",
            source="test",
        )

    def tearDown(self):
        self.store.close()
        self.temporary.cleanup()

    def app(self):
        return create_app(
            {
                "TESTING": True,
                "SECRET_KEY": "s" * 40,
                "ADMIN_USERNAME": "owner",
                "ADMIN_PASSWORD": "password",
                "MINIAPP_ENABLED": True,
                "MINIAPP_PUBLIC_URL": "https://mydictionary.example.test/miniapp",
                "MINIAPP_BOT_USERNAME": "mydictionary_test_bot",
                "MINIAPP_AUTH_MAX_AGE_SECONDS": 300,
                "BOT_TOKEN_FILE": "/protected/bot-token",
                "TELEGRAM_STARS_ENABLED": False,
            },
            database_store=self.store,
        )

    def verified_user(self, locale="fr"):
        return {
            "user_id": USER_ID,
            "display_name": "Mila",
            "language_code": locale,
        }

    def test_ac4_dedicated_schema_storage_migration_and_privacy_erasure(self):
        columns = {column["name"] for column in inspect(self.store.engine).get_columns("users")}
        self.assertIn("interface_locale", columns)
        with self.store.engine.connect() as connection:
            revision = connection.execute(text("select version_num from alembic_version")).scalar_one()
        self.assertEqual(revision, "0018_interface_locale")

        self.assertEqual(self.store.set_interface_locale(USER_ID, "es"), "es")
        with self.store.Session() as session:
            learner = session.get(User, USER_ID)
            interface_locale = session.execute(
                text("select interface_locale from users where telegram_user_id = :user_id"),
                {"user_id": USER_ID},
            ).scalar_one()
            self.assertEqual(interface_locale, "es")
            self.assertEqual(learner.language_code, "fr")

        erase_user_learning_data(self.store, USER_ID, actor="test")
        with self.store.Session() as session:
            self.assertIsNone(
                session.execute(
                    text("select interface_locale from users where telegram_user_id = :user_id"),
                    {"user_id": USER_ID},
                ).scalar_one()
            )

    def test_ac2_bootstrap_prefers_durable_override_and_falls_back_to_telegram(self):
        fake_store = MagicMock()
        fake_store.ai_usage_summary.return_value = {
            "available_credits": 0,
            "reserved_credits": 0,
            "spent_credits": 0,
        }
        fake_store.load_word_progress.return_value = {}
        snapshot = (
            {
                "role": "learner",
                "native_language": "ru",
                "learning_goal": "basics",
                "daily_word_goal": 5,
                "active_pack_id": None,
                "active_lang": "en",
                "mirror_style": "teacher",
                "interface_locale": "ru",
            },
            {},
            {"mode": "text", "depth": "balanced", "level": "adaptive"},
        )
        with (
            patch.object(miniapp, "require_active_learner", return_value={"role": "learner"}),
            patch.object(miniapp, "_read_only_database_snapshot", return_value=snapshot),
            patch.object(miniapp, "_read_only_activity_days", return_value=[]),
        ):
            payload = miniapp.build_bootstrap(
                fake_store,
                user_id=USER_ID,
                display_name="Mila",
                locale="fr",
                catalog=bot.CATALOG,
                products=[],
                checkout_enabled=False,
                ai_enabled=False,
                voice_enabled=False,
            )
        self.assertEqual(payload["locale"], "ru")
        self.assertEqual(payload["direction"], "ltr")
        self.assertEqual(payload["settings"]["interface_locale"], "ru")
        self.assertEqual({row["value"] for row in payload["interface_locales"]}, set(LOCALES))

    def test_ac2_http_post_persists_exact_locale_and_returns_localized_bootstrap(self):
        client = self.app().test_client()
        with patch.object(miniapp, "verify_init_data", return_value=self.verified_user()):
            response = client.post(
                "/miniapp/api/interface-locale",
                headers={"X-Telegram-Init-Data": "signed"},
                json={"locale": "ar"},
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["Cache-Control"], "no-store")
        payload = response.get_json()
        self.assertEqual(payload["locale"], "ar")
        self.assertEqual(payload["direction"], "rtl")
        with self.store.Session() as session:
            learner = session.get(User, USER_ID)
            interface_locale = session.execute(
                text("select interface_locale from users where telegram_user_id = :user_id"),
                {"user_id": USER_ID},
            ).scalar_one()
            self.assertEqual(interface_locale, "ar")
            self.assertEqual(learner.language_code, "fr")
            self.assertEqual(learner.native_language, "ru")

    def test_err1_post_is_strict_authenticated_and_fail_closed(self):
        client = self.app().test_client()
        self.assertEqual(
            client.post("/miniapp/api/interface-locale", json={"locale": "ru"}).status_code,
            401,
        )
        invalid = ({}, {"locale": "RU"}, {"locale": "it"}, {"locale": 7}, {"locale": "ru", "x": 1})
        with patch.object(miniapp, "verify_init_data", return_value=self.verified_user()):
            for body in invalid:
                with self.subTest(body=body):
                    response = client.post(
                        "/miniapp/api/interface-locale",
                        headers={"X-Telegram-Init-Data": "signed"},
                        json=body,
                    )
                    self.assertEqual(response.status_code, 400)

    def test_err2_response_serialization_fails_before_storage_mutation(self):
        client = self.app().test_client()
        with (
            patch.object(miniapp, "verify_init_data", return_value=self.verified_user()),
            patch.object(miniapp, "build_bootstrap", return_value={"bad": object()}),
            patch.object(self.store, "set_interface_locale", wraps=self.store.set_interface_locale) as persist,
        ):
            response = client.post(
                "/miniapp/api/interface-locale",
                headers={"X-Telegram-Init-Data": "signed"},
                json={"locale": "ru"},
            )

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.get_json(), {"error": "temporarily_unavailable"})
        persist.assert_not_called()
        with self.store.engine.connect() as connection:
            self.assertIsNone(
                connection.execute(
                    text(
                        "select interface_locale from users "
                        "where telegram_user_id = :user_id"
                    ),
                    {"user_id": USER_ID},
                ).scalar_one()
            )

    def test_ac3_bot_runtime_prefers_durable_override_to_telegram_language(self):
        self.assertIn("interface_locale", bot.LearnerRuntime.__dataclass_fields__)
        runtime = bot.LearnerRuntime(
            user_id=USER_ID,
            store=self.store,
            progress={},
            interface_locale="es",
        )
        token = bot._ACTIVE_RUNTIME.set(runtime)
        try:
            update = SimpleNamespace(
                effective_user=SimpleNamespace(id=USER_ID, language_code="fr")
            )
            self.assertEqual(bot.interface_locale_for_update(update), "es")
        finally:
            bot._ACTIVE_RUNTIME.reset(token)

    def test_ac1_ac5_frontend_has_accessible_localized_serialized_selector(self):
        for locale in LOCALES:
            with self.subTest(locale=locale):
                copy = miniapp.MINIAPP_COPY[locale]
                for key in (
                    "setting_interface_language",
                    "interface_language_pending",
                    "interface_language_error",
                    "interface_language_retry",
                ):
                    self.assertTrue(copy.get(key))

        js = (ROOT / "mydictionary/static/miniapp.js").read_text(encoding="utf-8")
        css = (ROOT / "mydictionary/static/miniapp.css").read_text(encoding="utf-8")
        self.assertIn('"/miniapp/api/interface-locale"', js)
        self.assertIn("interface-locale-select", js)
        self.assertIn("JSON.stringify({locale:", js)
        self.assertIn("interfaceLocalePending", js)
        self.assertIn("disabled", js)
        self.assertIn("await load()", js)
        self.assertIn(".interface-locale-select", css)
        self.assertIn(":focus-visible", css)


if __name__ == "__main__":
    unittest.main()
