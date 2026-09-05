from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import importlib
import json
import os
from pathlib import Path
import re
import tempfile
import time
from types import SimpleNamespace
from urllib.parse import urlencode
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from sqlalchemy import func, select, text
from telegram import MenuButtonDefault


os.environ.setdefault("BOT_TOKEN", "123456:TESTTOKEN_ABCDEFGHIJKLMNOP")
os.environ.setdefault("ALLOWED_USER_ID", "1")
os.environ.setdefault("ALLOW_SQLITE_DEV", "true")

import bot
from mydictionary.admin import create_app
from mydictionary.storage import (
    AIUsage,
    AIWallet,
    DatabaseStore,
    User,
    UserProgress,
    WordProgress,
    vocabulary_id_for,
)
from ops import mydictionary_admin as admin_launcher


INTERFACE_LOCALES = {"en", "fr", "de", "ja", "ar", "zh", "ru", "es"}
MINIAPP_COPY_KEYS = {
    "loading",
    "error",
    "retry",
    "profile",
    "words",
    "credits",
    "languages",
    "settings",
    "continue_lesson",
    "ai_tutor",
    "share",
    "empty_words",
    "start_lesson",
    "change_language",
    "open_settings",
    "privacy",
    "word_review",
    "word_learned",
    "attempts_correct",
    "attempts_wrong",
    "metric_level",
    "metric_xp",
    "metric_streak",
    "metric_best_streak",
    "metric_sessions",
    "metric_accuracy",
    "metric_today_xp",
    "metric_daily_goal",
    "metric_tracked_words",
    "metric_learned_words",
    "metric_ai_credits",
    "credit_available",
    "credit_reserved",
    "credit_spent",
    "credit_contract",
    "checkout_disabled",
    "setting_daily_goal",
    "setting_meaning_language",
    "setting_learning_goal",
    "setting_mirror_mode",
    "setting_mirror_style",
    "setting_mirror_depth",
    "setting_mirror_level",
    "setting_ai",
    "setting_voice",
    "setting_unknown",
    "feature_enabled",
    "feature_disabled",
    "navigation_label",
    "language_current",
}
TOKEN = "123456:TESTTOKEN_ABCDEFGHIJKLMNOP"
MINIAPP_URL = "https://mydictionary.example.test/miniapp"
SAFE_USERNAME = "mydictionary_test_bot"
SENSITIVE_KEYS = {
    "telegram_user_id",
    "user_id",
    "username",
    "init_data",
    "initdata",
    "bot_token",
    "credential",
    "message_history",
    "prompt",
    "answer",
    "charge_id",
    "database_url",
    "pack_id",
    "vocabulary_id",
    "vocabulary_hash",
}


def miniapp_module(testcase):
    try:
        return importlib.import_module("mydictionary.miniapp")
    except ModuleNotFoundError:
        testcase.fail("missing public module mydictionary.miniapp")


def signed_init_data(*, user_id=7001, auth_date=1_800_000_000, **extra):
    fields = {
        "auth_date": str(auth_date),
        "query_id": "AAHdF6IQAAAAAN0XohDhrOrc",
        "user": json.dumps(
            {
                "id": user_id,
                "first_name": "Mila",
                "language_code": "fr",
                "username": "must-not-enter-bootstrap",
            },
            separators=(",", ":"),
            ensure_ascii=False,
        ),
        **{key: str(value) for key, value in extra.items()},
    }
    data_check = "\n".join(f"{key}={fields[key]}" for key in sorted(fields))
    secret = hmac.new(b"WebAppData", TOKEN.encode(), hashlib.sha256).digest()
    fields["hash"] = hmac.new(
        secret, data_check.encode(), hashlib.sha256
    ).hexdigest()
    return urlencode(fields)


class MiniAppSecurityContractTest(unittest.TestCase):
    def test_ac1_valid_hmac_derives_only_signed_user_and_rejects_auth_edge_cases(self):
        miniapp = miniapp_module(self)
        verify = miniapp.verify_init_data
        now = 1_800_000_100
        verified = verify(
            signed_init_data(),
            bot_token=TOKEN,
            now=now,
            max_age_seconds=300,
        )
        self.assertEqual(
            verified,
            {
                "user_id": 7001,
                "display_name": "Mila",
                "language_code": "fr",
            },
        )

        cases = {
            "missing": "",
            "malformed": "not-a-query",
            "tampered": signed_init_data().replace("Mila", "Mallory"),
            "expired": signed_init_data(auth_date=now - 301),
            "future": signed_init_data(auth_date=now + 31),
            "duplicate": signed_init_data() + "&auth_date=1800000000",
        }
        for label, value in cases.items():
            with self.subTest(label=label):
                with self.assertRaises(miniapp.MiniAppAuthenticationError):
                    verify(
                        value,
                        bot_token=TOKEN,
                        now=now,
                        max_age_seconds=300,
                    )

    def test_err1_enabled_configuration_is_https_bounded_and_token_file_only(self):
        miniapp = miniapp_module(self)
        with tempfile.TemporaryDirectory(prefix="miniapp-token-") as raw:
            token_file = Path(raw) / "bot-token"
            token_file.write_text(TOKEN, encoding="ascii")
            os.chmod(token_file, 0o600)
            valid = {
                "MINIAPP_ENABLED": "true",
                "MINIAPP_PUBLIC_URL": MINIAPP_URL,
                "MINIAPP_BOT_USERNAME": SAFE_USERNAME,
                "MINIAPP_AUTH_MAX_AGE_SECONDS": "300",
                "BOT_TOKEN_FILE": str(token_file),
            }
            settings = miniapp.MiniAppSettings.from_env(valid)
            self.assertTrue(settings.enabled)
            self.assertEqual(settings.public_url, MINIAPP_URL)
            self.assertEqual(settings.auth_max_age_seconds, 300)
            self.assertNotIn(TOKEN, repr(settings))

            invalid = (
                {**valid, "MINIAPP_PUBLIC_URL": "http://example.test/miniapp"},
                {**valid, "MINIAPP_PUBLIC_URL": MINIAPP_URL + "/"},
                {**valid, "MINIAPP_PUBLIC_URL": MINIAPP_URL + "?token=x"},
                {**valid, "MINIAPP_PUBLIC_URL": "https://user@example.test/miniapp"},
                {**valid, "MINIAPP_BOT_USERNAME": "unsafe/name"},
                {**valid, "MINIAPP_AUTH_MAX_AGE_SECONDS": "59"},
                {**valid, "MINIAPP_AUTH_MAX_AGE_SECONDS": "901"},
                {**valid, "BOT_TOKEN": TOKEN},
            )
            for values in invalid:
                with self.subTest(values=values):
                    with self.assertRaises(miniapp.MiniAppConfigurationError):
                        miniapp.MiniAppSettings.from_env(values)

            os.chmod(token_file, 0o644)
            with self.assertRaises(miniapp.MiniAppConfigurationError):
                miniapp.MiniAppSettings.from_env(valid)

    def test_ac1_denied_learner_states_never_create_or_disclose_a_record(self):
        miniapp = miniapp_module(self)
        for profile in (
            None,
            {"access_status": "pending", "privacy_status": "active"},
            {"access_status": "blocked", "privacy_status": "active"},
            {"access_status": "active", "privacy_status": "erased"},
        ):
            with self.subTest(profile=profile):
                store = MagicMock()
                store.access_profile.return_value = profile
                with self.assertRaises(miniapp.MiniAppAccessDenied):
                    miniapp.require_active_learner(store, 7001)
                store.ensure_user_id.assert_not_called()
                store.product_profile.assert_not_called()


class MiniAppBootstrapContractTest(unittest.TestCase):
    def test_ac2_ac3_ac5_bootstrap_is_real_bounded_and_privacy_allowlisted(self):
        miniapp = miniapp_module(self)
        store = MagicMock()
        store.access_profile.return_value = {
            "role": "learner",
            "access_status": "active",
            "privacy_status": "active",
            "language_code": "fr",
        }
        store.product_profile.return_value = {
            "role": "learner",
            "native_language": "fr",
            "learning_goal": "travel",
            "daily_word_goal": 10,
            "active_lang": "ja",
            "active_pack_id": "ja-basics-100",
            "mirror_style": "teacher",
        }
        store.load_profile.return_value = {
            "level": 4,
            "xp": 820,
            "streak": 5,
            "streak_best": 9,
            "sessions": 13,
            "total_correct": 30,
            "total_wrong": 10,
            "today_xp": 40,
        }
        catalog_words = bot.CATALOG.words(bot.CATALOG.get("ja-basics-100"))
        store.load_word_progress.return_value = {
            vocabulary_id_for(word): {
                "correct_count": index,
                "wrong_count": 1,
                "interval": 2,
                "next_review": "2026-08-29",
            }
            for index, word in enumerate(catalog_words[:75])
        }
        store.ai_usage_summary.return_value = {
            "available_credits": 7,
            "reserved_credits": 1,
            "spent_credits": 3,
        }
        products = [
            {
                "product_id": "ai-mini",
                "title": "Mini",
                "description": "20 credits",
                "credits": 20,
                "price_xtr": 69,
                "status": "active",
                "billing_mode": "one_time",
                "display_order": 10,
            },
            {
                "product_id": "ai-monthly",
                "title": "Monthly",
                "credits": 100,
                "price_xtr": 229,
                "status": "active",
                "billing_mode": "subscription",
                "display_order": 20,
            },
        ]
        payload = miniapp.build_bootstrap(
            store,
            user_id=7001,
            display_name="Mila",
            locale="fr",
            catalog=bot.CATALOG,
            products=products,
            checkout_enabled=False,
            ai_enabled=True,
            voice_enabled=False,
        )
        serialized = json.dumps(payload, ensure_ascii=False).casefold()
        self.assertEqual(payload["profile"]["display_name"], "Mila")
        self.assertEqual(payload["progress"]["accuracy"], {"correct": 30, "total": 40})
        self.assertEqual(payload["credits"]["available"], 7)
        self.assertEqual(len(payload["words"]), 60)
        self.assertTrue(all("target" in word for word in payload["words"]))
        self.assertEqual(payload["words"][0]["target"], catalog_words[0]["target"])
        self.assertTrue(all("pack_id" not in word for word in payload["words"]))
        self.assertTrue(all(product["billing_mode"] == "one_time" for product in payload["products"]))
        self.assertFalse(payload["features"]["stars_checkout"])
        self.assertEqual(
            set(payload["actions"]),
            {"learn", "ai", "buy", "lang", "settings", "privacy", "help", "share"},
        )
        for key in SENSITIVE_KEYS:
            with self.subTest(key=key):
                self.assertNotIn(key, serialized)
        self.assertLessEqual(len(serialized), 64_000)

    def test_ec1_zero_progress_and_words_are_honest_not_fabricated(self):
        miniapp = miniapp_module(self)
        store = MagicMock()
        store.access_profile.return_value = {
            "role": "learner",
            "access_status": "active",
            "privacy_status": "active",
            "language_code": "en",
        }
        store.product_profile.return_value = {
            "role": "learner",
            "daily_word_goal": 10,
            "active_lang": "en",
            "active_pack_id": None,
        }
        store.load_profile.return_value = {}
        store.load_word_progress.return_value = {}
        store.ai_usage_summary.return_value = {
            "available_credits": 0,
            "reserved_credits": 0,
            "spent_credits": 0,
        }
        payload = miniapp.build_bootstrap(
            store,
            user_id=7001,
            display_name="Learner",
            locale="en",
            catalog=bot.CATALOG,
            products=[],
            checkout_enabled=False,
            ai_enabled=False,
            voice_enabled=False,
        )
        self.assertEqual(payload["words"], [])
        self.assertEqual(payload["progress"]["accuracy"], {"correct": 0, "total": 0})
        self.assertEqual(payload["progress"]["xp"], 0)
        self.assertEqual(payload["progress"]["sessions"], 0)

    def test_ac2_stale_today_xp_is_zero_read_only_but_current_date_is_preserved(self):
        miniapp = miniapp_module(self)
        store = MagicMock()
        store.access_profile.return_value = {
            "role": "learner",
            "access_status": "active",
            "privacy_status": "active",
            "language_code": "en",
        }
        store.product_profile.return_value = {
            "role": "learner",
            "daily_word_goal": 10,
            "active_lang": "en",
            "active_pack_id": None,
        }
        today = datetime.now(timezone.utc).date()
        store.load_profile.side_effect = (
            {"today_xp": 37, "today_date": (today - timedelta(days=1)).isoformat()},
            {"today_xp": 37, "today_date": today.isoformat()},
        )
        store.load_word_progress.return_value = {}
        store.ai_usage_summary.return_value = {}
        store.get_mirror_preferences.return_value = {}

        payloads = [
            miniapp.build_bootstrap(
                store,
                user_id=7001,
                display_name="Learner",
                locale="en",
                catalog=bot.CATALOG,
                products=[],
                checkout_enabled=False,
                ai_enabled=False,
                voice_enabled=False,
            )
            for _ in range(2)
        ]

        self.assertEqual(payloads[0]["progress"]["today_xp"], 0)
        self.assertEqual(payloads[1]["progress"]["today_xp"], 37)
        store.ensure_user_id.assert_not_called()
        store.save_profile.assert_not_called()

    def test_ac3_real_store_reads_tracked_words_by_pack_storage_key(self):
        miniapp = miniapp_module(self)
        user_id = 7103
        pack = bot.CATALOG.require("fr-basics-100")
        self.assertEqual(pack.target_language, "fr")
        self.assertEqual(pack.storage_key, "fr_basic")
        words = bot.CATALOG.words(pack)[:2]
        temporary = tempfile.TemporaryDirectory(prefix="miniapp-storage-key-")
        self.addCleanup(temporary.cleanup)
        self.store = DatabaseStore(
            f"sqlite:///{Path(temporary.name) / 'storage-key.sqlite3'}"
        )
        self.addCleanup(self.store.close)
        self.store.ensure_user_id(user_id)
        with self.store.Session.begin() as session:
            learner = session.get(User, user_id)
            learner.access_status = "active"
            learner.privacy_status = "active"
            learner.native_language = "ru"
            progress = session.get(UserProgress, user_id)
            progress.active_lang = pack.target_language
            progress.active_pack_id = pack.pack_id
            session.add_all(
                [
                    WordProgress(
                        telegram_user_id=user_id,
                        language=pack.storage_key,
                        vocabulary_id=vocabulary_id_for(word),
                        term=word["target"],
                        word_index=index,
                        correct_count=3 if index == 0 else 1,
                        wrong_count=4 if index == 0 else 1,
                        interval=2,
                    )
                    for index, word in enumerate(words)
                ]
            )

        self.assertEqual(
            len(self.store.load_word_progress(user_id, pack.storage_key)),
            2,
        )
        self.assertEqual(self.store.load_word_progress(user_id, pack.target_language), {})
        payload = miniapp.build_bootstrap(
            self.store,
            user_id=user_id,
            display_name="Camille",
            locale="fr",
            catalog=bot.CATALOG,
            products=[],
            checkout_enabled=False,
            ai_enabled=False,
            voice_enabled=False,
        )

        self.assertEqual([row["target"] for row in payload["words"]], [word["target"] for word in words])
        self.assertEqual(payload["progress"]["tracked_words"], 2)
        self.assertEqual(
            (payload["words"][0]["learned"], payload["progress"]["learned_words"]),
            (True, 1),
            "three correct answers define learned status even after more wrong attempts",
        )
        self.assertTrue(all("pack_id" not in row for row in payload["words"]))

    def test_ec1_real_active_learner_bootstrap_is_storage_read_only(self):
        miniapp = miniapp_module(self)
        user_id = 7104
        temporary = tempfile.TemporaryDirectory(prefix="miniapp-read-only-")
        self.addCleanup(temporary.cleanup)
        store = DatabaseStore(
            f"sqlite:///{Path(temporary.name) / 'read-only.sqlite3'}"
        )
        self.addCleanup(store.close)
        fixed = datetime(2026, 8, 1, 12, 0, tzinfo=timezone.utc)
        with store.Session.begin() as session:
            session.add(
                User(
                    telegram_user_id=user_id,
                    role="learner",
                    access_status="active",
                    privacy_status="active",
                    language_code="fr",
                    updated_at=fixed,
                    created_at=fixed,
                )
            )

        def snapshot():
            with store.Session() as session:
                learner = session.get(User, user_id)
                return {
                    "updated_at": learner.updated_at,
                    "users": session.scalar(select(func.count()).select_from(User)),
                    "progress": session.scalar(
                        select(func.count()).select_from(UserProgress)
                    ),
                    "words": session.scalar(
                        select(func.count()).select_from(WordProgress)
                    ),
                    "wallets": session.scalar(
                        select(func.count()).select_from(AIWallet)
                    ),
                    "usage": session.scalar(select(func.count()).select_from(AIUsage)),
                }

        before = snapshot()
        payload = miniapp.build_bootstrap(
            store,
            user_id=user_id,
            display_name="Camille",
            locale="fr",
            catalog=bot.CATALOG,
            products=[],
            checkout_enabled=False,
            ai_enabled=False,
            voice_enabled=False,
            initial_credits=9,
        )
        after = snapshot()

        self.assertEqual(payload["credits"]["available"], 9)
        self.assertEqual(after, before)

    def test_ac5_real_store_keeps_response_mode_distinct_localized_and_read_only(self):
        miniapp = miniapp_module(self)
        user_id = 7105
        temporary = tempfile.TemporaryDirectory(prefix="miniapp-mirror-mode-")
        self.addCleanup(temporary.cleanup)
        store = DatabaseStore(
            f"sqlite:///{Path(temporary.name) / 'mirror-mode.sqlite3'}"
        )
        self.addCleanup(store.close)
        fixed = datetime(2026, 8, 1, 12, 0, tzinfo=timezone.utc)
        with store.Session.begin() as session:
            session.add(
                User(
                    telegram_user_id=user_id,
                    role="learner",
                    access_status="active",
                    privacy_status="active",
                    language_code="en",
                    native_language="en",
                    updated_at=fixed,
                    created_at=fixed,
                )
            )
        with store.Session.begin() as session:
            session.execute(
                text(
                    "UPDATE users SET mirror_response_mode = 'both', "
                    "mirror_style = 'coach' "
                    "WHERE telegram_user_id = :user_id"
                ),
                {"user_id": user_id},
            )

        def snapshot():
            with store.Session() as session:
                learner = session.get(User, user_id)
                response_mode, mirror_style = session.execute(
                    text(
                        "SELECT mirror_response_mode, mirror_style FROM users "
                        "WHERE telegram_user_id = :user_id"
                    ),
                    {"user_id": user_id},
                ).one()
                return (
                    response_mode,
                    mirror_style,
                    learner.updated_at,
                    session.scalar(select(func.count()).select_from(UserProgress)),
                    session.scalar(select(func.count()).select_from(AIWallet)),
                    session.scalar(select(func.count()).select_from(AIUsage)),
                )

        expected = {
            "en": ("Text and voice", "Learning coach"),
            "fr": ("Texte et voix", "Coach pédagogique"),
            "de": ("Text und Sprache", "Lerncoach"),
            "ja": ("テキストと音声", "コーチ"),
            "ar": ("نص وصوت", "مدرّب"),
            "zh": ("文字和语音", "教练"),
            "ru": ("Текст и голос", "Наставник"),
            "es": ("Texto y voz", "Entrenador"),
        }
        before = snapshot()
        observed = {}
        for locale in INTERFACE_LOCALES:
            payload = miniapp.build_bootstrap(
                store,
                user_id=user_id,
                display_name="Learner",
                locale=locale,
                catalog=bot.CATALOG,
                products=[],
                checkout_enabled=False,
                ai_enabled=False,
                voice_enabled=False,
            )
            observed[locale] = (
                payload["settings"]["mirror_mode"],
                payload["settings"]["mirror_style"],
            )

        self.assertEqual(observed, expected)
        self.assertEqual(snapshot(), before, "bootstrap preference reads must be read-only")

    def test_ac3_wrong_attempt_copy_is_not_a_duplicate_review_status(self):
        miniapp = miniapp_module(self)
        expected = {
            "en": "Wrong",
            "fr": "Incorrectes",
            "de": "Falsch",
            "ja": "不正解",
            "ar": "خاطئة",
            "zh": "错误",
            "ru": "Неверно",
            "es": "Incorrectos",
        }
        observed = {
            locale: miniapp.MINIAPP_COPY[locale]["attempts_wrong"]
            for locale in INTERFACE_LOCALES
        }
        self.assertEqual(observed, expected)
        self.assertTrue(
            all(
                observed[locale] != miniapp.MINIAPP_COPY[locale]["word_review"]
                for locale in INTERFACE_LOCALES
            )
        )

    def test_ac7_settings_values_are_localized_and_unknown_values_are_honest(self):
        miniapp = miniapp_module(self)

        def payload(locale, *, unsupported=False):
            store = MagicMock()
            store.access_profile.return_value = {
                "role": "learner",
                "access_status": "active",
                "privacy_status": "active",
                "language_code": locale,
            }
            store.product_profile.return_value = {
                "role": "learner",
                "native_language": "fr",
                "learning_goal": "custom-choice" if unsupported else "travel",
                "daily_word_goal": 10,
                "active_lang": "fr",
                "active_pack_id": None,
                "mirror_style": "custom-choice" if unsupported else "teacher",
            }
            store.load_profile.return_value = {}
            store.load_word_progress.return_value = {}
            store.ai_usage_summary.return_value = {}
            store.get_mirror_preferences.return_value = {
                "mode": "custom-choice" if unsupported else "text",
                "depth": "custom-choice" if unsupported else "balanced",
                "level": "custom-choice" if unsupported else "adaptive",
            }
            return miniapp.build_bootstrap(
                store,
                user_id=7001,
                display_name="Learner",
                locale=locale,
                catalog=bot.CATALOG,
                products=[],
                checkout_enabled=False,
                ai_enabled=True,
                voice_enabled=False,
            )

        supported_raw = {
            "learning_goal": "travel",
            "mirror_mode": "text",
            "mirror_style": "teacher",
            "mirror_depth": "balanced",
            "mirror_level": "adaptive",
        }
        violations = []
        localized_by_locale = {}
        for locale in INTERFACE_LOCALES:
            localized = payload(locale)
            localized_by_locale[locale] = localized["settings"]
            for field, raw_value in supported_raw.items():
                value = str(localized["settings"].get(field) or "").strip()
                if not value or value.casefold() == raw_value:
                    violations.append((locale, field, value))
            unknown = payload(locale, unsupported=True)
            for field in supported_raw:
                if unknown["settings"].get(field) != unknown["copy"].get("setting_unknown"):
                    violations.append((locale, f"unknown:{field}", unknown["settings"].get(field)))
        self.assertEqual(violations, [])
        for field in supported_raw:
            self.assertNotEqual(
                localized_by_locale["fr"][field],
                localized_by_locale["en"][field],
            )

    def test_ac7_personal_learning_goal_is_localized_in_all_eight_locales(self):
        miniapp = miniapp_module(self)
        rendered = {}
        violations = []
        for locale in INTERFACE_LOCALES:
            store = MagicMock()
            store.access_profile.return_value = {
                "role": "learner",
                "access_status": "active",
                "privacy_status": "active",
                "language_code": locale,
            }
            store.product_profile.return_value = {
                "role": "learner",
                "native_language": locale,
                "learning_goal": "personal",
                "daily_word_goal": 10,
                "active_lang": "en",
                "active_pack_id": None,
                "mirror_style": "teacher",
            }
            store.load_profile.return_value = {}
            store.load_word_progress.return_value = {}
            store.ai_usage_summary.return_value = {}
            store.get_mirror_preferences.return_value = {}
            payload = miniapp.build_bootstrap(
                store,
                user_id=7001,
                display_name="Learner",
                locale=locale,
                catalog=bot.CATALOG,
                products=[],
                checkout_enabled=False,
                ai_enabled=False,
                voice_enabled=False,
            )
            value = str(payload["settings"]["learning_goal"] or "").strip()
            if value.casefold() == "personal" or value == payload["copy"]["setting_unknown"]:
                violations.append((locale, value))
            rendered[locale] = value
        for locale in INTERFACE_LOCALES - {"en"}:
            if rendered[locale] == rendered["en"]:
                violations.append((f"same-as-en:{locale}", rendered[locale]))
        self.assertEqual(violations, [])

    def test_ac4_products_are_one_time_ordered_and_never_create_checkout(self):
        miniapp = miniapp_module(self)
        products = [
            {"product_id": "b", "title": "B", "credits": 50, "price_xtr": 129, "status": "active", "billing_mode": "one_time", "display_order": 20},
            {"product_id": "sub", "title": "Sub", "credits": 100, "price_xtr": 229, "status": "active", "billing_mode": "subscription", "display_order": 5},
            {"product_id": "a", "title": "A", "credits": 20, "price_xtr": 69, "status": "active", "billing_mode": "one_time", "display_order": 10},
            {"product_id": "draft", "title": "Draft", "credits": 1, "price_xtr": 1, "status": "draft", "billing_mode": "one_time", "display_order": 1},
        ]
        service = MagicMock()
        visible = miniapp.visible_credit_products(products, locale="en")
        self.assertEqual(
            [(row["title"], row["credits"], row["price_xtr"]) for row in visible],
            [("A", 20, 69), ("B", 50, 129)],
        )
        self.assertEqual(
            [row["deep_link_action"] for row in visible],
            ["buy_a", "buy_b"],
        )
        self.assertFalse(any("invoice" in row for row in visible))
        service.create_order.assert_not_called()


class MiniAppHTTPContractTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="miniapp-http-")
        self.store = DatabaseStore(
            f"sqlite:///{Path(self.temporary.name) / 'miniapp.sqlite3'}"
        )

    def tearDown(self):
        self.store.close()
        self.temporary.cleanup()

    def app(self, **overrides):
        config = {
            "TESTING": True,
            "SECRET_KEY": "s" * 40,
            "ADMIN_USERNAME": "owner",
            "ADMIN_PASSWORD": "password",
            "MINIAPP_ENABLED": True,
            "MINIAPP_PUBLIC_URL": MINIAPP_URL,
            "MINIAPP_BOT_USERNAME": SAFE_USERNAME,
            "MINIAPP_AUTH_MAX_AGE_SECONDS": 300,
            "BOT_TOKEN_FILE": "/protected/bot-token",
            **overrides,
        }
        return create_app(config, database_store=self.store)

    def _make_erased_active_learner(self, user_id=7001):
        self.store.ensure_user_id(user_id)
        with self.store.Session.begin() as session:
            learner = session.get(User, user_id)
            learner.access_status = "active"
            learner.privacy_status = "erased"
        return self.store.access_profile(user_id)

    def _learner_snapshot(self, user_id=7001):
        with self.store.Session() as session:
            learner = session.get(User, user_id)
            return {
                "count": session.scalar(select(func.count()).select_from(User)),
                "access_status": learner.access_status,
                "privacy_status": learner.privacy_status,
                "first_name": learner.first_name,
                "username": learner.username,
            }

    def test_ac1_real_store_erased_learner_fails_closed_at_access_gate(self):
        miniapp = miniapp_module(self)
        access_profile = self._make_erased_active_learner()
        self.assertEqual(access_profile["access_status"], "active")

        with self.assertRaises(
            miniapp.MiniAppAccessDenied,
            msg=(
                "privacy-erased learner passed the access gate; "
                f"access_profile keys were {sorted(access_profile)}"
            ),
        ):
            miniapp.require_active_learner(self.store, 7001)

    def test_ac1_real_store_erased_http_bootstrap_is_generic_403_without_mutation(self):
        miniapp = miniapp_module(self)
        access_profile = self._make_erased_active_learner()
        self.assertEqual(access_profile["access_status"], "active")
        before = self._learner_snapshot()
        client = self.app().test_client()

        with (
            patch.object(
                miniapp,
                "verify_init_data",
                return_value={
                    "user_id": 7001,
                    "display_name": "Mila",
                    "language_code": "fr",
                },
            ),
            patch.object(
                self.store,
                "ensure_user_id",
                wraps=self.store.ensure_user_id,
            ) as ensure_user,
        ):
            response = client.get(
                "/miniapp/api/bootstrap",
                headers={"X-Telegram-Init-Data": signed_init_data()},
            )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.headers["Cache-Control"], "no-store")
        self.assertEqual(response.get_json(), {"error": "access_denied"})
        self.assertNotIn("profile", response.get_data(as_text=True).casefold())
        ensure_user.assert_not_called()
        self.assertEqual(self._learner_snapshot(), before)

    def test_ac2_ac4_initial_credit_parity_is_validated_read_only_and_fail_closed(self):
        miniapp = miniapp_module(self)
        user_id = 7204
        self.store.ensure_user_id(user_id)
        with self.store.Session.begin() as session:
            learner = session.get(User, user_id)
            learner.access_status = "active"
            learner.privacy_status = "active"
        with self.store.Session() as session:
            before = {
                "users": session.scalar(select(func.count()).select_from(User)),
                "wallets": session.scalar(select(func.count()).select_from(AIWallet)),
                "usage": session.scalar(select(func.count()).select_from(AIUsage)),
            }

        client = self.app(AI_INITIAL_CREDITS="9").test_client()
        with (
            patch.object(
                miniapp,
                "verify_init_data",
                return_value={
                    "user_id": user_id,
                    "display_name": "Mila",
                    "language_code": "fr",
                },
            ),
            patch.object(
                self.store,
                "ai_usage_summary",
                wraps=self.store.ai_usage_summary,
            ) as usage_summary,
        ):
            response = client.get(
                "/miniapp/api/bootstrap",
                headers={"X-Telegram-Init-Data": signed_init_data(user_id=user_id)},
            )

        violations = []
        if response.status_code != 200:
            violations.append(("status", response.status_code))
        else:
            available = response.get_json().get("credits", {}).get("available")
            if available != 9:
                violations.append(("available_credits", available))
        observed_initial = (
            usage_summary.call_args.kwargs.get("initial_credits")
            if usage_summary.call_args is not None
            else None
        )
        if observed_initial != 9:
            violations.append(("initial_credits", observed_initial))

        with self.store.Session() as session:
            after = {
                "users": session.scalar(select(func.count()).select_from(User)),
                "wallets": session.scalar(select(func.count()).select_from(AIWallet)),
                "usage": session.scalar(select(func.count()).select_from(AIUsage)),
            }
        if after != before:
            violations.append(("storage_mutation", before, after))

        for invalid in ("-1", "not-an-integer"):
            try:
                self.app(AI_INITIAL_CREDITS=invalid)
            except (RuntimeError, TypeError, ValueError):
                continue
            violations.append(("invalid_configuration_accepted", invalid))

        self.assertEqual(violations, [])

    def test_ac1_shell_static_headers_and_admin_csp_are_route_specific(self):
        client = self.app().test_client()
        shell = client.get("/miniapp")
        self.assertEqual(shell.status_code, 200)
        self.assertEqual(shell.headers["Cache-Control"], "no-store")
        csp = shell.headers["Content-Security-Policy"]
        self.assertIn("https://telegram.org", csp)
        self.assertNotIn("frame-ancestors 'none'", csp)
        self.assertNotIn(TOKEN, shell.get_data(as_text=True))

        admin = client.get("/admin/login")
        self.assertIn(
            "frame-ancestors 'none'",
            admin.headers["Content-Security-Policy"],
        )
        for asset in ("/miniapp/static/miniapp.css", "/miniapp/static/miniapp.js"):
            response = client.get(asset)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.headers["Cache-Control"], "no-store")

    def test_ac1_err2_api_errors_are_fixed_no_store_and_never_partial(self):
        client = self.app().test_client()
        cases = (
            ({}, 401),
            ({"X-Telegram-Init-Data": "bad"}, 401),
            ({"X-Telegram-Init-Data": "x" * 9000}, 401),
        )
        for headers, status in cases:
            with self.subTest(status=status, headers=bool(headers)):
                response = client.get("/miniapp/api/bootstrap", headers=headers)
                self.assertEqual(response.status_code, status)
                self.assertEqual(response.headers["Cache-Control"], "no-store")
                self.assertEqual(response.get_json(), {"error": "authentication_failed"})

        miniapp = miniapp_module(self)
        with (
            patch.object(miniapp, "verify_init_data", return_value={"user_id": 7001, "display_name": "Mila", "language_code": "en"}),
            patch.object(miniapp, "build_bootstrap", side_effect=RuntimeError("PRIVATE database url")),
        ):
            response = client.get(
                "/miniapp/api/bootstrap",
                headers={"X-Telegram-Init-Data": signed_init_data()},
            )
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.get_json(), {"error": "temporarily_unavailable"})
        self.assertNotIn("PRIVATE", response.get_data(as_text=True))

    def test_ec2_disabled_route_is_404_and_requires_no_token(self):
        client = self.app(
            MINIAPP_ENABLED=False,
            MINIAPP_PUBLIC_URL="",
            MINIAPP_BOT_USERNAME="",
            BOT_TOKEN_FILE="",
        ).test_client()
        self.assertEqual(client.get("/miniapp").status_code, 404)
        self.assertEqual(client.get("/miniapp/api/bootstrap").status_code, 404)


class MiniAppFrontendAndTelegramContractTest(unittest.IsolatedAsyncioTestCase):
    def test_ac7_frontend_has_five_accessible_tabs_rtl_and_reduced_motion(self):
        root = Path(__file__).resolve().parents[1]
        html_path = root / "mydictionary/templates/miniapp.html"
        css_path = root / "mydictionary/static/miniapp.css"
        js_path = root / "mydictionary/static/miniapp.js"
        for path in (html_path, css_path, js_path):
            self.assertTrue(path.is_file(), f"missing Mini App asset: {path}")
        html = html_path.read_text(encoding="utf-8").casefold()
        css = css_path.read_text(encoding="utf-8").casefold()
        js = js_path.read_text(encoding="utf-8").casefold()
        self.assertEqual(html.count('role="tab"'), 5)
        for tab in ("profile", "words", "credits", "languages", "settings"):
            self.assertIn(f'data-tab="{tab}"', html)
        for marker in (
            ":focus-visible",
            "min-height: 44px",
            "env(safe-area-inset-bottom)",
            "@media (prefers-reduced-motion: reduce)",
            "min-width: 320px",
        ):
            self.assertIn(marker, css)
        self.assertIn('document.documentelement.dir = "rtl"', js)
        for state in ("loading", "empty", "error", "disabled"):
            self.assertIn(state, f"{html}\n{js}")
        for forbidden in ("lottery", "ticket exchange", "daily reward", "unlimited"):
            self.assertNotIn(forbidden, f"{html}\n{js}")

    async def test_ac6_bot_app_command_private_launcher_menu_sync_and_deep_links(self):
        self.assertTrue(hasattr(bot, "cmd_app"), "missing /app handler")
        private_message = SimpleNamespace(reply_text=AsyncMock())
        private_update = SimpleNamespace(
            message=private_message,
            effective_chat=SimpleNamespace(id=7001, type="private"),
            effective_user=SimpleNamespace(id=7001),
        )
        context = SimpleNamespace(user_data={"interface_locale": "fr"})
        settings = SimpleNamespace(
            enabled=True,
            public_url=MINIAPP_URL,
            bot_username=SAFE_USERNAME,
        )
        with patch.object(bot, "MINIAPP_SETTINGS", settings, create=True):
            await bot.cmd_app.__wrapped__(private_update, context)
        button = private_message.reply_text.await_args.kwargs["reply_markup"].inline_keyboard[0][0]
        self.assertEqual(button.web_app.url, MINIAPP_URL)
        self.assertNotIn("7001", button.web_app.url)

        group_message = SimpleNamespace(reply_text=AsyncMock())
        group_update = SimpleNamespace(
            message=group_message,
            effective_chat=SimpleNamespace(id=-100, type="group"),
            effective_user=SimpleNamespace(id=7001),
        )
        with patch.object(bot, "MINIAPP_SETTINGS", settings, create=True):
            await bot.cmd_app.__wrapped__(group_update, context)
        rendered = repr(group_message.reply_text.await_args)
        self.assertNotIn("WebAppInfo", rendered)
        self.assertNotIn(MINIAPP_URL, rendered)

        commands = bot.build_bot_commands(
            ai_enabled=True, miniapp_enabled=True, locale="fr"
        )
        self.assertIn("app", [command.command for command in commands])
        source = importlib.import_module("inspect").getsource(bot.manual_polling)
        self.assertIn('CommandHandler("app", cmd_app)', source)
        self.assertIn("set_chat_menu_button", importlib.import_module("inspect").getsource(bot.sync_telegram_profile))
        for action in ("learn", "ai", "buy", "lang", "settings", "privacy", "help"):
            self.assertEqual(
                bot.miniapp_start_action(f"miniapp_{action}"),
                action,
            )

    async def test_ac6_disabled_miniapp_resets_stale_menu_and_removes_app_commands(self):
        telegram_bot = SimpleNamespace(
            set_my_commands=AsyncMock(),
            set_my_name=AsyncMock(),
            set_my_short_description=AsyncMock(),
            set_my_description=AsyncMock(),
            set_chat_menu_button=AsyncMock(),
        )
        profile = {
            "bot_name": "MY DICTIONARY",
            "bot_short_description": "Short",
            "bot_description": "Description",
        }
        disabled = SimpleNamespace(enabled=False, public_url="")
        with (
            patch.object(bot, "MINIAPP_SETTINGS", disabled),
            patch.object(bot, "get_bot_profile", return_value=profile),
        ):
            await bot.sync_telegram_profile(telegram_bot)

        for call in telegram_bot.set_my_commands.await_args_list:
            self.assertNotIn("app", [command.command for command in call.args[0]])
        telegram_bot.set_chat_menu_button.assert_awaited_once()
        menu_button = telegram_bot.set_chat_menu_button.await_args.kwargs[
            "menu_button"
        ]
        self.assertIsInstance(menu_button, MenuButtonDefault)

    async def test_err2_disabled_menu_reset_failure_is_nonblocking(self):
        telegram_bot = SimpleNamespace(
            set_my_commands=AsyncMock(),
            set_my_name=AsyncMock(),
            set_my_short_description=AsyncMock(),
            set_my_description=AsyncMock(),
            set_chat_menu_button=AsyncMock(
                side_effect=bot.TelegramError("temporary menu failure")
            ),
        )
        profile = {
            "bot_name": "MY DICTIONARY",
            "bot_short_description": "Short",
            "bot_description": "Description",
        }
        disabled = SimpleNamespace(enabled=False, public_url="")
        with (
            patch.object(bot, "MINIAPP_SETTINGS", disabled),
            patch.object(bot, "get_bot_profile", return_value=profile),
        ):
            await bot.sync_telegram_profile(telegram_bot)

        telegram_bot.set_chat_menu_button.assert_awaited_once()
        telegram_bot.set_my_commands.assert_awaited()
        telegram_bot.set_my_name.assert_awaited_once()
        telegram_bot.set_my_short_description.assert_awaited_once()
        telegram_bot.set_my_description.assert_awaited_once()

    async def test_ac6_start_deep_links_obey_target_specific_safety_limits(self):
        for action, expected_scope in (
            ("learn", "learning"),
            ("ai", "ai"),
            ("buy", "billing"),
        ):
            with self.subTest(action=action):
                message = SimpleNamespace(reply_text=AsyncMock())
                user = SimpleNamespace(id=7001, first_name="Mila", language_code="en")
                update = SimpleNamespace(
                    message=message,
                    effective_message=message,
                    effective_user=user,
                    callback_query=None,
                )
                context = SimpleNamespace(args=[f"miniapp_{action}"], user_data={})
                store = MagicMock()
                store.access_profile.return_value = {
                    "role": "learner",
                    "access_status": "active",
                }
                runtime = SimpleNamespace(
                    access_status="active",
                    role="learner",
                    onboarding_completed=True,
                    store=store,
                    user_id=7001,
                )
                policies = {
                    "cmd_start": ("default", object()),
                    "cmd_learn": ("learning", object()),
                    "cmd_ai": ("ai", object()),
                    "cmd_buy": ("billing", object()),
                }
                safety = SimpleNamespace(
                    enabled=True,
                    for_handler=MagicMock(side_effect=lambda name: policies[name]),
                )
                limiter = MagicMock()
                limiter.consume.side_effect = (
                    SimpleNamespace(allowed=True, retry_after_seconds=0),
                    SimpleNamespace(allowed=False, retry_after_seconds=60),
                )
                learn_probe = MagicMock(
                    return_value=bot.CATALOG.require("en-basics-100")
                )
                ai_probe = AsyncMock()
                buy_probe = MagicMock(return_value=False)

                @contextmanager
                def runtime_scope(_user):
                    token = bot._ACTIVE_RUNTIME.set(runtime)
                    try:
                        yield runtime
                    finally:
                        bot._ACTIVE_RUNTIME.reset(token)

                with (
                    patch.object(bot, "get_store", return_value=store),
                    patch.object(bot, "BOT_ACCESS_MODE", "public"),
                    patch.object(bot, "ALLOWED_USER_IDS", set()),
                    patch.object(bot, "ADMIN_USER_IDS", set()),
                    patch.object(
                        bot,
                        "learner_scope",
                        side_effect=runtime_scope,
                    ),
                    patch.object(bot, "SAFETY_SETTINGS", safety),
                    patch.object(
                        bot,
                        "PersistentRateLimiter",
                        return_value=limiter,
                    ),
                    patch.object(bot, "record_product_event"),
                    patch.object(bot, "active_content_pack", learn_probe),
                    patch.object(bot, "handle_mirror_question", ai_probe),
                    patch.object(bot, "_billing_entry_enabled_for", buy_probe),
                ):
                    await bot.cmd_start(update, context)

                self.assertEqual(
                    [call.kwargs["scope"] for call in limiter.consume.call_args_list],
                    ["default", expected_scope],
                )
                self.assertEqual(
                    [call.kwargs["policy"] for call in limiter.consume.call_args_list],
                    [policies["cmd_start"][1], policies[f"cmd_{action}"][1]],
                )
                {"learn": learn_probe, "ai": ai_probe, "buy": buy_probe}[
                    action
                ].assert_not_called()
                store.update_product_profile.assert_called_once()
                message.reply_text.assert_awaited_once()

    async def test_ac6_allowed_ai_deep_link_opens_free_menu_with_empty_target_args(self):
        message = SimpleNamespace(reply_text=AsyncMock())
        user = SimpleNamespace(id=7001, first_name="Mila", language_code="en")
        update = SimpleNamespace(
            message=message,
            effective_message=message,
            effective_user=user,
            callback_query=None,
        )
        context = SimpleNamespace(args=["miniapp_ai"], user_data={})
        store = MagicMock()
        store.access_profile.return_value = {
            "role": "learner",
            "access_status": "active",
        }
        runtime = SimpleNamespace(
            access_status="active",
            role="learner",
            onboarding_completed=True,
            store=store,
            user_id=7001,
        )
        policies = {
            "cmd_start": ("default", object()),
            "cmd_ai": ("ai", object()),
        }
        safety = SimpleNamespace(
            enabled=True,
            for_handler=MagicMock(side_effect=lambda name: policies[name]),
        )
        limiter = MagicMock()
        limiter.consume.return_value = SimpleNamespace(
            allowed=True,
            retry_after_seconds=0,
        )
        menu = AsyncMock()
        mirror = AsyncMock()
        tutor_service = MagicMock()

        @contextmanager
        def runtime_scope(_user):
            token = bot._ACTIVE_RUNTIME.set(runtime)
            try:
                yield runtime
            finally:
                bot._ACTIVE_RUNTIME.reset(token)

        with (
            patch.object(bot, "get_store", return_value=store),
            patch.object(bot, "BOT_ACCESS_MODE", "public"),
            patch.object(bot, "ALLOWED_USER_IDS", set()),
            patch.object(bot, "ADMIN_USER_IDS", set()),
            patch.object(bot, "learner_scope", side_effect=runtime_scope),
            patch.object(bot, "SAFETY_SETTINGS", safety),
            patch.object(bot, "PersistentRateLimiter", return_value=limiter),
            patch.object(bot, "AI_SETTINGS", SimpleNamespace(enabled=True)),
            patch.object(bot, "record_product_event"),
            patch.object(bot, "send_ai_tutor_menu", menu),
            patch.object(bot, "handle_mirror_question", mirror),
            patch.object(bot, "get_ai_tutor_service", tutor_service),
        ):
            await bot.cmd_start(update, context)

        violations = []
        scopes = [call.kwargs["scope"] for call in limiter.consume.call_args_list]
        if scopes != ["default", "ai"]:
            violations.append(("limiter_scopes", scopes))
        if menu.await_count != 1:
            violations.append(("menu_calls", menu.await_count))
        if mirror.await_count:
            violations.append(("mirror_calls", mirror.await_count))
        if tutor_service.call_count:
            violations.append(("provider_service_calls", tutor_service.call_count))
        if store.ai_usage_summary.call_count:
            violations.append(("metering_calls", store.ai_usage_summary.call_count))
        self.assertEqual(violations, [])

    def test_ac7_all_eight_locales_and_unsupported_fallback_are_complete(self):
        miniapp = miniapp_module(self)
        self.assertEqual(set(miniapp.MINIAPP_COPY), INTERFACE_LOCALES)
        missing = {}
        for locale in INTERFACE_LOCALES:
            absent = sorted(
                key
                for key in MINIAPP_COPY_KEYS
                if not str(miniapp.MINIAPP_COPY[locale].get(key) or "").strip()
            )
            if absent:
                missing[locale] = absent
        self.assertEqual(missing, {})
        self.assertEqual(miniapp.miniapp_locale("it"), "en")
        self.assertEqual(miniapp.miniapp_text_direction("ar"), "rtl")
        self.assertEqual(miniapp.miniapp_text_direction("fr"), "ltr")

    def test_ac7_frontend_binds_every_visible_label_without_raw_or_english_copy(self):
        root = Path(__file__).resolve().parents[1]
        html = (root / "mydictionary/templates/miniapp.html").read_text(
            encoding="utf-8"
        )
        js = (root / "mydictionary/static/miniapp.js").read_text(encoding="utf-8")
        combined = f"{html}\n{js}"

        violations = []
        for key in MINIAPP_COPY_KEYS:
            bindings = (
                f'data-i18n="{key}"',
                f'data-i18n-aria-label="{key}"',
                f"copy.{key}",
                f'copy["{key}"]',
            )
            if not any(binding in combined for binding in bindings):
                violations.append(f"unbound:{key}")

        for heading_and_tab in ("profile", "words", "credits", "languages", "settings"):
            if html.count(f'data-i18n="{heading_and_tab}"') < 2:
                violations.append(f"heading-and-tab:{heading_and_tab}")
        self.assertEqual(violations, [])

    def test_ac7_frontend_contains_no_raw_keys_or_hard_coded_english_copy(self):
        root = Path(__file__).resolve().parents[1]
        html = (root / "mydictionary/templates/miniapp.html").read_text(
            encoding="utf-8"
        )
        js = (root / "mydictionary/static/miniapp.js").read_text(encoding="utf-8")
        combined = f"{html}\n{js}"
        violations = []
        self.assertNotIn('key.replaceAll("_", " ")', js)
        for raw_english in (
            ">Loading…<",
            ">Something went wrong.<",
            ">Retry<",
            ">Profile<",
            ">My words<",
            ">AI credits<",
            ">Languages<",
            ">Settings<",
            ">Continue lesson<",
            ">AI Tutor<",
            ">Share<",
            ">No tracked words yet.<",
            ">Start a lesson<",
            ">Change in Telegram<",
            ">Open settings<",
            ">Privacy<",
            'metric("Level"',
            'metric("Available"',
            'word.due ? "Review" : "Learned"',
        ):
            if raw_english in combined:
                violations.append(raw_english)
        self.assertEqual(violations, [])

    def test_ac2_ac5_frontend_visibly_renders_all_real_profile_language_and_feature_data(self):
        root = Path(__file__).resolve().parents[1]
        js = (root / "mydictionary/static/miniapp.js").read_text(encoding="utf-8")
        for data_reference in (
            "progress.today_xp",
            "data.profile.daily_word_goal",
            "progress.learned_words",
            "data.features.ai",
            "data.features.voice",
            "language.word_count",
            "language.current",
            "language.direction",
        ):
            with self.subTest(data_reference=data_reference):
                self.assertIn(data_reference, js)
        self.assertRegex(
            js,
            r'text\(node\("current-language"\),[^;\n]*\.label',
            "the current language must use its localized catalog label, not a raw code",
        )
        self.assertNotIn('language.current ? "✓" : language.word_count', js)

    def test_ac7_theme_safe_areas_long_navigation_and_keyboard_tabs_are_accessible(self):
        root = Path(__file__).resolve().parents[1]
        html = (root / "mydictionary/templates/miniapp.html").read_text(
            encoding="utf-8"
        )
        css = (root / "mydictionary/static/miniapp.css").read_text(encoding="utf-8")
        js = (root / "mydictionary/static/miniapp.js").read_text(encoding="utf-8")
        for variable in (
            "--tg-theme-bg-color",
            "--tg-theme-text-color",
            "--tg-theme-button-color",
            "--tg-theme-button-text-color",
            "--tg-theme-secondary-bg-color",
        ):
            with self.subTest(theme_variable=variable):
                self.assertRegex(css, rf"var\({re.escape(variable)},\s*[^)]+\)")
        for edge in ("top", "right", "bottom", "left"):
            with self.subTest(safe_area=edge):
                self.assertIn(f"env(safe-area-inset-{edge})", css)
        self.assertNotIn("text-overflow: ellipsis", css)
        self.assertNotIn("clamp(.58rem", css)
        for tab in ("profile", "words", "credits", "languages", "settings"):
            with self.subTest(tab=tab):
                self.assertRegex(
                    html,
                    rf'<button(?=[^>]*id="tab-{tab}")(?=[^>]*aria-controls="panel-{tab}")[^>]*>',
                )
                self.assertRegex(
                    html,
                    rf'<section(?=[^>]*id="panel-{tab}")(?=[^>]*role="tabpanel")[^>]*>',
                )
        for key in ('"ArrowLeft"', '"ArrowRight"', '"Home"', '"End"'):
            self.assertIn(key, js)
        self.assertIn("tabIndex", js)
        self.assertIn(".focus()", js)

    def test_ac7_prebootstrap_states_use_telegram_locale_hint_without_identity(self):
        miniapp = miniapp_module(self)
        root = Path(__file__).resolve().parents[1]
        js = (root / "mydictionary/static/miniapp.js").read_text(encoding="utf-8")
        self.assertIn("initDataUnsafe", js)
        self.assertIn("language_code", js)
        self.assertNotIn("initDataUnsafe.user.id", js)
        self.assertNotIn("initDataUnsafe.user.username", js)
        for locale in INTERFACE_LOCALES:
            for key in ("loading", "error", "retry"):
                with self.subTest(locale=locale, key=key):
                    self.assertIn(
                        json.dumps(miniapp.MINIAPP_COPY[locale][key], ensure_ascii=False),
                        js,
                    )
        self.assertIn('"en"', js)
        self.assertLess(js.index("language_code"), js.index("fetch("))

    def test_err3_initial_bootstrap_is_bounded_and_recovers_without_reload(self):
        root = Path(__file__).resolve().parents[1]
        html = (root / "mydictionary/templates/miniapp.html").read_text(
            encoding="utf-8"
        )
        js = (root / "mydictionary/static/miniapp.js").read_text(encoding="utf-8")

        violations = []
        if "AbortController" not in js:
            violations.append("bootstrap-fetch-has-no-abort-controller")
        if re.search(r"setTimeout\([\s\S]{0,240}?\.abort\(\)", js) is None:
            violations.append("bootstrap-fetch-has-no-bounded-timeout")
        if re.search(r"signal\s*:\s*[A-Za-z_$][\w$]*\.signal", js) is None:
            violations.append("bootstrap-timeout-is-not-wired-to-fetch")
        if "clearTimeout(" not in js:
            violations.append("bootstrap-timeout-is-not-cleaned-up")
        if re.search(r"BOOTSTRAP_MAX_ATTEMPTS\s*=\s*[2-9]", js) is None:
            violations.append("initial-bootstrap-has-no-bounded-automatic-retry")
        if re.search(r"location\s*\.\s*reload\s*\(", js):
            violations.append("bootstrap-recovery-must-not-loop-page-reloads")
        if 'headers: {"X-Telegram-Init-Data": webApp.initData}' not in js:
            violations.append("bootstrap-retry-does-not-read-authenticated-init-data")
        if 'id="retry-button"' not in html or 'data-i18n="retry"' not in html:
            violations.append("exhausted-retries-have-no-localized-manual-retry")

        self.assertEqual(violations, [])

    def test_ac7_languages_use_one_flag_and_a_dedicated_localized_current_label(self):
        miniapp = miniapp_module(self)
        root = Path(__file__).resolve().parents[1]
        js = (root / "mydictionary/static/miniapp.js").read_text(encoding="utf-8")
        violations = [
            f"missing-copy:{locale}"
            for locale in INTERFACE_LOCALES
            if not str(miniapp.MINIAPP_COPY[locale].get("language_current") or "").strip()
        ]
        if "`${language.flag} ${language.label}`" in js:
            violations.append("double-flag-render")
        if (
            re.search(
                r"text\(label,\s*(?:language\.label|languageDisplayLabel\(language\))\)",
                js,
            )
            is None
        ):
            violations.append("catalog-label-not-rendered")
        if "copy.language_current" not in js:
            violations.append("current-label-not-bound")
        if "text(current, copy.feature_enabled)" in js:
            violations.append("generic-feature-label-used-for-current")
        self.assertEqual(violations, [])

    def test_ac7_prebootstrap_nav_and_rtl_keyboard_are_localized_and_accessible(self):
        miniapp = miniapp_module(self)
        root = Path(__file__).resolve().parents[1]
        html = (root / "mydictionary/templates/miniapp.html").read_text(
            encoding="utf-8"
        )
        js = (root / "mydictionary/static/miniapp.js").read_text(encoding="utf-8")
        prebootstrap = js[
            js.index("const prebootstrapCopy") : js.index("const hintedLanguage")
        ]
        nav_hidden = bool(re.search(r"<nav(?=[^>]*class=\"bottom-nav\")(?=[^>]*hidden)[^>]*>", html))
        nav_revealed = bool(
            re.search(r"bottom-nav[^\n;]{0,160}hidden\s*=\s*false", js)
        )
        nav_localized = all(
            json.dumps(miniapp.MINIAPP_COPY[locale][key], ensure_ascii=False)
            in prebootstrap
            for locale in INTERFACE_LOCALES
            for key in (
                "profile",
                "words",
                "credits",
                "languages",
                "settings",
                "navigation_label",
            )
        )
        violations = []
        if not ((nav_hidden and nav_revealed) or nav_localized):
            violations.append("prebootstrap-nav-visible-without-localized-a11y")

        before_fetch = js[: js.index("fetch(")]
        if "document.documentElement.lang = hintedLocale" not in before_fetch:
            violations.append("hinted-lang-not-applied")
        if 'hintedLocale === "ar"' not in before_fetch:
            violations.append("arabic-hint-not-detected")
        if 'document.documentElement.dir = "rtl"' not in before_fetch:
            violations.append("arabic-rtl-not-applied")

        keyboard = js[
            js.index('tab.addEventListener("keydown"') :
            js.index('document.querySelectorAll("[data-action]")')
        ]
        if "rtl" not in keyboard.casefold():
            violations.append("rtl-keyboard-direction-not-read")
        left_swaps = bool(
            re.search(r'ArrowLeft[\s\S]{0,500}\?\s*1\s*:\s*-1', keyboard)
        )
        right_swaps = bool(
            re.search(r'ArrowRight[\s\S]{0,500}\?\s*-1\s*:\s*1', keyboard)
        )
        if not (left_swaps and right_swaps):
            violations.append("rtl-arrow-directions-not-swapped")
        self.assertEqual(violations, [])

    def test_ac7_light_theme_uses_adaptive_readable_tokens_without_forced_dark(self):
        root = Path(__file__).resolve().parents[1]
        html = (root / "mydictionary/templates/miniapp.html").read_text(
            encoding="utf-8"
        )
        css = (root / "mydictionary/static/miniapp.css").read_text(encoding="utf-8")
        violations = []
        if re.search(r'<meta[^>]+name="color-scheme"[^>]+content="dark"', html):
            violations.append("forced-dark-meta")
        if "color-scheme: dark" in css:
            violations.append("forced-dark-css")
        if re.search(
            r"--(?:app-)?muted:\s*var\(--tg-theme-hint-color,\s*[^)]+\)",
            css,
        ) is None:
            violations.append("non-adaptive-muted")
        if re.search(
            r"--(?:app-)?line:\s*var\(--tg-theme-section-separator-color,\s*[^)]+\)",
            css,
        ) is None:
            violations.append("non-adaptive-line")
        if re.search(
            r"\.state-card\s*\{[^}]*background:\s*var\(--(?:app-)?(?:state|surface)",
            css,
        ) is None:
            violations.append("non-adaptive-state")
        self.assertEqual(violations, [])

    def test_ac7_no_telegram_fallback_surfaces_keep_text_contrast_readable(self):
        root = Path(__file__).resolve().parents[1]
        css = (root / "mydictionary/static/miniapp.css").read_text(
            encoding="utf-8"
        )

        def variable_fallback(name):
            match = re.search(
                rf"{re.escape(name)}\s*:\s*(?:var\([^,]+,\s*)?"
                r"(#[0-9a-fA-F]{6})",
                css,
            )
            self.assertIsNotNone(match, f"missing fallback color for {name}")
            return match.group(1)

        def rule_color(selector, *, inherited):
            rule = re.search(rf"{re.escape(selector)}\s*\{{([^}}]+)\}}", css)
            self.assertIsNotNone(rule, f"missing CSS rule for {selector}")
            declaration = re.search(r"(?:^|;)\s*color\s*:\s*([^;]+)", rule.group(1))
            if declaration is None:
                return variable_fallback(inherited)
            value = declaration.group(1).strip()
            direct = re.fullmatch(r"#[0-9a-fA-F]{6}", value)
            if direct:
                return direct.group(0)
            variable = re.fullmatch(r"var\((--[\w-]+)\)", value)
            self.assertIsNotNone(
                variable,
                f"{selector} color needs a testable fallback, got {value!r}",
            )
            return variable_fallback(variable.group(1))

        def contrast(first, second):
            def luminance(value):
                channels = [int(value[index : index + 2], 16) / 255 for index in (1, 3, 5)]
                linear = [
                    channel / 12.92
                    if channel <= 0.04045
                    else ((channel + 0.055) / 1.055) ** 2.4
                    for channel in channels
                ]
                return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]

            lighter, darker = sorted((luminance(first), luminance(second)), reverse=True)
            return (lighter + 0.05) / (darker + 0.05)

        paper = variable_fallback("--paper")
        pairs = {
            "state-card": (
                rule_color(".state-card", inherited="--app-text"),
                variable_fallback("--app-state"),
            ),
            "muted-on-app-bg": (
                variable_fallback("--muted"),
                variable_fallback("--app-bg"),
            ),
            "muted-on-app-surface": (
                variable_fallback("--muted"),
                variable_fallback("--app-surface"),
            ),
            "paper-eyebrow": (rule_color(".eyebrow", inherited="--paper-ink"), paper),
            "paper-metric-caption": (
                rule_color(".metric span", inherited="--paper-ink"),
                paper,
            ),
            "paper-definition-caption": (
                rule_color(".paper-card dt", inherited="--paper-ink"),
                paper,
            ),
        }
        violations = [
            f"{label}={contrast(foreground, background):.2f}:1"
            for label, (foreground, background) in pairs.items()
            if contrast(foreground, background) < 4.5
        ]
        self.assertEqual(
            violations,
            [],
            "no-Telegram fallback colors must keep normal text at WCAG 4.5:1",
        )

    def test_ec2_admin_launcher_forwards_only_safe_miniapp_metadata(self):
        with tempfile.TemporaryDirectory(prefix="miniapp-launcher-") as raw:
            root = Path(raw)
            release = root / "releases" / ("b" * 40)
            python = release / ".venv/bin/python3"
            python.parent.mkdir(parents=True)
            python.write_text("", encoding="utf-8")
            (root / "current").symlink_to(release, target_is_directory=True)
            secrets = root / "admin-secrets.json"
            secrets.write_text(
                json.dumps(
                    {
                        "username": "owner",
                        "password_hash": "hash",
                        "session_secret": "s" * 40,
                    }
                ),
                encoding="utf-8",
            )
            os.chmod(secrets, 0o600)
            (root / "local-config").mkdir()
            token_file = root / "bot-token"
            token_file.write_text(TOKEN, encoding="ascii")
            os.chmod(token_file, 0o600)
            source = {
                "MYDICTIONARY_APP_ROOT": str(root),
                "DATABASE_URL": "postgresql+psycopg://user@/db?host=/tmp",
                "MINIAPP_ENABLED": "true",
                "MINIAPP_PUBLIC_URL": MINIAPP_URL,
                "MINIAPP_BOT_USERNAME": SAFE_USERNAME,
                "MINIAPP_AUTH_MAX_AGE_SECONDS": "300",
                "BOT_TOKEN_FILE": str(token_file),
                "BOT_TOKEN": "must-not-forward",
            }
            _, arguments, environment, _ = admin_launcher.build_process(source)
        for key in (
            "MINIAPP_ENABLED",
            "MINIAPP_PUBLIC_URL",
            "MINIAPP_BOT_USERNAME",
            "MINIAPP_AUTH_MAX_AGE_SECONDS",
            "BOT_TOKEN_FILE",
        ):
            self.assertIn(key, environment)
            self.assertEqual(environment[key], source[key])
        self.assertNotIn("BOT_TOKEN", environment)
        rendered = "\n".join([*arguments, *environment.values()])
        self.assertNotIn(TOKEN, rendered)
        self.assertNotIn("must-not-forward", rendered)


if __name__ == "__main__":
    unittest.main()
