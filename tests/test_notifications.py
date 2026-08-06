import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

os.environ.setdefault("BOT_TOKEN", "123456:TESTTOKEN")
os.environ.setdefault("ALLOWED_USER_ID", "1")

import bot
from telegram.error import TelegramError

from mydictionary.admin_store import AdminStore
from mydictionary.storage import DatabaseStore, TelegramNotification


class TelegramNotificationDeliveryTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(
            prefix="mydictionary-notifications-"
        )
        database_path = Path(self.temporary.name) / "notifications.db"
        self.store = DatabaseStore(f"sqlite:///{database_path}")
        self.user_id = 8801
        self.store.ensure_user(
            SimpleNamespace(
                id=self.user_id,
                username="pilot_user",
                first_name="Pilot",
                last_name=None,
                language_code="ru",
            )
        )
        AdminStore(self.store).set_user_access_status(
            self.user_id,
            status="active",
            actor="test",
        )

    def tearDown(self):
        self.store.close()
        self.temporary.cleanup()

    async def test_delivery_marks_notification_sent(self):
        telegram_bot = SimpleNamespace(send_message=AsyncMock())

        delivered = await bot.deliver_telegram_notifications(
            telegram_bot, self.store
        )

        self.assertEqual(delivered, 1)
        telegram_bot.send_message.assert_awaited_once()
        with self.store.Session() as session:
            notification = session.query(TelegramNotification).one()
            self.assertEqual(notification.status, "sent")
            self.assertEqual(notification.attempts, 1)
            self.assertIsNotNone(notification.sent_at)

    async def test_temporary_failure_is_safely_deferred(self):
        telegram_bot = SimpleNamespace(
            send_message=AsyncMock(side_effect=TelegramError("temporary"))
        )

        with self.assertLogs(bot.logger, level="WARNING") as captured:
            delivered = await bot.deliver_telegram_notifications(
                telegram_bot, self.store
            )

        self.assertEqual(delivered, 0)
        with self.store.Session() as session:
            notification = session.query(TelegramNotification).one()
            self.assertEqual(notification.status, "pending")
            self.assertEqual(notification.attempts, 1)
            self.assertEqual(notification.last_error_code, "TelegramError")
        logs = "\n".join(captured.output)
        self.assertIn("error_type=TelegramError status=pending", logs)
        self.assertNotIn(str(self.user_id), logs)


if __name__ == "__main__":
    unittest.main()
