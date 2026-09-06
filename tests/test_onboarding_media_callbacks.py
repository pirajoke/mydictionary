from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import AsyncMock, patch

from telegram.error import BadRequest


os.environ.setdefault("BOT_TOKEN", "123456:TESTTOKEN")
os.environ.setdefault("ALLOWED_USER_ID", "1")

import bot
from mydictionary.storage import DatabaseStore


class _PhotoCallbackQuery:
    """A Telegram callback query whose source message is a photo caption."""

    def __init__(self, message) -> None:
        self.data = "onboarding:begin"
        self.message = message
        self.answer = AsyncMock()
        self.edit_message_text = AsyncMock(
            side_effect=BadRequest("There is no text in the message to edit")
        )
        self.caption_edits: list[tuple[str, object | None]] = []

    async def edit_message_caption(self, *, caption, reply_markup=None) -> None:
        self.caption_edits.append((caption, reply_markup))


class OnboardingMediaCallbackRegressionTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory(prefix="onboarding-media-")
        self.store = DatabaseStore(
            f"sqlite:///{Path(self.temp_dir.name) / 'onboarding.db'}"
        )

    def tearDown(self) -> None:
        self.store.close()
        self.temp_dir.cleanup()

    async def test_photo_onboarding_edits_caption_through_every_step(self) -> None:
        """AC-MEDIA-1: every callback remains valid on the photo intro."""

        user_id = 9961
        message = SimpleNamespace(
            chat_id=91,
            photo=(SimpleNamespace(file_id="welcome-photo"),),
            caption=bot.translate("onboarding_intro", "ru"),
            reply_photo=AsyncMock(),
            reply_text=AsyncMock(),
        )
        query = _PhotoCallbackQuery(message)
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
            for callback_data in (
                "onboarding:begin",
                "onboarding:native:ru",
                "onboarding:pack:en-basics-100",
                "onboarding:pace:10",
            ):
                query.data = callback_data
                await bot.onboarding_cb(update, context)

        query.edit_message_text.assert_not_awaited()
        self.assertEqual(len(query.caption_edits), 4)
        self.assertIn("Шаг 1 из 3", query.caption_edits[0][0])
        self.assertIn("Шаг 2 из 3", query.caption_edits[1][0])
        self.assertIn("Шаг 3 из 3", query.caption_edits[2][0])
        self.assertIsNotNone(
            self.store.product_profile(user_id)["onboarding_completed_at"]
        )

    async def test_photo_onboarding_error_and_legacy_paths_also_edit_caption(self) -> None:
        """EC-MEDIA-1: no callback branch tries to edit photo message text."""

        cases = (
            "onboarding:native:not-a-language",
            "onboarding:pack:not-a-pack",
            "onboarding:goal:basics",
            "onboarding:pace:10",
            "onboarding:stale",
        )
        with (
            patch.object(bot, "_STORE", self.store),
            patch.object(bot, "BOT_ACCESS_MODE", "public"),
            patch.object(bot, "LEGACY_USER_ID", None),
            patch.object(bot, "ADMIN_USER_IDS", set()),
        ):
            for offset, callback_data in enumerate(cases):
                with self.subTest(callback_data=callback_data):
                    message = SimpleNamespace(
                        chat_id=92 + offset,
                        photo=(SimpleNamespace(file_id="welcome-photo"),),
                        caption=bot.translate("onboarding_intro", "ru"),
                    )
                    query = _PhotoCallbackQuery(message)
                    query.data = callback_data
                    update = SimpleNamespace(
                        callback_query=query,
                        effective_message=message,
                        effective_user=SimpleNamespace(
                            id=9970 + offset,
                            first_name="Лена",
                            language_code="ru",
                        ),
                    )

                    await bot.onboarding_cb(
                        update, SimpleNamespace(user_data={})
                    )

                    query.edit_message_text.assert_not_awaited()
                    self.assertEqual(len(query.caption_edits), 1)


if __name__ == "__main__":
    unittest.main()
