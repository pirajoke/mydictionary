import os
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, MagicMock, patch


os.environ["BOT_TOKEN"] = "123456:TESTTOKEN"
os.environ["ALLOWED_USER_ID"] = "1"
os.environ["DATA_DIR"] = tempfile.mkdtemp(prefix="mydictionary-ai-handlers-")
os.environ["ALLOW_SQLITE_DEV"] = "true"

import bot


AI_CONSENT_VERSION = "ai-processing-2026-08-09"
AI_PROCESSING_NOTICE = (
    "AI Tutor sends only the current question and active learning block to "
    "the configured provider after explicit learner consent."
)


def enabled_settings():
    return SimpleNamespace(
        enabled=True,
        consent_version=AI_CONSENT_VERSION,
        processing_notice=AI_PROCESSING_NOTICE,
    )


class AIConsentHandlerTest(unittest.IsolatedAsyncioTestCase):
    def command_update(self):
        message = SimpleNamespace(reply_text=AsyncMock())
        update = SimpleNamespace(
            effective_message=message,
            message=message,
            effective_user=SimpleNamespace(id=55),
            effective_chat=SimpleNamespace(id=55),
        )
        context = SimpleNamespace(
            user_data={"block_session": "block-1"},
            args=["Объясни", "слово"],
            bot=SimpleNamespace(),
        )
        return update, context, message

    async def test_ac_03_ai_command_requires_current_consent_before_provider_or_credit(self):
        update, context, message = self.command_update()
        store = MagicMock()
        store.has_consent.return_value = False
        with (
            patch.object(bot, "AI_SETTINGS", enabled_settings()),
            patch.object(bot, "get_store", return_value=store),
            patch.object(bot, "get_ai_tutor_service") as service,
            patch.object(bot, "send_ai_tutor_answer", new=AsyncMock()) as answer,
        ):
            await bot.cmd_ai.__wrapped__(update, context)

        store.has_consent.assert_called_once_with(
            55,
            consent_type="ai_processing",
            document_version=AI_CONSENT_VERSION,
        )
        store.reserve_ai_usage.assert_not_called()
        service.assert_not_called()
        answer.assert_not_awaited()
        self.assertEqual(
            context.user_data["pending_ai_consent"]["request_kind"], "command"
        )
        self.assertIn("AI", message.reply_text.await_args.args[0])

    async def test_ac_03_active_block_ai_button_requires_consent_before_provider_or_credit(self):
        query = SimpleNamespace(
            data="bai:block-1",
            answer=AsyncMock(),
            edit_message_text=AsyncMock(),
            message=SimpleNamespace(chat_id=55, reply_text=AsyncMock()),
        )
        update = SimpleNamespace(
            callback_query=query,
            effective_user=SimpleNamespace(id=55),
        )
        context = SimpleNamespace(
            user_data={"block_session": "block-1"}, bot=SimpleNamespace()
        )
        store = MagicMock()
        store.has_consent.return_value = False
        with (
            patch.object(bot, "AI_SETTINGS", enabled_settings()),
            patch.object(bot, "get_store", return_value=store),
            patch.object(bot, "get_ai_tutor_service") as service,
            patch.object(bot, "send_ai_tutor_answer", new=AsyncMock()) as answer,
        ):
            await bot.block_ai_cb.__wrapped__(update, context)

        store.reserve_ai_usage.assert_not_called()
        service.assert_not_called()
        answer.assert_not_awaited()
        query.answer.assert_awaited_once_with()
        pending = context.user_data["pending_ai_consent"]
        self.assertEqual(pending["request_kind"], "active_block")
        self.assertEqual(pending["block_session"], "block-1")

    async def test_ac_03_acceptance_resumes_only_still_valid_pending_request(self):
        query = SimpleNamespace(
            data="aiconsent:accept",
            answer=AsyncMock(),
            edit_message_reply_markup=AsyncMock(),
            message=SimpleNamespace(chat_id=55, reply_text=AsyncMock()),
        )
        update = SimpleNamespace(
            callback_query=query,
            effective_user=SimpleNamespace(id=55),
        )
        context = SimpleNamespace(
            user_data={
                "block_session": "block-1",
                "pending_ai_consent": {
                    "request_kind": "active_block",
                    "block_session": "block-1",
                    "expires_at": 9_999_999_999,
                },
            },
            bot=SimpleNamespace(),
        )
        store = MagicMock()
        store.grant_consent.return_value = True
        with (
            patch.object(bot, "AI_SETTINGS", enabled_settings()),
            patch.object(bot, "get_store", return_value=store),
            patch.object(bot, "send_ai_tutor_answer", new=AsyncMock()) as answer,
        ):
            await bot.ai_consent_cb.__wrapped__(update, context)

        store.grant_consent.assert_called_once_with(
            55,
            consent_type="ai_processing",
            document_version=AI_CONSENT_VERSION,
            source="telegram",
        )
        answer.assert_awaited_once()
        self.assertNotIn("pending_ai_consent", context.user_data)

    async def test_ac_03_cancel_expiry_malformed_and_stale_callbacks_do_nothing(self):
        cases = (
            ("aiconsent:cancel", "block-1", 9_999_999_999),
            ("aiconsent:accept", "block-1", 1),
            ("aiconsent:unexpected", "block-1", 9_999_999_999),
            ("aiconsent:accept", "stale-block", 9_999_999_999),
            ("aiconsent:accept", "block-1", "not-a-timestamp"),
        )
        for callback, pending_block, expires_at in cases:
            with self.subTest(callback=callback, block=pending_block):
                query = SimpleNamespace(
                    data=callback,
                    answer=AsyncMock(),
                    edit_message_reply_markup=AsyncMock(),
                    message=SimpleNamespace(chat_id=55, reply_text=AsyncMock()),
                )
                update = SimpleNamespace(
                    callback_query=query,
                    effective_user=SimpleNamespace(id=55),
                )
                context = SimpleNamespace(
                    user_data={
                        "block_session": "block-1",
                        "pending_ai_consent": {
                            "request_kind": "active_block",
                            "block_session": pending_block,
                            "expires_at": expires_at,
                        },
                    },
                    bot=SimpleNamespace(),
                )
                store = MagicMock()
                with (
                    patch.object(bot, "AI_SETTINGS", enabled_settings()),
                    patch.object(bot, "get_store", return_value=store),
                    patch.object(bot, "get_ai_tutor_service") as service,
                    patch.object(
                        bot, "send_ai_tutor_answer", new=AsyncMock()
                    ) as answer,
                ):
                    await bot.ai_consent_cb.__wrapped__(update, context)

                store.reserve_ai_usage.assert_not_called()
                service.assert_not_called()
                answer.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
