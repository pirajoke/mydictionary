"""Owner contract: Telegram chat is primary; swipe is an explicit extra."""
from contextlib import ExitStack
from dataclasses import replace
import inspect
import os
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

os.environ.setdefault("BOT_TOKEN", "123456:TESTTOKEN_ABCDEFGHIJKLMNOP")
os.environ.setdefault("ALLOWED_USER_ID", "1")
os.environ.setdefault("ALLOW_SQLITE_DEV", "true")

import bot
from mydictionary.bot_profile import BOT_PROFILE_DEFAULTS


def buttons(markup):
    return [button for row in getattr(markup, "inline_keyboard", ()) for button in row]


class NativeChatEntryTest(unittest.IsolatedAsyncioTestCase):
    def fixture(self, action, locale="en"):
        message = SimpleNamespace(text=bot.quick_action_label(action, locale),
                                  chat_id=123, reply_text=AsyncMock())
        update = SimpleNamespace(message=message, effective_message=message,
                                 effective_chat=SimpleNamespace(type="private"),
                                 effective_user=SimpleNamespace(id=1, language_code=locale))
        return update, SimpleNamespace(user_data={"interface_locale": locale})

    def test_persistent_primary_actions_include_native_mode_not_swipe(self):
        expected = {"continue", "mode", "review", "words", "lang", "add", "start"}
        for locale in bot.INTERFACE_LOCALES:
            markup = bot.get_quick_actions_keyboard(locale)
            labels = [button.text for row in markup.keyboard for button in row]
            actions = [bot.quick_action_for_text(label) for label in labels]
            self.assertEqual(set(actions), expected)
            self.assertEqual(len(actions), 7)
            self.assertTrue(markup.is_persistent)
            self.assertFalse(markup.one_time_keyboard)

    async def test_primary_continue_review_language_use_chat_even_with_miniapp_on(self):
        for locale in ("en", "ru", "de", "ja"):
            for action in ("continue", "review", "lang"):
                with self.subTest(locale=locale, action=action), ExitStack() as stack:
                    routes = {
                        "continue": stack.enter_context(patch.object(bot, "continue_or_start_lesson", new_callable=AsyncMock)),
                        "review": stack.enter_context(patch.object(bot, "start_home_lesson", new_callable=AsyncMock)),
                        "lang": stack.enter_context(patch.object(bot.cmd_lang, "__wrapped__", new_callable=AsyncMock)),
                    }
                    stack.enter_context(patch.object(bot, "record_product_event"))
                    stack.enter_context(patch.object(bot, "MINIAPP_SETTINGS", replace(bot.MINIAPP_SETTINGS, enabled=True, public_url="https://dictionary.example/miniapp")))
                    update, context = self.fixture(action, locale)
                    await bot.handle_quick_action.__wrapped__(update, context)
                    routes[action].assert_awaited_once()
                    for call in update.message.reply_text.await_args_list:
                        self.assertFalse(any(button.web_app for button in buttons(call.kwargs.get("reply_markup"))))
                    if action == "review":
                        self.assertEqual(routes[action].await_args.kwargs["lesson_kind"], "review")

    async def test_words_opens_native_chooser_not_webapp(self):
        update, context = self.fixture("words")
        with (
            patch.object(bot.cmd_learn, "__wrapped__", new_callable=AsyncMock) as learn,
            patch.object(bot, "record_product_event"),
            patch.object(bot, "MINIAPP_SETTINGS", replace(bot.MINIAPP_SETTINGS, enabled=True, public_url="https://dictionary.example/miniapp")),
        ):
            await bot.handle_quick_action.__wrapped__(update, context)
        delivered = [button for call in update.message.reply_text.await_args_list
                     for button in buttons(call.kwargs.get("reply_markup"))]
        self.assertFalse(any(button.web_app for button in delivered), "Words stays in native chat")
        self.assertTrue(learn.await_count or any(button.callback_data for button in delivered),
                        "Words must open a usable native menu")

    async def test_add_visible_action_dispatches_existing_deterministic_add_flow(self):
        self.assertIn("add", bot.QUICK_ACTION_KEYS, "Add words is a visible primary action")
        update, context = self.fixture("add")
        with (
            patch.object(bot.cmd_add_words, "__wrapped__", new_callable=AsyncMock) as add,
            patch.object(bot, "record_product_event"),
            patch.object(bot, "MINIAPP_SETTINGS", replace(bot.MINIAPP_SETTINGS, enabled=True, public_url="https://dictionary.example/miniapp")),
        ):
            await bot.handle_quick_action.__wrapped__(update, context)
        add.assert_awaited_once_with(update, context)

    async def test_legacy_mode_remains_native_and_does_not_launch_swipe(self):
        update, context = self.fixture("mode")
        with (
            patch.object(bot, "open_practice_mode_picker", new_callable=AsyncMock) as modes,
            patch.object(bot, "record_product_event"),
            patch.object(bot, "MINIAPP_SETTINGS", replace(bot.MINIAPP_SETTINGS, enabled=True, public_url="https://dictionary.example/miniapp")),
        ):
            await bot.handle_quick_action.__wrapped__(update, context)
        modes.assert_awaited_once_with(update.message, context)

    async def test_swipe_is_separate_explicit_action_that_opens_webapp(self):
        self.assertIn("swipe", bot.QUICK_ACTION_KEYS | bot.LEGACY_QUICK_ACTION_KEYS,
                      "Swipe is separately routable, never a primary learning action")
        update, context = self.fixture("swipe")
        with (
            patch.object(bot, "record_product_event"),
            patch.object(bot, "MINIAPP_SETTINGS", replace(bot.MINIAPP_SETTINGS, enabled=True, public_url="https://dictionary.example/miniapp")),
        ):
            await bot.handle_quick_action.__wrapped__(update, context)
        delivered = [button for call in update.message.reply_text.await_args_list
                     for button in buttons(call.kwargs.get("reply_markup"))]
        self.assertEqual(sum(bool(button.web_app) for button in delivered), 1)

    async def test_start_shows_direct_native_continue_and_keeps_reply_keyboard(self):
        message = SimpleNamespace(chat_id=123, reply_text=AsyncMock(), reply_photo=AsyncMock())
        context = SimpleNamespace(user_data={"interface_locale": "en"})
        with (
            patch.object(bot, "WELCOME_BANNER_PATH") as banner,
            patch.object(bot, "get_bot_profile", return_value=dict(BOT_PROFILE_DEFAULTS)),
            patch.object(bot, "due_word_indices", return_value=[0, 1, 2]),
            patch.object(bot, "active_content_pack", return_value=bot.CATALOG.require("ja-basics-100")),
        ):
            banner.exists.return_value = False
            await bot.send_start_message(message, context, first_name="Synthetic Learner", locale="en")
        calls = message.reply_text.await_args_list + message.reply_photo.await_args_list
        inline = [button for call in calls for button in buttons(call.kwargs.get("reply_markup"))]
        self.assertTrue(any(button.callback_data in {"start:daily", "start:continue"} for button in inline),
                        "Start exposes a visible native Continue/Start button")
        self.assertFalse(any(button.web_app for button in inline))
        self.assertTrue(any(getattr(call.kwargs.get("reply_markup"), "is_persistent", False) for call in calls))
        text = "\n".join(str(call.kwargs.get("caption", call.args[0] if call.args else "")) for call in calls)
        self.assertIn("Synthetic Learner", text)
        self.assertRegex(text, r"(?i)japanese|日本|🇯🇵")
        self.assertIn("3", text, "Start includes the due-review count")


class NativeChatCompletionTest(unittest.IsolatedAsyncioTestCase):
    def completed(self, wrong):
        state = {"interface_locale": "en"}
        bot.reset_block_state(state, [0, 1, 2], "ja", None, "ja-basics-100", lesson_kind="daily")
        bot.start_block_attempt(state, "flash")
        state.update(block_pos=3, block_correct=3 - len(wrong), block_wrong=list(wrong))
        return state

    def test_completion_has_max_three_actions_retry_first_and_more_collapsed(self):
        state = self.completed([0])
        with (
            patch.object(bot, "AI_SETTINGS", replace(bot.AI_SETTINGS, enabled=True)),
            patch.object(bot, "VOICE_SETTINGS", replace(bot.VOICE_SETTINGS, enabled=True)),
        ):
            inline = buttons(bot.build_block_summary_keyboard(state))
        self.assertLessEqual(len(inline), 3, "Completion keeps optional controls behind More")
        self.assertEqual(inline[0].callback_data, f"bretry:{state['block_session']}")
        self.assertTrue(any(button.callback_data == f"bmore:{state['block_session']}" for button in inline))
        self.assertFalse(any(button.callback_data.startswith(("bai:", "bvoice:", "bconversation:", "btopics:")) for button in inline))
        self.assertIn('^bmore', inspect.getsource(bot.manual_polling), "Collapsed More has a registered callback")

    async def test_more_expands_optional_controls_in_native_chat(self):
        handler = getattr(bot, "block_more_cb", None)
        self.assertTrue(callable(handler), "More has a usable native callback handler")
        state = self.completed([0])
        query = SimpleNamespace(data=f"bmore:{state['block_session']}", answer=AsyncMock(),
                                edit_message_text=AsyncMock(), edit_message_reply_markup=AsyncMock(),
                                message=SimpleNamespace(chat_id=123))
        update = SimpleNamespace(callback_query=query, effective_user=SimpleNamespace(id=1, language_code="en"))
        context = SimpleNamespace(user_data=state)
        with (
            patch.object(bot, "activate_block_language"),
            patch.object(bot, "validate_block_callback", new=AsyncMock(return_value=True)),
            patch.object(bot, "AI_SETTINGS", replace(bot.AI_SETTINGS, enabled=True)),
            patch.object(bot, "VOICE_SETTINGS", replace(bot.VOICE_SETTINGS, enabled=True)),
        ):
            await getattr(handler, "__wrapped__", handler)(update, context)
        calls = query.edit_message_text.await_args_list + query.edit_message_reply_markup.await_args_list
        expanded = [button for call in calls for button in buttons(call.kwargs.get("reply_markup"))]
        callbacks = {button.callback_data for button in expanded}
        for prefix in ("bai", "bvoice", "bconversation", "btopics"):
            self.assertIn(f"{prefix}:{state['block_session']}", callbacks)
        self.assertFalse(any(button.web_app for button in expanded))

    def test_rendering_same_completion_twice_awards_session_bonus_once(self):
        state = self.completed([])
        progress = {"xp": 0, "today_xp": 0, "sessions": 0, "streak": 0,
                    "active_lang": "ja", "active_pack_id": "ja-basics-100"}
        with patch.object(bot, "PROGRESS", progress), patch.object(bot, "save_progress"):
            first = bot.format_block_summary(state)
            second = bot.format_block_summary(state)
        self.assertEqual(progress["sessions"], 1, "Duplicate callbacks/redelivery must not award another session")
        self.assertEqual(progress["xp"], bot.XP_SESSION)
        self.assertEqual(first, second)


if __name__ == "__main__":
    unittest.main()
