import os
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch


os.environ.setdefault("BOT_TOKEN", "123456:TESTTOKEN")
os.environ.setdefault("ALLOWED_USER_ID", "1")

import bot
from mydictionary.bot_profile import BOT_PROFILE_DEFAULTS, render_start_text


class BotProfileTest(unittest.TestCase):
    def test_default_start_is_russian_first_and_explains_card_order(self):
        text = render_start_text(BOT_PROFILE_DEFAULTS, "Макс")
        self.assertTrue(text.startswith("Привет, Макс!"))
        self.assertIn("значение по-русски", text)
        self.assertIn("латинская транскрипция", text)
        self.assertIn("голосовое произношение", text)
        self.assertLessEqual(len(text), 1024)

    def test_start_keyboard_routes_primary_workflows(self):
        callbacks = [
            button.callback_data
            for row in bot.start_keyboard().inline_keyboard
            for button in row
        ]
        self.assertEqual(
            callbacks,
            ["start:learn", "start:lang", "start:stats", "start:about"],
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
            "start:learn",
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


if __name__ == "__main__":
    unittest.main()
