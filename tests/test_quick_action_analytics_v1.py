import os
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock, patch


os.environ.setdefault("BOT_TOKEN", "123456:TESTTOKEN_ABCDEFGHIJKLMNOP")
os.environ.setdefault("ALLOWED_USER_ID", "1")
os.environ.setdefault("ALLOW_SQLITE_DEV", "true")

import bot


def quick_update(action: str, locale: str = "en"):
    message = SimpleNamespace(
        text=bot.quick_action_label(action, locale),
        chat_id=123,
        reply_text=AsyncMock(),
    )
    return (
        SimpleNamespace(
            message=message,
            effective_message=message,
            effective_user=SimpleNamespace(id=1, language_code=locale),
        ),
        SimpleNamespace(user_data={"interface_locale": locale}),
    )


class QuickActionAnalyticsV1Test(unittest.IsolatedAsyncioTestCase):
    async def test_ac1_every_visible_selection_records_stable_action_source(self):
        route_continue = AsyncMock()
        route_review = AsyncMock()
        route_mode = AsyncMock()
        route_words = AsyncMock()
        route_lang = AsyncMock()
        with (
            patch.object(bot, "record_product_event") as record,
            patch.object(bot, "continue_or_start_lesson", new=route_continue),
            patch.object(bot, "start_home_lesson", new=route_review),
            patch.object(bot, "open_practice_mode_picker", new=route_mode),
            patch.object(bot.cmd_learn, "__wrapped__", new=route_words),
            patch.object(bot.cmd_lang, "__wrapped__", new=route_lang),
        ):
            for action in ("continue", "review", "mode", "words", "lang"):
                with self.subTest(action=action):
                    record.reset_mock()
                    update, context = quick_update(action)
                    await bot.handle_quick_action.__wrapped__(update, context)
                    record.assert_called_once_with(
                        "quick_action_selected",
                        source=action,
                    )

    async def test_ac1_selection_is_recorded_before_routing(self):
        update, context = quick_update("mode")
        with patch.object(bot, "record_product_event") as record:
            async def assert_recorded_before_route(*_args):
                record.assert_called_once_with(
                    "quick_action_selected",
                    source="mode",
                )

            with patch.object(
                bot,
                "open_practice_mode_picker",
                new=AsyncMock(side_effect=assert_recorded_before_route),
            ):
                await bot.handle_quick_action.__wrapped__(update, context)

    async def test_ac1_legacy_selection_is_measured_without_button_text(self):
        update, context = quick_update("dictionary", "fr")
        route = AsyncMock()
        with (
            patch.object(bot, "record_product_event") as record,
            patch.object(bot.cmd_dictionary, "__wrapped__", new=route),
        ):
            await bot.handle_quick_action.__wrapped__(update, context)

        record.assert_called_once_with(
            "quick_action_selected",
            source="dictionary",
        )
        self.assertNotIn(update.message.text, str(record.call_args))
        route.assert_awaited_once_with(update, context)

    async def test_ac2_reply_keyboard_continue_and_review_propagate_source(self):
        with (
            patch.object(bot, "record_product_event"),
            patch.object(bot, "continue_or_start_lesson", new=AsyncMock()) as resume,
            patch.object(bot, "start_home_lesson", new=AsyncMock()) as review,
        ):
            update, context = quick_update("continue")
            await bot.handle_quick_action.__wrapped__(update, context)
            resume.assert_awaited_once_with(
                update.message,
                context,
                source="reply_keyboard",
            )

            update, context = quick_update("review")
            await bot.handle_quick_action.__wrapped__(update, context)
            review.assert_awaited_once_with(
                SimpleNamespace(message=update.message),
                context,
                lesson_kind="review",
                source="reply_keyboard",
            )

    async def test_ac2_new_lesson_records_reply_keyboard_on_all_start_events(self):
        message = SimpleNamespace(chat_id=123, reply_text=AsyncMock())
        context = SimpleNamespace(
            user_data={"interface_locale": "en"},
            bot=SimpleNamespace(send_message=AsyncMock()),
        )
        pack = bot.CATALOG.require("ja-basics-100")
        with (
            patch.object(bot, "active_content_pack", return_value=pack),
            patch.object(bot, "daily_lesson_size", return_value=5),
            patch.object(bot, "pick_block", return_value=[0, 1, 2, 3, 4]),
            patch.object(bot, "record_product_event") as record,
            patch.object(bot, "block_send_question_msg", new=AsyncMock()),
        ):
            await bot.start_home_lesson(
                SimpleNamespace(message=message),
                context,
                lesson_kind="daily",
                source="reply_keyboard",
            )

        starts = [
            call for call in record.call_args_list
            if call.args[0] in {"lesson_started", "block_started", "block_mode_started"}
        ]
        self.assertEqual(len(starts), 3)
        self.assertTrue(
            all(call.kwargs["source"] == "reply_keyboard" for call in starts)
        )

    async def test_ac3_default_home_source_remains_compatible(self):
        message = SimpleNamespace(chat_id=123, reply_text=AsyncMock())
        context = SimpleNamespace(
            user_data={"interface_locale": "en"},
            bot=SimpleNamespace(send_message=AsyncMock()),
        )
        pack = bot.CATALOG.require("ja-basics-100")
        with (
            patch.object(bot, "active_content_pack", return_value=pack),
            patch.object(bot, "daily_lesson_size", return_value=5),
            patch.object(bot, "pick_block", return_value=[0, 1, 2, 3, 4]),
            patch.object(bot, "record_product_event") as record,
            patch.object(bot, "block_send_question_msg", new=AsyncMock()),
        ):
            await bot.start_home_lesson(
                SimpleNamespace(message=message),
                context,
                lesson_kind="daily",
            )

        self.assertTrue(
            all(call.kwargs["source"] == "home" for call in record.call_args_list)
        )

    async def test_ac4_resume_selection_is_visible_without_duplicate_start(self):
        update, context = quick_update("continue")
        route = AsyncMock()
        with (
            patch.object(bot, "record_product_event") as record,
            patch.object(bot, "continue_or_start_lesson", new=route),
        ):
            await bot.handle_quick_action.__wrapped__(update, context)

        record.assert_called_once_with("quick_action_selected", source="continue")
        self.assertNotIn("lesson_started", [call.args[0] for call in record.call_args_list])
        route.assert_awaited_once()

    async def test_ec1_inexact_text_records_nothing(self):
        update, context = quick_update("continue")
        update.message.text = f" {update.message.text}"
        with patch.object(bot, "record_product_event") as record:
            await bot.handle_quick_action.__wrapped__(update, context)
        record.assert_not_called()

    def test_ec2_analytics_failure_remains_non_blocking(self):
        store = SimpleNamespace(record_event=Mock(side_effect=RuntimeError("offline")))
        token = bot._ACTIVE_RUNTIME.set(SimpleNamespace(store=store, user_id=1))
        try:
            bot.record_product_event("quick_action_selected", source="continue")
        finally:
            bot._ACTIVE_RUNTIME.reset(token)

        store.record_event.assert_called_once_with(
            1,
            "quick_action_selected",
            properties=None,
            session_id=None,
            source="continue",
        )


if __name__ == "__main__":
    unittest.main()
