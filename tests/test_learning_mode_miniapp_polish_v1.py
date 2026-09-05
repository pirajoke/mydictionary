import os
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

from telegram import MenuButtonWebApp


os.environ.setdefault("BOT_TOKEN", "123456:TESTTOKEN_ABCDEFGHIJKLMNOP")
os.environ.setdefault("ALLOWED_USER_ID", "1")
os.environ.setdefault("ALLOW_SQLITE_DEV", "true")

import bot
from mydictionary import miniapp


ROOT = Path(__file__).resolve().parents[1]


class LearningModeMessageCleanupContractTest(unittest.IsolatedAsyncioTestCase):
    def _block_context(self):
        user_data = {}
        bot.reset_block_state(
            user_data,
            [10, 21, 22],
            "ja",
            "people",
            "ja-basics-100",
        )
        send_message = AsyncMock(
            side_effect=[
                SimpleNamespace(message_id=101),
                SimpleNamespace(message_id=102),
            ]
        )
        client = SimpleNamespace(
            send_message=send_message,
            delete_message=AsyncMock(),
        )
        return user_data, SimpleNamespace(user_data=user_data, bot=client)

    async def _open_review_words(self, context):
        session_id = context.user_data["block_session"]
        with (
            patch.object(bot, "activate_block_language"),
            patch.object(bot, "record_product_event"),
            patch.object(bot, "send_pronunciation", new=AsyncMock()),
        ):
            for idx in (10, 21):
                query = SimpleNamespace(
                    data=f"lplay:{session_id}:{idx}",
                    answer=AsyncMock(),
                    message=SimpleNamespace(chat_id=123),
                )
                update = SimpleNamespace(
                    callback_query=query,
                    effective_user=SimpleNamespace(id=1),
                )
                await bot.learn_play_cb.__wrapped__(update, context)

    async def test_ac1_quiz_and_written_keep_review_words_and_last_audio(self):
        for mode in ("quiz", "type"):
            with self.subTest(mode=mode):
                user_data, context = self._block_context()
                await self._open_review_words(context)
                user_data[bot.LAST_PRONUNCIATION_MESSAGES_KEY] = {"123": 103}
                previous_session = user_data["block_session"]
                query = SimpleNamespace(
                    data=f"bmode:{previous_session}:{mode}",
                    answer=AsyncMock(),
                    message=SimpleNamespace(chat_id=123),
                )
                update = SimpleNamespace(
                    callback_query=query,
                    effective_user=SimpleNamespace(id=1, language_code="fr"),
                )
                pack = bot.CATALOG.require("ja-basics-100")
                with (
                    patch.object(bot, "activate_block_language"),
                    patch.object(bot, "active_content_pack", return_value=pack),
                    patch.object(bot, "record_product_event"),
                    patch.object(bot, "block_send_question", new=AsyncMock()) as send,
                ):
                    await bot.block_mode_cb.__wrapped__(update, context)

                context.bot.delete_message.assert_not_awaited()
                self.assertEqual(
                    user_data.get("block_review_messages", {}).get("123"),
                    [101, 102],
                )
                self.assertEqual(
                    user_data.get(bot.LAST_PRONUNCIATION_MESSAGES_KEY, {}).get("123"),
                    103,
                )
                self.assertEqual(user_data["block_mode"], mode)
                self.assertEqual(user_data["block_all_indices"], [10, 21, 22])
                send.assert_awaited_once_with(query, context)

    async def test_ac2_mode_switch_never_attempts_cleanup(self):
        user_data, context = self._block_context()
        user_data["block_review_messages"] = {"123": [101, 102]}
        user_data[bot.LAST_PRONUNCIATION_MESSAGES_KEY] = {"123": 103}
        context.bot.delete_message.side_effect = RuntimeError("must not delete")
        session_id = user_data["block_session"]
        query = SimpleNamespace(
            data=f"bmode:{session_id}:quiz",
            answer=AsyncMock(),
            message=SimpleNamespace(chat_id=123),
        )
        update = SimpleNamespace(
            callback_query=query,
            effective_user=SimpleNamespace(id=1),
        )
        pack = bot.CATALOG.require("ja-basics-100")
        with (
            patch.object(bot, "activate_block_language"),
            patch.object(bot, "active_content_pack", return_value=pack),
            patch.object(bot, "record_product_event"),
            patch.object(bot, "block_send_question", new=AsyncMock()) as send,
        ):
            await bot.block_mode_cb.__wrapped__(update, context)

        context.bot.delete_message.assert_not_awaited()
        self.assertEqual(user_data["block_review_messages"], {"123": [101, 102]})
        self.assertEqual(
            user_data[bot.LAST_PRONUNCIATION_MESSAGES_KEY],
            {"123": 103},
        )
        send.assert_awaited_once_with(query, context)

    def test_ec1_review_tracking_is_positive_bot_owned_and_bounded(self):
        user_data = {}
        context = SimpleNamespace(user_data=user_data, bot=SimpleNamespace())
        for invalid in (None, 0, -1, True, "42"):
            bot.track_block_review_message(
                123,
                SimpleNamespace(message_id=invalid),
                context,
            )
        for message_id in range(1, 26):
            bot.track_block_review_message(
                123,
                SimpleNamespace(message_id=message_id),
                context,
            )
        bot.track_block_review_message(
            123,
            SimpleNamespace(message_id=25),
            context,
        )

        self.assertEqual(
            user_data[bot.BLOCK_REVIEW_MESSAGES_KEY]["123"],
            list(range(6, 26)),
        )


class TelegramMenuAndAvatarContractTest(unittest.IsolatedAsyncioTestCase):
    async def test_ac3_persistent_webapp_button_is_named_menu(self):
        telegram_bot = SimpleNamespace(
            set_my_commands=AsyncMock(),
            set_my_name=AsyncMock(),
            set_my_short_description=AsyncMock(),
            set_my_description=AsyncMock(),
            set_chat_menu_button=AsyncMock(),
        )
        settings = SimpleNamespace(
            enabled=True,
            public_url="https://mydictionary.meshly.fr/miniapp",
        )
        with patch.object(bot, "MINIAPP_SETTINGS", settings):
            await bot.sync_telegram_profile(telegram_bot)

        menu = telegram_bot.set_chat_menu_button.await_args.kwargs["menu_button"]
        self.assertIsInstance(menu, MenuButtonWebApp)
        self.assertEqual(menu.text, "Menu")

    def test_ac4_signed_telegram_cdn_avatar_and_client_fallback_are_supported(self):
        safe_urls = (
            "https://t.me/i/userpic/320/avatar.jpeg",
            "https://cdn4.cdn-telegram.org/file/avatar.jpeg",
            "https://cdn4.telesco.pe/file/avatar.svg",
        )
        for value in safe_urls:
            with self.subTest(value=value):
                self.assertEqual(miniapp._safe_telegram_photo_url(value), value)
        for value in (
            "http://cdn4.telesco.pe/file/avatar.jpeg",
            "https://user:password@cdn-telegram.org/avatar.jpeg",
            "https://cdn-telegram.org:444/avatar.jpeg",
            "https://evil.example/avatar.jpeg",
        ):
            with self.subTest(value=value):
                self.assertEqual(miniapp._safe_telegram_photo_url(value), "")

        js = (ROOT / "mydictionary/static/miniapp.js").read_text(encoding="utf-8")
        self.assertIn("initDataUnsafe.user.photo_url", js)
        self.assertIn("safeTelegramPhotoUrl", js)
        admin_source = (ROOT / "mydictionary/admin.py").read_text(encoding="utf-8")
        for host in ("cdn-telegram.org", "*.cdn-telegram.org", "telesco.pe", "*.telesco.pe"):
            self.assertIn(host, admin_source)


class MiniAppCompactIllustratedSectionsContractTest(unittest.TestCase):
    def setUp(self):
        self.css = (ROOT / "mydictionary/static/miniapp.css").read_text(encoding="utf-8")
        self.html = (ROOT / "mydictionary/templates/miniapp.html").read_text(encoding="utf-8")

    def test_ac5_compact_profile_and_navigation_keep_touch_targets(self):
        required = (
            "width: clamp(88px, 27vw, 112px)",
            ".credit-chip > span:first-child { color: var(--amber); font-size: .95rem; }",
            "min-height: 48px",
            ".nav-icon { display: grid; place-items: center; width: 32px; height: 32px",
            ".bottom-nav button { position: relative; min-width: 0; min-height: 58px",
            ".calendar-day { display: grid; place-items: center; min-width: 0; min-height: 32px",
        )
        for contract in required:
            with self.subTest(contract=contract):
                self.assertIn(contract, self.css)
        self.assertNotIn("font-size: 1.35rem", self.css)
        self.assertIn("min-height: 44px", self.css)

    def test_ac6_three_local_section_images_are_optimized_and_decorative(self):
        expected = (
            "lexi-section-words-v1.webp",
            "lexi-section-credits-v1.webp",
            "lexi-section-languages-v1.webp",
        )
        self.assertEqual(self.html.count('class="section-art"'), 3)
        for filename in expected:
            with self.subTest(filename=filename):
                self.assertIn(filename, self.html)
                path = ROOT / "mydictionary/static/miniapp" / filename
                self.assertTrue(path.is_file(), f"missing generated asset: {filename}")
                data = path.read_bytes()
                self.assertGreater(len(data), 2_000)
                self.assertEqual(data[:4], b"RIFF")
                self.assertEqual(data[8:12], b"WEBP")
        for contract in ('alt=""', 'loading="lazy"', 'decoding="async"'):
            self.assertGreaterEqual(self.html.count(contract), 3)


if __name__ == "__main__":
    unittest.main()
