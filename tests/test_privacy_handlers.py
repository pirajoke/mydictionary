import os
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import AsyncMock, patch

os.environ.setdefault("BOT_TOKEN", "123456:TESTTOKEN")

import bot
from mydictionary.storage import DatabaseStore, User


class PrivacyHandlerTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="mydictionary-privacy-handler-")
        self.store = DatabaseStore(
            f"sqlite:///{self.temporary.name}/test.sqlite3"
        )
        self.user = SimpleNamespace(
            id=991,
            username="privacy-user",
            first_name="Privacy",
            last_name="User",
            language_code="ru",
        )
        self.store.ensure_user(self.user)
        self.store.activate_user_access(self.user.id)

    async def asyncTearDown(self):
        self.store.close()
        self.temporary.cleanup()

    async def test_confirmation_erases_data_and_clears_telegram_session(self):
        query = SimpleNamespace(
            data="privacy:confirm",
            answer=AsyncMock(),
            edit_message_text=AsyncMock(),
        )
        update = SimpleNamespace(callback_query=query)
        context = SimpleNamespace(user_data={"block_session": "private"})

        with (
            patch.object(bot, "get_store", return_value=self.store),
            bot.learner_scope(self.user),
        ):
            await bot.privacy_cb.__wrapped__(update, context)

        self.assertEqual(context.user_data, {})
        query.answer.assert_awaited_once_with("Данные удалены.")
        with self.store.Session() as session:
            user = session.get(User, self.user.id)
            self.assertEqual(user.privacy_status, "erased")
            self.assertEqual(user.access_status, "blocked")

    async def test_request_requires_a_second_explicit_confirmation(self):
        query = SimpleNamespace(
            data="privacy:request",
            answer=AsyncMock(),
            edit_message_text=AsyncMock(),
        )
        update = SimpleNamespace(callback_query=query)
        context = SimpleNamespace(user_data={})

        await bot.privacy_cb.__wrapped__(update, context)

        query.answer.assert_awaited_once_with()
        markup = query.edit_message_text.await_args.kwargs["reply_markup"]
        callback_values = [button.callback_data for button in markup.inline_keyboard[0]]
        self.assertEqual(callback_values, ["privacy:confirm", "privacy:cancel"])
        with self.store.Session() as session:
            self.assertEqual(session.get(User, self.user.id).privacy_status, "active")

    async def test_voice_consent_can_be_revoked_without_erasing_profile(self):
        self.store.grant_consent(
            self.user.id,
            consent_type="voice_processing",
            document_version=bot.VOICE_SETTINGS.consent_version,
            source="telegram",
        )
        query = SimpleNamespace(
            data="privacy:voice_revoke",
            answer=AsyncMock(),
            edit_message_text=AsyncMock(),
        )
        update = SimpleNamespace(
            callback_query=query,
            effective_user=SimpleNamespace(id=self.user.id),
        )
        context = SimpleNamespace(user_data={"pending_voice_consent": {}})

        with (
            patch.object(bot, "get_store", return_value=self.store),
            patch.object(bot, "record_product_event"),
            bot.learner_scope(self.user),
        ):
            await bot.privacy_cb.__wrapped__(update, context)

        self.assertFalse(
            self.store.has_consent(
                self.user.id,
                consent_type="voice_processing",
                document_version=bot.VOICE_SETTINGS.consent_version,
            )
        )
        self.assertNotIn("pending_voice_consent", context.user_data)
        with self.store.Session() as session:
            self.assertEqual(session.get(User, self.user.id).privacy_status, "active")

    async def test_ac_04_privacy_shows_and_revokes_ai_processing_consent(self):
        version = "ai-processing-2026-08-09"
        self.store.grant_consent(
            self.user.id,
            consent_type="ai_processing",
            document_version=version,
            source="telegram",
        )
        message = SimpleNamespace(reply_text=AsyncMock())
        command_update = SimpleNamespace(
            effective_message=message,
            effective_user=SimpleNamespace(id=self.user.id),
        )
        settings = SimpleNamespace(enabled=True, consent_version=version)
        with (
            patch.object(bot, "get_store", return_value=self.store),
            patch.object(bot, "AI_SETTINGS", settings),
            patch.object(
                bot,
                "MIRROR_MEMORY_SETTINGS",
                SimpleNamespace(enabled=True, retention_days=7),
            ),
            bot.learner_scope(self.user),
        ):
            await bot.cmd_privacy.__wrapped__(command_update, SimpleNamespace())

        rendered = message.reply_text.await_args.args[0]
        self.assertIn("AI", rendered)
        self.assertIn("принято", rendered.lower())
        self.assertIn("20", rendered)
        self.assertIn("7 дней", rendered)

        query = SimpleNamespace(
            data="privacy:ai_revoke",
            answer=AsyncMock(),
            edit_message_text=AsyncMock(),
        )
        callback_update = SimpleNamespace(
            callback_query=query,
            effective_user=SimpleNamespace(id=self.user.id),
        )
        context = SimpleNamespace(
            user_data={"pending_ai_consent": {"request_kind": "command"}}
        )
        with (
            patch.object(bot, "get_store", return_value=self.store),
            patch.object(bot, "AI_SETTINGS", settings),
            patch.object(bot, "record_product_event"),
            bot.learner_scope(self.user),
        ):
            await bot.privacy_cb.__wrapped__(callback_update, context)

        self.assertFalse(
            self.store.has_consent(
                self.user.id,
                consent_type="ai_processing",
                document_version=version,
            )
        )
        self.assertNotIn("pending_ai_consent", context.user_data)
        with self.store.Session() as session:
            self.assertEqual(session.get(User, self.user.id).privacy_status, "active")
