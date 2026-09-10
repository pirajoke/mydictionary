import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from sqlalchemy import select


os.environ.setdefault("BOT_TOKEN", "123456:TESTTOKEN")
os.environ.setdefault("ALLOWED_USER_ID", "1")

import bot
from mydictionary.admin_store import AdminStore
from mydictionary.bot_profile import BOT_PROFILE_DEFAULTS, render_start_text
from mydictionary.storage import AnalyticsEvent, DatabaseStore


class BotProfileTest(unittest.TestCase):
    def test_default_start_is_short_and_explains_daily_card_flow(self):
        text = render_start_text(BOT_PROFILE_DEFAULTS, "Макс")
        self.assertTrue(text.startswith("Привет, Макс!"))
        self.assertIn("короткий урок", text)
        self.assertIn("по одной карточке", text)
        self.assertIn("произношение", text)
        self.assertIn("повторение", text)
        self.assertLessEqual(len(text), 1024)

    def test_start_keyboard_routes_primary_workflows(self):
        callbacks = [
            button.callback_data
            for row in bot.start_keyboard().inline_keyboard
            for button in row
        ]
        self.assertEqual(
            callbacks,
            [
                "start:daily",
                "start:review",
                "start:topics",
                "start:stats",
                "start:settings",
            ],
        )
        self.assertEqual(
            bot.start_keyboard().inline_keyboard[0][0].text,
            "▶️ Урок на сегодня",
        )


class WelcomeMessageTest(unittest.IsolatedAsyncioTestCase):
    async def test_start_sends_banner_with_editable_text(self):
        message = SimpleNamespace(
            reply_photo=AsyncMock(),
            reply_text=AsyncMock(),
        )
        profile = dict(
            BOT_PROFILE_DEFAULTS,
            bot_start_text="Привет, {name}! Настраиваемый старт.",
        )
        with patch.object(bot, "get_bot_profile", return_value=profile):
            await bot.send_start_message(
                message,
                SimpleNamespace(),
                first_name="Анна",
            )

        message.reply_photo.assert_awaited_once()
        payload = message.reply_photo.await_args.kwargs
        self.assertEqual(payload["caption"], "Привет, Анна! Настраиваемый старт.")
        self.assertEqual(
            [
                button.text
                for row in payload["reply_markup"].keyboard
                for button in row
            ],
            [
                bot.quick_action_label("continue", "ru"),
                bot.quick_action_label("review", "ru"),
                bot.quick_action_label("ai", "ru"),
                bot.quick_action_label("audit", "ru"),
                bot.quick_action_label("dictionary", "ru"),
                bot.quick_action_label("lang", "ru"),
            ],
        )
        message.reply_text.assert_not_awaited()

    async def test_start_falls_back_to_text_when_photo_fails(self):
        message = SimpleNamespace(
            reply_photo=AsyncMock(side_effect=RuntimeError("photo unavailable")),
            reply_text=AsyncMock(),
        )
        with patch.object(bot, "get_bot_profile", return_value=BOT_PROFILE_DEFAULTS):
            await bot.send_start_message(
                message,
                SimpleNamespace(),
                first_name="Иван",
            )

        message.reply_text.assert_awaited_once()
        self.assertIn("Привет, Иван!", message.reply_text.await_args.args[0])


class ProductOnboardingTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory(prefix="mydictionary-onboarding-")
        self.store = DatabaseStore(
            f"sqlite:///{Path(self.temp_dir.name) / 'onboarding.db'}"
        )

    def tearDown(self):
        self.store.close()
        self.temp_dir.cleanup()

    async def test_new_learner_start_opens_free_onboarding(self):
        message = SimpleNamespace(reply_text=AsyncMock())
        user = SimpleNamespace(id=9901, first_name="Лена")
        update = SimpleNamespace(
            message=message,
            effective_message=message,
            effective_user=user,
            callback_query=None,
        )
        context = SimpleNamespace(args=["telegram-ad"], user_data={})
        with (
            patch.object(bot, "_STORE", self.store),
            patch.object(bot, "BOT_ACCESS_MODE", "public"),
            patch.object(bot, "LEGACY_USER_ID", None),
            patch.object(bot, "ADMIN_USER_IDS", set()),
        ):
            await bot.cmd_start(update, context)

        text = message.reply_text.await_args.args[0]
        self.assertIn("минут", text.lower())
        self.assertLessEqual(len(text), 220)
        button = (
            message.reply_text.await_args.kwargs["reply_markup"]
            .inline_keyboard[0][0]
        )
        self.assertEqual(
            button.callback_data,
            "onboarding:begin",
        )
        self.assertIn("Выбрать язык", button.text)
        self.assertEqual(
            self.store.product_profile(9901)["acquisition_source"],
            "telegram-ad",
        )
        self.assertEqual(
            self.store.product_profile(9901)["access_status"], "active"
        )

    async def test_pilot_start_registers_one_pending_waitlist_entry(self):
        message = SimpleNamespace(reply_text=AsyncMock())
        user = SimpleNamespace(id=9910, first_name="Лена")
        update = SimpleNamespace(
            message=message,
            effective_message=message,
            effective_user=user,
            callback_query=None,
        )
        context = SimpleNamespace(args=["pilot-campaign"], user_data={})
        with (
            patch.object(bot, "_STORE", self.store),
            patch.object(bot, "BOT_ACCESS_MODE", "pilot"),
            patch.object(bot, "ALLOWED_USER_IDS", set()),
            patch.object(bot, "ADMIN_USER_IDS", set()),
            patch.object(bot, "LEGACY_USER_ID", None),
        ):
            await bot.cmd_start(update, context)
            await bot.cmd_start(update, context)

        self.assertIn("Заявка", message.reply_text.await_args.args[0])
        profile = self.store.product_profile(9910)
        self.assertEqual(profile["access_status"], "pending")
        self.assertIsNone(profile["onboarding_completed_at"])
        self.assertEqual(profile["acquisition_source"], "pilot-campaign")
        with self.store.Session() as session:
            events = session.execute(
                select(AnalyticsEvent.event_name).where(
                    AnalyticsEvent.telegram_user_id == 9910
                )
            ).scalars().all()
        self.assertEqual(events.count("start_received"), 2)
        self.assertEqual(events.count("pilot_waitlist_joined"), 1)
        self.assertEqual(len(events), 3)

    async def test_pilot_approval_opens_onboarding_and_block_is_global(self):
        user_id = 9911
        user = SimpleNamespace(id=user_id, first_name="Маша")
        message = SimpleNamespace(reply_text=AsyncMock())
        update = SimpleNamespace(
            message=message,
            effective_message=message,
            effective_user=user,
            callback_query=None,
        )
        context = SimpleNamespace(args=[], user_data={})
        self.store.ensure_user(user)
        AdminStore(self.store).set_user_access_status(
            user_id, status="active", actor="owner"
        )
        with (
            patch.object(bot, "_STORE", self.store),
            patch.object(bot, "BOT_ACCESS_MODE", "pilot"),
            patch.object(bot, "ALLOWED_USER_IDS", set()),
            patch.object(bot, "ADMIN_USER_IDS", set()),
            patch.object(bot, "LEGACY_USER_ID", None),
        ):
            await bot.cmd_start(update, context)
        self.assertIn("минут", message.reply_text.await_args.args[0].lower())

        AdminStore(self.store).set_user_access_status(
            user_id, status="blocked", actor="owner"
        )
        message.reply_text.reset_mock()
        with (
            patch.object(bot, "_STORE", self.store),
            patch.object(bot, "BOT_ACCESS_MODE", "public"),
            patch.object(bot, "ALLOWED_USER_IDS", set()),
            patch.object(bot, "ADMIN_USER_IDS", set()),
            patch.object(bot, "LEGACY_USER_ID", None),
        ):
            await bot.cmd_start(update, context)
        self.assertIn("заблокирован", message.reply_text.await_args.args[0])

    async def test_forged_private_pack_callback_is_rejected_for_learner(self):
        user_id = 9902
        self.store.ensure_user_id(user_id)
        self.store.activate_pack(
            user_id,
            pack_id="ja-basics-100",
            language="ja",
            source="onboarding",
        )
        self.store.update_product_profile(
            user_id,
            native_language="ru",
            learning_goal="basics",
            daily_word_goal=10,
            complete_onboarding=True,
            onboarding_version=bot.CURRENT_ONBOARDING_VERSION,
        )
        message = SimpleNamespace(chat_id=7, reply_text=AsyncMock())
        query = SimpleNamespace(
            data="lang:pirajoke-en-personal",
            answer=AsyncMock(),
            edit_message_text=AsyncMock(),
            message=message,
        )
        update = SimpleNamespace(
            callback_query=query,
            effective_message=message,
            effective_user=SimpleNamespace(id=user_id),
        )
        with (
            patch.object(bot, "_STORE", self.store),
            patch.object(bot, "BOT_ACCESS_MODE", "public"),
            patch.object(bot, "LEGACY_USER_ID", None),
            patch.object(bot, "ADMIN_USER_IDS", set()),
        ):
            await bot.lang_switch_cb(update, SimpleNamespace(user_data={}))

        self.assertIn(
            "недоступен", query.edit_message_text.await_args.args[0]
        )
        self.assertEqual(
            self.store.product_profile(user_id)["active_pack_id"],
            "ja-basics-100",
        )

    async def test_complete_onboarding_persists_profile_and_funnel_events(self):
        user_id = 9903
        message = SimpleNamespace(
            chat_id=8,
            reply_text=AsyncMock(),
            reply_photo=AsyncMock(),
        )
        query = SimpleNamespace(
            data="onboarding:begin",
            answer=AsyncMock(),
            edit_message_text=AsyncMock(),
            message=message,
        )
        update = SimpleNamespace(
            callback_query=query,
            effective_message=message,
            effective_user=SimpleNamespace(id=user_id, first_name="Маша"),
        )
        context = SimpleNamespace(user_data={})
        steps = (
            "onboarding:begin",
            "onboarding:native:ru",
            "onboarding:pack:ja-basics-100",
            "onboarding:goal:travel",
            "onboarding:preference:conversation",
            "onboarding:pace:10",
        )
        with (
            patch.object(bot, "_STORE", self.store),
            patch.object(bot, "BOT_ACCESS_MODE", "public"),
            patch.object(bot, "LEGACY_USER_ID", None),
            patch.object(bot, "ADMIN_USER_IDS", set()),
        ):
            for data in steps:
                query.data = data
                await bot.onboarding_cb(update, context)

        profile = self.store.product_profile(user_id)
        self.assertEqual(profile["native_language"], "ru")
        self.assertEqual(profile["learning_goal"], "travel")
        self.assertEqual(profile["daily_word_goal"], 10)
        self.assertEqual(profile["active_pack_id"], "ja-basics-100")
        self.assertIsNotNone(profile["onboarding_completed_at"])
        self.assertEqual(
            self.store.get_mirror_preferences(user_id),
            {
                "mode": "conversation",
                "depth": "balanced",
                "level": "adaptive",
            },
        )
        with self.store.Session() as session:
            event_names = session.execute(
                select(AnalyticsEvent.event_name).where(
                    AnalyticsEvent.telegram_user_id == user_id
                )
            ).scalars().all()
        self.assertEqual(
            set(event_names),
            {
                "onboarding_started",
                "onboarding_native_selected",
                "onboarding_pack_selected",
                "onboarding_goal_selected",
                "onboarding_preference_selected",
                "onboarding_completed",
            },
        )
        message.reply_photo.assert_not_awaited()
        completion = query.edit_message_text.await_args
        self.assertIn(bot.CATALOG.require("ja-basics-100").label, completion.args[0])
        self.assertIn(bot.translate("onboarding_goal_travel", "ru"), completion.args[0])
        self.assertIn(
            bot.translate("onboarding_preference_conversation", "ru"),
            completion.args[0],
        )
        self.assertIn("10", completion.args[0])
        final_button = completion.kwargs["reply_markup"].inline_keyboard[0][0]
        self.assertEqual(final_button.callback_data, "start:daily")
        self.assertEqual(
            final_button.text,
            bot.translate("onboarding_start_first_lesson", "ru"),
        )

    async def test_onboarding_begin_asks_for_meaning_language(self):
        user_id = 9904
        message = SimpleNamespace(chat_id=9)
        query = SimpleNamespace(
            data="onboarding:begin",
            answer=AsyncMock(),
            edit_message_text=AsyncMock(),
            message=message,
        )
        update = SimpleNamespace(
            callback_query=query,
            effective_message=message,
            effective_user=SimpleNamespace(id=user_id, first_name="Лена"),
        )
        with (
            patch.object(bot, "_STORE", self.store),
            patch.object(bot, "BOT_ACCESS_MODE", "public"),
            patch.object(bot, "LEGACY_USER_ID", None),
            patch.object(bot, "ADMIN_USER_IDS", set()),
        ):
            await bot.onboarding_cb(update, SimpleNamespace(user_data={}))

        text = query.edit_message_text.await_args.args[0]
        keyboard = query.edit_message_text.await_args.kwargs["reply_markup"]
        callbacks = [row[0].callback_data for row in keyboard.inline_keyboard]
        self.assertIn("Шаг 1 из 5", text)
        self.assertTrue(
            all(value.startswith("onboarding:native:") for value in callbacks)
        )
        profile = self.store.product_profile(user_id)
        self.assertIsNone(profile["native_language"])
        self.assertIsNone(profile["learning_goal"])

    async def test_pack_goal_and_preference_steps_use_native_buttons(self):
        user_id = 9905
        message = SimpleNamespace(chat_id=10)
        query = SimpleNamespace(
            data="onboarding:native:ru",
            answer=AsyncMock(),
            edit_message_text=AsyncMock(),
            message=message,
        )
        update = SimpleNamespace(
            callback_query=query,
            effective_message=message,
            effective_user=SimpleNamespace(
                id=user_id,
                first_name="Лена",
                language_code="ru",
            ),
        )
        context = SimpleNamespace(user_data={})
        with (
            patch.object(bot, "_STORE", self.store),
            patch.object(bot, "BOT_ACCESS_MODE", "public"),
            patch.object(bot, "LEGACY_USER_ID", None),
            patch.object(bot, "ADMIN_USER_IDS", set()),
        ):
            await bot.onboarding_cb(update, context)
            self.assertIn("Шаг 2 из 5", query.edit_message_text.await_args.args[0])

            query.data = "onboarding:pack:en-basics-100"
            await bot.onboarding_cb(update, context)
            goal_edit = query.edit_message_text.await_args
            self.assertIn("Шаг 3 из 5", goal_edit.args[0])
            self.assertEqual(
                {
                    button.callback_data
                    for row in goal_edit.kwargs["reply_markup"].inline_keyboard
                    for button in row
                },
                {
                    "onboarding:goal:basics",
                    "onboarding:goal:travel",
                    "onboarding:goal:conversation",
                    "onboarding:goal:work",
                },
            )

            query.data = "onboarding:goal:work"
            await bot.onboarding_cb(update, context)
            preference_edit = query.edit_message_text.await_args
            self.assertIn("Шаг 4 из 5", preference_edit.args[0])
            self.assertEqual(
                {
                    button.callback_data
                    for row in preference_edit.kwargs["reply_markup"].inline_keyboard
                    for button in row
                },
                {
                    "onboarding:preference:practice",
                    "onboarding:preference:conversation",
                    "onboarding:preference:teacher",
                },
            )
            self.assertEqual(
                self.store.product_profile(user_id)["learning_goal"], "work"
            )

            query.data = "onboarding:preference:teacher"
            await bot.onboarding_cb(update, context)
            pace_edit = query.edit_message_text.await_args

        self.assertIn("Шаг 5 из 5", pace_edit.args[0])
        self.assertEqual(
            self.store.get_mirror_preferences(user_id),
            {"mode": "teacher", "depth": "balanced", "level": "adaptive"},
        )
        callback_values = [
            button.callback_data
            for edit in (goal_edit, preference_edit, pace_edit)
            for row in edit.kwargs["reply_markup"].inline_keyboard
            for button in row
        ]
        self.assertTrue(all(len(value.encode("utf-8")) <= 64 for value in callback_values))

    async def test_onboarding_answers_are_durable_and_isolated_by_user_id(self):
        async def complete(
            user_id: int,
            native: str,
            pack_id: str,
            goal: str,
            preference: str,
            pace: int,
        ) -> None:
            message = SimpleNamespace(
                chat_id=user_id,
                reply_photo=AsyncMock(),
                reply_text=AsyncMock(),
            )
            query = SimpleNamespace(
                data="onboarding:begin",
                answer=AsyncMock(),
                edit_message_text=AsyncMock(),
                message=message,
            )
            update = SimpleNamespace(
                callback_query=query,
                effective_message=message,
                effective_user=SimpleNamespace(
                    id=user_id,
                    first_name="Ученик",
                    language_code="ru",
                ),
            )
            for callback in (
                "onboarding:begin",
                f"onboarding:native:{native}",
                f"onboarding:pack:{pack_id}",
                f"onboarding:goal:{goal}",
                f"onboarding:preference:{preference}",
                f"onboarding:pace:{pace}",
            ):
                query.data = callback
                # Simulate a fresh process/update: no in-memory onboarding state.
                await bot.onboarding_cb(update, SimpleNamespace(user_data={}))

        with (
            patch.object(bot, "_STORE", self.store),
            patch.object(bot, "BOT_ACCESS_MODE", "public"),
            patch.object(bot, "LEGACY_USER_ID", None),
            patch.object(bot, "ADMIN_USER_IDS", set()),
        ):
            await complete(9912, "ru", "en-basics-100", "travel", "practice", 5)
            await complete(9913, "ru", "de-basics-100", "work", "teacher", 20)

        first = self.store.product_profile(9912)
        second = self.store.product_profile(9913)
        self.assertEqual(
            (first["active_pack_id"], first["learning_goal"], first["daily_word_goal"]),
            ("en-basics-100", "travel", 5),
        )
        self.assertEqual(
            (second["active_pack_id"], second["learning_goal"], second["daily_word_goal"]),
            ("de-basics-100", "work", 20),
        )
        self.assertEqual(self.store.get_mirror_preferences(9912)["mode"], "practice")
        self.assertEqual(self.store.get_mirror_preferences(9913)["mode"], "teacher")

    async def test_unknown_goal_preference_and_pace_do_not_complete_onboarding(self):
        user_id = 9914
        message = SimpleNamespace(chat_id=user_id)
        query = SimpleNamespace(
            data="onboarding:goal:not-real",
            answer=AsyncMock(),
            edit_message_text=AsyncMock(),
            message=message,
        )
        update = SimpleNamespace(
            callback_query=query,
            effective_message=message,
            effective_user=SimpleNamespace(id=user_id, language_code="ru"),
        )
        self.store.ensure_user(update.effective_user)
        self.store.activate_user_access(user_id)
        self.store.update_product_profile(user_id, native_language="ru")
        self.store.activate_pack(
            user_id,
            pack_id="en-basics-100",
            language="en",
            source="onboarding",
        )
        with (
            patch.object(bot, "_STORE", self.store),
            patch.object(bot, "BOT_ACCESS_MODE", "public"),
            patch.object(bot, "LEGACY_USER_ID", None),
            patch.object(bot, "ADMIN_USER_IDS", set()),
        ):
            for callback in (
                "onboarding:goal:not-real",
                "onboarding:preference:not-real",
                "onboarding:pace:99",
            ):
                query.data = callback
                await bot.onboarding_cb(update, SimpleNamespace(user_data={}))
                self.assertIsNone(
                    self.store.product_profile(user_id)["onboarding_completed_at"]
                )

    async def test_stale_answers_cannot_skip_fresh_goal_selection(self):
        user_id = 9916
        telegram_user = SimpleNamespace(
            id=user_id,
            first_name="Лена",
            language_code="ru",
        )
        self.store.ensure_user(telegram_user)
        self.store.activate_user_access(user_id)
        self.store.update_product_profile(user_id, learning_goal="travel")
        self.store.set_mirror_preferences(
            user_id,
            mode="conversation",
            depth="balanced",
            level="adaptive",
        )
        initial_daily_word_goal = self.store.product_profile(user_id)[
            "daily_word_goal"
        ]
        message = SimpleNamespace(
            chat_id=user_id,
            reply_photo=AsyncMock(),
            reply_text=AsyncMock(),
        )
        query = SimpleNamespace(
            data="onboarding:begin",
            answer=AsyncMock(),
            edit_message_text=AsyncMock(),
            message=message,
        )
        update = SimpleNamespace(
            callback_query=query,
            effective_message=message,
            effective_user=telegram_user,
        )
        context = SimpleNamespace(user_data={})

        with (
            patch.object(bot, "_STORE", self.store),
            patch.object(bot, "BOT_ACCESS_MODE", "public"),
            patch.object(bot, "LEGACY_USER_ID", None),
            patch.object(bot, "ADMIN_USER_IDS", set()),
        ):
            for callback in (
                "onboarding:begin",
                "onboarding:native:ru",
                "onboarding:pack:en-basics-100",
            ):
                query.data = callback
                await bot.onboarding_cb(update, context)

            rejection_texts = []
            for forged_callback in (
                "onboarding:preference:teacher",
                "onboarding:pace:10",
            ):
                query.data = forged_callback
                await bot.onboarding_cb(update, SimpleNamespace(user_data={}))
                rejection_texts.append(query.edit_message_text.await_args.args[0])

        profile = self.store.product_profile(user_id)
        self.assertIsNone(profile["onboarding_completed_at"])
        self.assertEqual(profile["daily_word_goal"], initial_daily_word_goal)
        self.assertEqual(
            self.store.get_mirror_preferences(user_id)["mode"],
            "conversation",
        )
        self.assertTrue(
            all("Шаг 3 из 5" in text for text in rejection_texts),
            rejection_texts,
        )

    async def test_final_daily_callback_enters_existing_lesson_path(self):
        user_id = 9915
        telegram_user = SimpleNamespace(id=user_id, language_code="ru")
        self.store.ensure_user(telegram_user)
        self.store.activate_user_access(user_id)
        self.store.update_product_profile(
            user_id,
            native_language="ru",
            learning_goal="basics",
            daily_word_goal=5,
            complete_onboarding=True,
            onboarding_version=bot.CURRENT_ONBOARDING_VERSION,
        )
        self.store.activate_pack(
            user_id,
            pack_id="en-basics-100",
            language="en",
            source="onboarding",
        )
        message = SimpleNamespace(chat_id=user_id)
        query = SimpleNamespace(
            data="start:daily",
            answer=AsyncMock(),
            message=message,
        )
        update = SimpleNamespace(
            callback_query=query,
            effective_message=message,
            effective_user=telegram_user,
        )
        context = SimpleNamespace(user_data={})
        with (
            patch.object(bot, "_STORE", self.store),
            patch.object(bot, "BOT_ACCESS_MODE", "public"),
            patch.object(bot, "LEGACY_USER_ID", None),
            patch.object(bot, "ADMIN_USER_IDS", set()),
            patch.object(bot, "start_home_lesson", new=AsyncMock()) as start_lesson,
        ):
            await bot.start_menu_cb(update, context)

        start_lesson.assert_awaited_once_with(query, context, lesson_kind="daily")

    def test_new_onboarding_copy_exists_for_every_interface_locale(self):
        keys = (
            "onboarding_choose_goal",
            "onboarding_goal_basics",
            "onboarding_goal_travel",
            "onboarding_goal_conversation",
            "onboarding_goal_work",
            "onboarding_choose_preference",
            "onboarding_preference_practice",
            "onboarding_preference_conversation",
            "onboarding_preference_teacher",
            "onboarding_start_first_lesson",
        )
        for locale in bot.INTERFACE_LOCALES:
            with self.subTest(locale=locale):
                for key in keys:
                    self.assertTrue(bot.translate(key, locale))


if __name__ == "__main__":
    unittest.main()
