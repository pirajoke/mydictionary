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


def _buttons(markup):
    return [button for row in markup.keyboard for button in row]


def _inline_buttons(markup):
    return [button for row in markup.inline_keyboard for button in row]


class TelegramQuickMenuContractTest(unittest.IsolatedAsyncioTestCase):
    def test_ac1_quick_keyboard_has_four_localized_actions_and_no_languages(self):
        factory = getattr(bot, "get_quick_actions_keyboard", None)
        self.assertTrue(callable(factory), "quick-action keyboard is missing")
        pack_labels = {pack.label for pack in bot.CATALOG.packs}

        for locale in sorted(INTERFACE_LOCALES):
            with self.subTest(locale=locale):
                labels = [button.text for button in _buttons(factory(locale))]
                self.assertEqual(
                    labels,
                    [
                        translate("start_daily", locale),
                        translate("start_review", locale),
                        f"✨ {translate('command_ai', locale)}",
                        f"📊 {translate('command_stats', locale)}",
                    ],
                )
                self.assertTrue(pack_labels.isdisjoint(labels))
                self.assertTrue(all(len(label) <= 64 for label in labels))

    def test_ac2_visible_command_menu_prioritizes_learning_and_hides_language(self):
        base = bot.build_bot_commands(ai_enabled=False, miniapp_enabled=True)
        with_ai = bot.build_bot_commands(ai_enabled=True, miniapp_enabled=True)

        self.assertEqual(
            [command.command for command in base],
            [
                "continue",
                "review",
                "learn",
                "dictionary",
                "stats",
                "app",
                "invite",
                "privacy",
                "help",
            ],
        )
        self.assertEqual(
            [command.command for command in with_ai],
            [
                "continue",
                "review",
                "learn",
                "dictionary",
                "stats",
                "ai",
                "app",
                "invite",
                "privacy",
                "help",
            ],
        )
        self.assertNotIn("lang", {command.command for command in with_ai})

    async def test_ac3_language_switch_replaces_legacy_language_keyboard(self):
        pack = bot.CATALOG.require("ja-basics-100")
        query = SimpleNamespace(
            data=f"lang:{pack.pack_id}",
            answer=AsyncMock(),
            edit_message_text=AsyncMock(),
            message=SimpleNamespace(chat_id=123),
        )
        update = SimpleNamespace(
            callback_query=query,
            effective_user=SimpleNamespace(id=1, language_code="fr"),
        )
        context = SimpleNamespace(
            user_data={"interface_locale": "fr"},
            bot=SimpleNamespace(send_message=AsyncMock()),
        )

        with (
            patch.object(bot, "switchable_packs", return_value=[pack]),
            patch.object(bot, "activate_content_pack"),
            patch.object(bot, "record_product_event"),
        ):
            await bot.lang_switch_cb.__wrapped__(update, context)

        markup = context.bot.send_message.await_args.kwargs["reply_markup"]
        labels = [button.text for button in _buttons(markup)]
        self.assertEqual(
            labels,
            [
                translate("start_daily", "fr"),
                translate("start_review", "fr"),
                f"✨ {translate('command_ai', 'fr')}",
                f"📊 {translate('command_stats', 'fr')}",
            ],
        )
        self.assertNotIn(pack.label, labels)

    async def test_ac3_start_installs_quick_actions_without_language_tiles(self):
        message = SimpleNamespace(reply_text=AsyncMock())
        context = SimpleNamespace()

        with (
            patch.object(bot, "WELCOME_BANNER_PATH") as banner,
            patch.object(bot, "get_bot_profile", return_value={}),
            patch.object(bot, "render_start_text", return_value="welcome"),
        ):
            banner.exists.return_value = False
            await bot.send_start_message(
                message,
                context,
                first_name="Learner",
                locale="ru",
            )

        markup = message.reply_text.await_args.kwargs["reply_markup"]
        self.assertEqual(
            [button.text for button in _buttons(markup)],
            [
                translate("start_daily", "ru"),
                translate("start_review", "ru"),
                f"✨ {translate('command_ai', 'ru')}",
                f"📊 {translate('command_stats', 'ru')}",
            ],
        )

    def test_ac4_quick_label_router_is_exact_and_registered_before_mirror(self):
        resolver = getattr(bot, "quick_action_for_text", None)
        self.assertTrue(callable(resolver), "quick-action resolver is missing")
        for locale in sorted(INTERFACE_LOCALES):
            cases = {
                translate("start_daily", locale): "continue",
                translate("start_review", locale): "review",
                f"✨ {translate('command_ai', locale)}": "ai",
                f"📊 {translate('command_stats', locale)}": "audit",
            }
            for label, expected in cases.items():
                with self.subTest(locale=locale, action=expected):
                    self.assertEqual(resolver(label), expected)
                    self.assertIsNone(resolver(f" {label}"))
                    self.assertIsNone(resolver(f"{label}!"))
        self.assertIsNone(resolver("🇫🇷 Français · 100"))

        source = inspect.getsource(bot.manual_polling)
        self.assertIn("handle_quick_action", source)
        self.assertLess(
            source.index("handle_quick_action"),
            source.index("mirror_text_handler"),
        )

    async def test_ac4_continue_resumes_the_exact_incomplete_block(self):
        handler = getattr(bot, "handle_quick_action", None)
        self.assertTrue(callable(handler), "quick-action handler is missing")
        user_data = {"interface_locale": "ru"}
        indices = [0, 1, 2, 3]
        bot.reset_block_state(
            user_data,
            indices,
            "ja",
            "greetings",
            "ja-basics-100",
        )
        bot.start_block_attempt(user_data, "quiz")
        user_data["block_pos"] = 2
        session_id = user_data["block_session"]
        message = SimpleNamespace(
            text=translate("start_daily", "ru"),
            chat_id=123,
            reply_text=AsyncMock(),
        )
        update = SimpleNamespace(
            message=message,
            effective_message=message,
            effective_user=SimpleNamespace(id=1, language_code="ru"),
        )
        context = SimpleNamespace(user_data=user_data, bot=SimpleNamespace())

        with (
            patch.object(bot, "active_tutor_context", return_value=object()),
            patch.object(bot, "block_send_question_msg", new=AsyncMock()) as resume,
            patch.object(bot, "start_home_lesson", new=AsyncMock()) as start,
        ):
            await getattr(handler, "__wrapped__", handler)(update, context)

        resume.assert_awaited_once_with(message, context)
        start.assert_not_awaited()
        self.assertEqual(user_data["block_all_indices"], indices)
        self.assertEqual(user_data["block_pos"], 2)
        self.assertEqual(user_data["block_session"], session_id)

    async def test_ac4_review_ai_and_audit_use_existing_safe_entrypoints(self):
        handler = bot.handle_quick_action.__wrapped__

        async def invoke(text):
            message = SimpleNamespace(text=text, chat_id=123, reply_text=AsyncMock())
            update = SimpleNamespace(
                message=message,
                effective_message=message,
                effective_user=SimpleNamespace(id=7, language_code="en"),
            )
            context = SimpleNamespace(user_data={"interface_locale": "en"})
            await handler(update, context)
            return update, context, message

        with patch.object(bot, "start_home_lesson", new=AsyncMock()) as start:
            _update, context, message = await invoke(translate("start_review", "en"))
        start.assert_awaited_once()
        self.assertIs(start.await_args.args[0].message, message)
        self.assertIs(start.await_args.args[1], context)
        self.assertEqual(start.await_args.kwargs, {"lesson_kind": "review"})

        with patch.object(bot, "format_stats_text", return_value="safe audit"):
            _update, _context, message = await invoke(
                f"📊 {translate('command_stats', 'en')}"
            )
        message.reply_text.assert_awaited_once_with(
            "safe audit",
            parse_mode="Markdown",
        )

        with (
            patch.object(bot, "AI_SETTINGS", SimpleNamespace(enabled=True)),
            patch.object(bot, "send_ai_tutor_menu", new=AsyncMock()) as tutor,
        ):
            update, context, message = await invoke(
                f"✨ {translate('command_ai', 'en')}"
            )
        tutor.assert_awaited_once_with(
            message,
            context,
            user_id=7,
            locale="en",
        )

        with (
            patch.object(bot, "AI_SETTINGS", SimpleNamespace(enabled=False)),
            patch.object(bot, "send_ai_tutor_menu", new=AsyncMock()) as tutor,
        ):
            _update, _context, message = await invoke(
                f"✨ {translate('command_ai', 'en')}"
            )
        tutor.assert_not_awaited()
        message.reply_text.assert_awaited_once_with(translate("ai_disabled", "en"))

    async def test_ec2_completed_block_starts_a_fresh_daily_lesson(self):
        user_data = {"interface_locale": "ru"}
        bot.reset_block_state(
            user_data,
            [0, 1, 2, 3],
            "ja",
            "greetings",
            "ja-basics-100",
        )
        bot.start_block_attempt(user_data, "quiz")
        user_data["block_pos"] = len(user_data["block_indices"])
        message = SimpleNamespace(
            text=translate("start_daily", "ru"),
            chat_id=123,
            reply_text=AsyncMock(),
        )
        update = SimpleNamespace(
            message=message,
            effective_message=message,
            effective_user=SimpleNamespace(id=1, language_code="ru"),
        )
        context = SimpleNamespace(user_data=user_data)

        with (
            patch.object(bot, "active_tutor_context", return_value=object()),
            patch.object(bot, "start_home_lesson", new=AsyncMock()) as start,
            patch.object(bot, "block_send_question_msg", new=AsyncMock()) as resume,
        ):
            await bot.handle_quick_action.__wrapped__(update, context)

        resume.assert_not_awaited()
        start.assert_awaited_once()
        self.assertEqual(start.await_args.kwargs, {"lesson_kind": "daily"})


class PersistentBlockCardsContractTest(unittest.IsolatedAsyncioTestCase):
    def _active_block(self, mode="quiz"):
        user_data = {"interface_locale": "ru"}
        indices = [0, 1, 2, 3]
        bot.reset_block_state(
            user_data,
            indices,
            "ja",
            "greetings",
            "ja-basics-100",
        )
        bot.start_block_attempt(user_data, mode)
        return user_data, indices

    def test_ac6_quiz_and_summary_offer_return_to_exact_cards(self):
        user_data, _indices = self._active_block("quiz")
        session_id = user_data["block_session"]
        quiz_callbacks = {
            button.callback_data
            for button in _inline_buttons(
                bot.build_block_quiz_keyboard(user_data, user_data["block_indices"][0])
            )
        }
        summary_callbacks = {
            button.callback_data
            for button in _inline_buttons(bot.build_block_summary_keyboard(user_data))
        }
        self.assertIn(f"bstudy:{session_id}", quiz_callbacks)
        self.assertIn(f"bstudy:{session_id}", summary_callbacks)

    async def test_ac6_written_question_offers_return_to_cards(self):
        user_data, _indices = self._active_block("type")
        query = SimpleNamespace(
            edit_message_text=AsyncMock(),
            message=SimpleNamespace(chat_id=123),
        )
        context = SimpleNamespace(user_data=user_data)
        with (
            patch.object(bot, "activate_block_language"),
            patch.object(bot, "format_word_label", return_value="word"),
            patch.object(bot, "track_card_shown"),
            patch.object(bot, "send_pronunciation", new=AsyncMock()),
        ):
            await bot.block_send_question(query, context)

        markup = query.edit_message_text.await_args.kwargs["reply_markup"]
        self.assertEqual(
            markup.inline_keyboard[0][0].callback_data,
            f"bstudy:{user_data['block_session']}",
        )
        self.assertIn("block_study_cb", inspect.getsource(bot.manual_polling))

    async def test_ac6_return_restores_original_study_list_without_mutation(self):
        handler = getattr(bot, "block_study_cb", None)
        self.assertTrue(callable(handler), "return-to-cards handler is missing")
        user_data, indices = self._active_block("quiz")
        user_data["block_pos"] = 2
        user_data["block_correct"] = 1
        old_session = user_data["block_session"]
        query = SimpleNamespace(
            data=f"bstudy:{old_session}",
            answer=AsyncMock(),
            edit_message_text=AsyncMock(),
            message=SimpleNamespace(chat_id=123),
        )
        update = SimpleNamespace(
            callback_query=query,
            effective_user=SimpleNamespace(id=1, language_code="ru"),
        )
        context = SimpleNamespace(user_data=user_data, bot=SimpleNamespace())

        with (
            patch.object(bot, "activate_block_language"),
            patch.object(bot, "format_block_intro", return_value="study list"),
            patch.object(bot, "build_study_buttons", return_value="buttons"),
            patch.object(bot, "mark_correct") as mark_correct,
            patch.object(bot, "mark_wrong") as mark_wrong,
            patch.object(bot, "save_progress") as save_progress,
        ):
            await getattr(handler, "__wrapped__", handler)(update, context)

        query.answer.assert_awaited_once_with()
        query.edit_message_text.assert_awaited_once_with(
            "study list",
            reply_markup="buttons",
            parse_mode="Markdown",
        )
        self.assertEqual(user_data["block_all_indices"], indices)
        self.assertEqual(user_data["block_indices"], indices)
        self.assertIsNone(user_data["block_mode"])
        self.assertNotEqual(user_data["block_session"], old_session)
        mark_correct.assert_not_called()
        mark_wrong.assert_not_called()
        save_progress.assert_not_called()

    async def test_err1_stale_return_to_cards_is_rejected_without_state_change(self):
        handler = getattr(bot, "block_study_cb", None)
        self.assertTrue(callable(handler), "return-to-cards handler is missing")
        user_data, indices = self._active_block("type")
        before = dict(user_data)
        query = SimpleNamespace(
            data="bstudy:stale",
            answer=AsyncMock(),
            edit_message_text=AsyncMock(),
            message=SimpleNamespace(chat_id=123),
        )
        update = SimpleNamespace(
            callback_query=query,
            effective_user=SimpleNamespace(id=1, language_code="ru"),
        )
        context = SimpleNamespace(user_data=user_data, bot=SimpleNamespace())

        await getattr(handler, "__wrapped__", handler)(update, context)

        query.answer.assert_awaited_once_with(bot.BLOCK_STALE_TEXT, show_alert=True)
        query.edit_message_text.assert_not_awaited()
        self.assertEqual(user_data, before)
        self.assertEqual(user_data["block_all_indices"], indices)


if __name__ == "__main__":
    unittest.main()
