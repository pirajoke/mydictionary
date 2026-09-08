from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import AsyncMock, patch

from alembic import command
from alembic.config import Config
from sqlalchemy import text


os.environ.setdefault("BOT_TOKEN", "123456:TESTTOKEN")
os.environ.setdefault("ALLOWED_USER_ID", "1")

import bot
from mydictionary.storage import DatabaseStore


def _reply_markup(message):
    if message.reply_photo.await_count:
        return message.reply_photo.await_args.kwargs["reply_markup"]
    return message.reply_text.await_args.kwargs["reply_markup"]


def _contains_onboarding_begin(markup) -> bool:
    return any(
        button.callback_data == "onboarding:begin"
        for row in getattr(markup, "inline_keyboard", ())
        for button in row
    )


class OnboardingVersionGateRegressionTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory(
            prefix="onboarding-version-gate-"
        )
        self.store = DatabaseStore(
            f"sqlite:///{Path(self.temp_dir.name) / 'onboarding.db'}"
        )

    def tearDown(self) -> None:
        self.store.close()
        self.temp_dir.cleanup()

    def _message_and_update(self, user_id: int):
        message = SimpleNamespace(
            chat_id=user_id,
            reply_photo=AsyncMock(),
            reply_text=AsyncMock(),
        )
        user = SimpleNamespace(
            id=user_id,
            first_name="Макс",
            language_code="ru",
        )
        update = SimpleNamespace(
            message=message,
            effective_message=message,
            effective_user=user,
            callback_query=None,
        )
        return message, user, update

    async def test_legacy_completed_profile_receives_current_guided_onboarding(self):
        """A legacy completion timestamp must not suppress the new funnel CTA."""

        user_id = 9981
        message, user, update = self._message_and_update(user_id)
        self.store.ensure_user(user)
        self.store.activate_user_access(user_id)
        self.store.activate_pack(
            user_id,
            pack_id="en-basics-100",
            language="en",
            source="legacy_onboarding",
        )
        self.store.update_product_profile(
            user_id,
            native_language="ru",
            learning_goal="general",
            daily_word_goal=10,
            complete_onboarding=True,
        )
        self.assertIsNone(
            self.store.product_profile(user_id)["onboarding_version"]
        )

        with (
            patch.object(bot, "_STORE", self.store),
            patch.object(bot, "BOT_ACCESS_MODE", "public"),
            patch.object(bot, "LEGACY_USER_ID", None),
            patch.object(bot, "ADMIN_USER_IDS", set()),
        ):
            await bot.cmd_start(update, SimpleNamespace(args=[], user_data={}))

        markup = _reply_markup(message)
        self.assertTrue(_contains_onboarding_begin(markup))
        button = markup.inline_keyboard[0][0]
        self.assertIn("Выбрать язык", button.text)

    async def test_current_guided_onboarding_completion_is_not_repeated(self):
        """Completing all current funnel steps keeps returning users past the CTA."""

        user_id = 9982
        message, user, update = self._message_and_update(user_id)
        context = SimpleNamespace(args=[], user_data={})
        query = SimpleNamespace(
            data="onboarding:begin",
            answer=AsyncMock(),
            edit_message_text=AsyncMock(),
            message=message,
        )
        callback_update = SimpleNamespace(
            callback_query=query,
            effective_message=message,
            effective_user=user,
        )

        with (
            patch.object(bot, "_STORE", self.store),
            patch.object(bot, "BOT_ACCESS_MODE", "public"),
            patch.object(bot, "LEGACY_USER_ID", None),
            patch.object(bot, "ADMIN_USER_IDS", set()),
        ):
            for callback_data in (
                "onboarding:begin",
                "onboarding:native:ru",
                "onboarding:pack:en-basics-100",
                "onboarding:goal:conversation",
                "onboarding:preference:practice",
                "onboarding:pace:10",
            ):
                query.data = callback_data
                await bot.onboarding_cb(callback_update, context)

            message.reply_photo.reset_mock()
            message.reply_text.reset_mock()
            await bot.cmd_start(update, context)

        self.assertEqual(
            self.store.product_profile(user_id)["onboarding_version"],
            bot.CURRENT_ONBOARDING_VERSION,
        )
        self.assertFalse(_contains_onboarding_begin(_reply_markup(message)))

    def test_migration_backfills_only_profiles_with_current_funnel_evidence(self):
        legacy_user_id = 9983
        current_user_id = 9984
        for user_id in (legacy_user_id, current_user_id):
            self.store.ensure_user_id(user_id)
            self.store.update_product_profile(
                user_id,
                native_language="ru",
                learning_goal="basics",
                daily_word_goal=10,
                complete_onboarding=True,
            )
        self.store.record_event(
            current_user_id,
            "onboarding_preference_selected",
            properties={"mode": "practice"},
        )

        database_url = str(self.store.engine.url)
        self.store.close()
        root = Path(__file__).resolve().parents[1]
        config = Config(str(root / "alembic.ini"))
        config.attributes["configure_logging"] = False
        config.set_main_option("script_location", str(root / "migrations"))
        config.set_main_option("sqlalchemy.url", database_url)
        command.downgrade(config, "0019_referral_program_v1")
        command.upgrade(config, "head")
        self.store = DatabaseStore(database_url, migrate=False)

        with self.store.engine.connect() as connection:
            versions = dict(
                connection.execute(
                    text(
                        "SELECT telegram_user_id, onboarding_version FROM users "
                        "WHERE telegram_user_id IN (:legacy_id, :current_id)"
                    ),
                    {
                        "legacy_id": legacy_user_id,
                        "current_id": current_user_id,
                    },
                ).all()
            )
        self.assertIsNone(versions[legacy_user_id])
        self.assertEqual(
            versions[current_user_id], bot.CURRENT_ONBOARDING_VERSION
        )
