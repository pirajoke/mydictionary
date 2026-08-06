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
            payload["reply_markup"].inline_keyboard[0][0].callback_data,
            "start:daily",
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
        self.assertIn("Два коротких шага", text)
        self.assertEqual(
            message.reply_text.await_args.kwargs["reply_markup"]
            .inline_keyboard[0][0]
            .callback_data,
            "onboarding:begin",
        )
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
        self.assertIn("Два коротких шага", message.reply_text.await_args.args[0])

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
            "onboarding:pack:ja-basics-100",
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
        self.assertEqual(profile["learning_goal"], "basics")
        self.assertEqual(profile["daily_word_goal"], 10)
        self.assertEqual(profile["active_pack_id"], "ja-basics-100")
        self.assertIsNotNone(profile["onboarding_completed_at"])
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
                "onboarding_completed",
            },
        )
        message.reply_photo.assert_awaited_once()

    async def test_onboarding_begin_goes_directly_to_language_selection(self):
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
        self.assertIn("Шаг 1 из 2", text)
        self.assertTrue(all(value.startswith("onboarding:pack:") for value in callbacks))
        profile = self.store.product_profile(user_id)
        self.assertEqual(profile["native_language"], "ru")
        self.assertEqual(profile["learning_goal"], "basics")


if __name__ == "__main__":
    unittest.main()
