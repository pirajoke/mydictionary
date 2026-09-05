from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import AsyncMock, MagicMock, patch


os.environ.setdefault("BOT_TOKEN", "123456:TESTTOKEN_ABCDEFGHIJKLMNOP")
os.environ.setdefault("ALLOWED_USER_ID", "1")
os.environ.setdefault("ALLOW_SQLITE_DEV", "true")

import bot
from mydictionary import miniapp
from mydictionary.admin import create_app
from mydictionary.localization import translate
from mydictionary.storage import DatabaseStore, User


ROOT = Path(__file__).resolve().parents[1]
USER_ID = 904_221


class LexiCommandLocaleContractTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="lexi-command-locale-")
        self.store = DatabaseStore(
            f"sqlite:///{Path(self.temporary.name) / 'locale.sqlite3'}"
        )
        self.store.ensure_user(
            SimpleNamespace(
                id=USER_ID,
                username="learner",
                first_name="Learner",
                last_name=None,
                language_code="fr",
            )
        )
        with self.store.Session.begin() as session:
            learner = session.get(User, USER_ID)
            learner.access_status = "active"
            learner.privacy_status = "active"
        self.store.activate_pack(
            USER_ID,
            pack_id="en-basics-100",
            language="en",
            source="test",
        )

    def tearDown(self) -> None:
        self.store.close()
        self.temporary.cleanup()

    def app(self):
        return create_app(
            {
                "TESTING": True,
                "SECRET_KEY": "s" * 40,
                "ADMIN_USERNAME": "owner",
                "ADMIN_PASSWORD": "password",
                "MINIAPP_ENABLED": True,
                "MINIAPP_PUBLIC_URL": "https://mydictionary.example.test/miniapp",
                "MINIAPP_BOT_USERNAME": "mydictionary_test_bot",
                "MINIAPP_AUTH_MAX_AGE_SECONDS": 300,
                "BOT_TOKEN_FILE": "/protected/bot-token",
                "AI_TUTOR_ENABLED": True,
                "TELEGRAM_STARS_ENABLED": False,
            },
            database_store=self.store,
        )

    def test_saved_russian_interface_immediately_scopes_russian_commands_to_chat(self) -> None:
        app = self.app()
        client = app.test_client()
        sync_commands = getattr(miniapp, "sync_telegram_chat_commands", None)
        self.assertTrue(
            callable(sync_commands),
            "Mini App locale changes must synchronize the private Telegram command menu",
        )
        if not callable(sync_commands):
            return

        with (
            patch.object(
                miniapp,
                "verify_init_data",
                return_value={
                    "user_id": USER_ID,
                    "display_name": "Learner",
                    "language_code": "fr",
                },
            ),
            patch.object(miniapp, "sync_telegram_chat_commands") as sync,
        ):
            response = client.post(
                "/miniapp/api/interface-locale",
                headers={"X-Telegram-Init-Data": "signed"},
                json={"locale": "ru"},
            )

        self.assertEqual(response.status_code, 200)
        sync.assert_called_once()
        kwargs = sync.call_args.kwargs
        self.assertEqual(kwargs["user_id"], USER_ID)
        self.assertEqual(kwargs["locale"], "ru")
        self.assertTrue(kwargs["ai_enabled"])
        self.assertTrue(kwargs["miniapp_enabled"])

    def test_chat_command_sync_posts_only_bounded_russian_commands_to_exact_chat(self) -> None:
        sync_commands = getattr(miniapp, "sync_telegram_chat_commands", None)
        self.assertTrue(callable(sync_commands))
        if not callable(sync_commands):
            return
        response = MagicMock(status=200)
        response.read.return_value = b'{"ok":true,"result":true}'
        connection = MagicMock()
        connection.getresponse.return_value = response
        with patch.object(miniapp, "HTTPSConnection", return_value=connection):
            sync_commands(
                bot_token="123456:TESTTOKEN_ABCDEFGHIJKLMNOP",
                user_id=USER_ID,
                locale="ru",
                ai_enabled=True,
                miniapp_enabled=True,
            )

        request = connection.request.call_args
        self.assertEqual(request.args[0], "POST")
        self.assertTrue(request.args[1].endswith("/setMyCommands"))
        import json

        request_body = request.kwargs["body"]
        self.assertIsInstance(
            request_body,
            bytes,
            "http.client requires explicit UTF-8 bytes for localized command copy",
        )
        payload = json.loads(request_body.decode("utf-8"))
        self.assertEqual(payload["scope"], {"type": "chat", "chat_id": USER_ID})
        self.assertEqual(payload["commands"][0]["description"], translate("start_daily", "ru"))
        self.assertNotIn("fr", request_body.decode("utf-8").casefold())
        connection.close.assert_called_once()


class LexiBotCommandRepairContractTest(unittest.IsolatedAsyncioTestCase):
    async def test_next_bot_interaction_repairs_chat_scoped_commands_from_saved_locale(self) -> None:
        sync = getattr(bot, "sync_user_command_menu", None)
        self.assertTrue(
            callable(sync),
            "bot runtime must repair chat-scoped commands from the durable locale",
        )
        if not callable(sync):
            return

        telegram_bot = SimpleNamespace(set_my_commands=AsyncMock())
        await sync(telegram_bot, user_id=USER_ID, locale="ru")

        telegram_bot.set_my_commands.assert_awaited_once()
        call = telegram_bot.set_my_commands.await_args
        descriptions = {
            command.command: command.description for command in call.args[0]
        }
        self.assertEqual(descriptions["continue"], translate("start_daily", "ru"))
        self.assertNotEqual(descriptions["continue"], translate("start_daily", "fr"))
        self.assertEqual(call.kwargs["scope"].chat_id, USER_ID)


class LexiFirstStartMediaContractTest(unittest.IsolatedAsyncioTestCase):
    async def test_first_onboarding_message_uses_selected_fox_with_text_fallback(self) -> None:
        message = SimpleNamespace(reply_photo=AsyncMock(), reply_text=AsyncMock())
        await bot.send_onboarding_intro(message, locale="ru")

        message.reply_photo.assert_awaited_once()
        payload = message.reply_photo.await_args.kwargs
        self.assertEqual(payload["caption"], translate("onboarding_intro", "ru"))
        self.assertEqual(
            payload["reply_markup"].inline_keyboard[0][0].callback_data,
            "onboarding:begin",
        )
        message.reply_text.assert_not_awaited()

        fallback = SimpleNamespace(
            reply_photo=AsyncMock(side_effect=RuntimeError("photo unavailable")),
            reply_text=AsyncMock(),
        )
        await bot.send_onboarding_intro(fallback, locale="ru")
        fallback.reply_text.assert_awaited_once_with(
            translate("onboarding_intro", "ru"),
            reply_markup=bot.onboarding_intro_keyboard("ru"),
        )

    def test_start_media_uses_one_canonical_fox_asset_not_the_old_dictionary_banner(self) -> None:
        self.assertEqual(
            bot.WELCOME_BANNER_PATH,
            ROOT / "mydictionary/static/mascot/lexi-telegram-avatar-v1.jpg",
        )
        self.assertFalse((ROOT / "assets/lexi-welcome-v1.jpg").exists())


class LexiMiniAppArtworkContractTest(unittest.TestCase):
    def test_all_five_tabs_use_the_same_compact_artwork_format(self) -> None:
        html = (ROOT / "mydictionary/templates/miniapp.html").read_text(
            encoding="utf-8"
        )
        css = (ROOT / "mydictionary/static/miniapp.css").read_text(
            encoding="utf-8"
        )

        self.assertEqual(html.count('class="section-art"'), 5)
        for panel in ("profile", "words", "credits", "languages", "settings"):
            with self.subTest(panel=panel):
                self.assertIn(f"lexi-section-{panel}-v1.webp", html)
        self.assertNotIn("lexi-miniapp-hero-v1.jpg", html)
        self.assertNotIn('class="lexi-hero', html)
        self.assertNotIn('class="settings-visual', html)
        self.assertEqual(html.count("section-hero"), 5)
        self.assertIn(".section-hero .section-art", css)
        self.assertIn("width: 100%", css)
        self.assertIn("aspect-ratio: 2 / 1", css)
        self.assertIn("object-fit: cover", css)

    def test_all_tab_artwork_files_are_webp_1200_by_600(self) -> None:
        directory = ROOT / "mydictionary/static/miniapp"
        for panel in ("profile", "words", "credits", "languages", "settings"):
            path = directory / f"lexi-section-{panel}-v1.webp"
            with self.subTest(panel=panel):
                self.assertTrue(path.is_file())
                data = path.read_bytes()
                self.assertEqual(data[:4], b"RIFF")
                self.assertEqual(data[8:12], b"WEBP")
                frame = data.find(b"\x9d\x01\x2a")
                self.assertGreater(frame, 0)
                width = int.from_bytes(data[frame + 3 : frame + 5], "little") & 0x3FFF
                height = int.from_bytes(data[frame + 5 : frame + 7], "little") & 0x3FFF
                self.assertEqual((width, height), (1200, 600))


if __name__ == "__main__":
    unittest.main()
