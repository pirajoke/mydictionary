import inspect
import os
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch


os.environ.setdefault("BOT_TOKEN", "123456:TESTTOKEN_ABCDEFGHIJKLMNOP")
os.environ.setdefault("ALLOWED_USER_ID", "1")
os.environ.setdefault("ALLOW_SQLITE_DEV", "true")

import bot
from mydictionary.localization import INTERFACE_LOCALES, translate


def reply_labels(markup):
    return [[button.text for button in row] for row in markup.keyboard]


def inline_callbacks(markup):
    return [button.callback_data for row in markup.inline_keyboard for button in row]


class ContextualQuickActionsV1Test(unittest.IsolatedAsyncioTestCase):
    def test_ac1_learning_first_keyboard_has_five_actions_in_three_rows(self):
        for locale in sorted(INTERFACE_LOCALES):
            with self.subTest(locale=locale):
                markup = bot.get_quick_actions_keyboard(locale)
                self.assertEqual(
                    reply_labels(markup),
                    [
                        [bot.quick_action_label("continue", locale)],
                        [
                            bot.quick_action_label("review", locale),
                            bot.quick_action_label("mode", locale),
                        ],
                        [
                            bot.quick_action_label("words", locale),
                            bot.quick_action_label("lang", locale),
                        ],
                    ],
                )
                flattened = [label for row in reply_labels(markup) for label in row]
                self.assertEqual(len(flattened), 5)
                self.assertTrue(all(len(label) <= 64 for label in flattened))
                self.assertNotIn(f"✨ {translate('command_ai', locale)}", flattened)
                self.assertNotIn(f"📊 {translate('command_stats', locale)}", flattened)
                self.assertNotIn(f"📖 {translate('command_dictionary', locale)}", flattened)

    def test_ac2_exact_router_supports_only_the_five_visible_actions(self):
        for locale in sorted(INTERFACE_LOCALES):
            for action in ("continue", "review", "mode", "words", "lang"):
                label = bot.quick_action_label(action, locale)
                with self.subTest(locale=locale, action=action):
                    self.assertEqual(bot.quick_action_for_text(label), action)
                    self.assertIsNone(bot.quick_action_for_text(f" {label}"))
                    self.assertIsNone(bot.quick_action_for_text(f"{label}!"))
        self.assertEqual(set(bot.QUICK_ACTION_KEYS), {
            "continue", "review", "mode", "words", "lang"
        })
        source = inspect.getsource(bot.manual_polling)
        self.assertLess(source.index("handle_quick_action"), source.index("mirror_text_handler"))

    async def test_ac3_mode_chooser_preserves_an_incomplete_word_set_and_session(self):
        user_data = {"interface_locale": "ru"}
        bot.reset_block_state(
            user_data, [0, 1, 2, 3], "ja", "greetings", "ja-basics-100"
        )
        bot.start_block_attempt(user_data, "quiz")
        user_data["block_pos"] = 2
        original = {
            "indices": list(user_data["block_all_indices"]),
            "session": user_data["block_session"],
            "position": user_data["block_pos"],
        }
        message = SimpleNamespace(reply_text=AsyncMock(), chat_id=123)
        context = SimpleNamespace(user_data=user_data)

        await bot.open_practice_mode_picker(message, context)

        self.assertEqual(user_data["block_all_indices"], original["indices"])
        self.assertEqual(user_data["block_session"], original["session"])
        self.assertEqual(user_data["block_pos"], original["position"])
        callbacks = inline_callbacks(message.reply_text.await_args.kwargs["reply_markup"])
        self.assertEqual(callbacks, [
            f"bmode:{original['session']}:flash",
            f"bmode:{original['session']}:quiz",
            f"bmode:{original['session']}:type",
        ])

    async def test_ac3_new_mode_chooser_prepares_sr_block_without_starting_it(self):
        message = SimpleNamespace(reply_text=AsyncMock(), chat_id=123)
        context = SimpleNamespace(user_data={"interface_locale": "en"})
        pack = bot.CATALOG.require("ja-basics-100")

        with (
            patch.object(bot, "active_content_pack", return_value=pack),
            patch.object(bot, "daily_lesson_size", return_value=5),
            patch.object(bot, "pick_block", return_value=[4, 3, 2, 1, 0]) as pick,
            patch.object(bot, "record_product_event") as event,
        ):
            await bot.open_practice_mode_picker(message, context)

        pick.assert_called_once_with(size=5)
        event.assert_not_called()
        self.assertEqual(context.user_data["block_all_indices"], [4, 3, 2, 1, 0])
        self.assertIsNone(context.user_data["block_mode"])
        self.assertEqual(context.user_data["block_pos"], 0)
        session = context.user_data["block_session"]
        self.assertEqual(inline_callbacks(message.reply_text.await_args.kwargs["reply_markup"]), [
            f"bmode:{session}:flash",
            f"bmode:{session}:quiz",
            f"bmode:{session}:type",
        ])

    async def test_ac3_mode_selection_records_traction_only_when_practice_starts(self):
        user_data = {"interface_locale": "en"}
        bot.reset_block_state(
            user_data, [0, 1, 2], "ja", None, "ja-basics-100",
            lesson_kind="practice",
        )
        user_data["quick_mode_pending_start"] = True
        session = user_data["block_session"]
        query = SimpleNamespace(
            data=f"bmode:{session}:flash",
            answer=AsyncMock(),
            edit_message_text=AsyncMock(),
            message=SimpleNamespace(chat_id=123),
        )
        update = SimpleNamespace(
            callback_query=query,
            effective_user=SimpleNamespace(id=1, language_code="en"),
        )
        context = SimpleNamespace(user_data=user_data)
        pack = bot.CATALOG.require("ja-basics-100")

        with (
            patch.object(bot, "validate_block_callback", new=AsyncMock(return_value=True)),
            patch.object(bot, "activate_block_language"),
            patch.object(bot, "active_content_pack", return_value=pack),
            patch.object(bot, "record_product_event") as event,
            patch.object(bot, "block_send_question", new=AsyncMock()) as question,
        ):
            await bot.block_mode_cb.__wrapped__(update, context)

        self.assertEqual(
            [call.args[0] for call in event.call_args_list],
            ["lesson_started", "block_started", "block_mode_started"],
        )
        self.assertTrue(all(call.kwargs["session_id"] == user_data["block_session"] for call in event.call_args_list))
        self.assertEqual(event.call_args_list[0].kwargs["source"], "reply_keyboard")
        self.assertNotIn("quick_mode_pending_start", user_data)
        question.assert_awaited_once_with(query, context)

    async def test_ac4_words_action_delegates_to_the_existing_topic_picker(self):
        message = SimpleNamespace(
            text=bot.quick_action_label("words", "ru"),
            reply_text=AsyncMock(),
            chat_id=123,
        )
        update = SimpleNamespace(
            message=message,
            effective_message=message,
            effective_user=SimpleNamespace(id=1, language_code="ru"),
        )
        context = SimpleNamespace(user_data={"interface_locale": "ru"})
        with patch.object(bot.cmd_learn, "__wrapped__", new=AsyncMock()) as learn:
            await bot.handle_quick_action.__wrapped__(update, context)
        learn.assert_awaited_once_with(update, context)

    async def test_ec1_empty_pack_returns_localized_message_without_callbacks(self):
        message = SimpleNamespace(reply_text=AsyncMock(), chat_id=123)
        context = SimpleNamespace(user_data={"interface_locale": "fr"})
        pack = bot.CATALOG.require("ja-basics-100")
        with (
            patch.object(bot, "active_content_pack", return_value=pack),
            patch.object(bot, "daily_lesson_size", return_value=5),
            patch.object(bot, "pick_block", return_value=[]),
        ):
            await bot.open_practice_mode_picker(message, context)
        message.reply_text.assert_awaited_once_with(translate("learning_no_words", "fr"))
        self.assertIsNone(context.user_data.get("block_session"))

    async def test_ec2_completed_block_is_replaced_before_mode_choice(self):
        user_data = {"interface_locale": "en"}
        bot.reset_block_state(user_data, [0, 1], "ja", None, "ja-basics-100")
        bot.start_block_attempt(user_data, "flash")
        old_session = user_data["block_session"]
        user_data["block_pos"] = 2
        message = SimpleNamespace(reply_text=AsyncMock(), chat_id=123)
        context = SimpleNamespace(user_data=user_data)
        pack = bot.CATALOG.require("ja-basics-100")
        with (
            patch.object(bot, "active_content_pack", return_value=pack),
            patch.object(bot, "daily_lesson_size", return_value=5),
            patch.object(bot, "pick_block", return_value=[3, 4, 5]),
        ):
            await bot.open_practice_mode_picker(message, context)
        self.assertNotEqual(user_data["block_session"], old_session)
        self.assertEqual(user_data["block_all_indices"], [3, 4, 5])


if __name__ == "__main__":
    unittest.main()
