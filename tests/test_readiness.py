import asyncio
import json
import logging
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

os.environ.setdefault("BOT_TOKEN", "123456:TESTTOKEN")
os.environ.setdefault("ALLOWED_USER_ID", "1")

import bot
from telegram.error import RetryAfter
from mydictionary.readiness import (
    BotHeartbeat,
    configured_max_age_seconds,
    heartbeat_path,
    inspect_bot_heartbeat,
)


class BotReadinessTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory(prefix="mydictionary-heartbeat-")
        self.path = Path(self.temp_dir.name) / "bot-heartbeat.json"
        self.now = datetime(2026, 8, 4, 12, 0, tzinfo=timezone.utc)

    def tearDown(self):
        self.temp_dir.cleanup()

    def heartbeat(self, observed_at=None):
        return BotHeartbeat(
            self.path,
            release_sha="a" * 40,
            access_mode="pilot",
            now=lambda: observed_at or self.now,
        )

    def test_ready_heartbeat_is_atomic_private_and_fresh(self):
        heartbeat = self.heartbeat()
        heartbeat.mark_ready()

        readiness = inspect_bot_heartbeat(
            self.path,
            max_age_seconds=45,
            now=self.now + timedelta(seconds=10),
        )

        self.assertTrue(readiness.ready)
        self.assertEqual(readiness.reason, "ready")
        self.assertEqual(readiness.age_seconds, 10)
        self.assertEqual(readiness.release_sha, "a" * 40)
        self.assertEqual(readiness.access_mode, "pilot")
        self.assertEqual(self.path.stat().st_mode & 0o777, 0o600)
        self.assertEqual(list(self.path.parent.glob(f".{self.path.name}.*")), [])

    def test_stale_stopped_and_invalid_heartbeats_fail_closed(self):
        heartbeat = self.heartbeat()
        heartbeat.mark_ready()
        stale = inspect_bot_heartbeat(
            self.path,
            max_age_seconds=45,
            now=self.now + timedelta(seconds=46),
        )
        self.assertFalse(stale.ready)
        self.assertEqual(stale.reason, "heartbeat_stale")

        heartbeat.mark_stopped()
        stopped = inspect_bot_heartbeat(
            self.path, max_age_seconds=45, now=self.now
        )
        self.assertFalse(stopped.ready)
        self.assertEqual(stopped.reason, "bot_stopped")

        self.path.write_text(json.dumps({"state": "ready"}), encoding="utf-8")
        invalid = inspect_bot_heartbeat(
            self.path, max_age_seconds=45, now=self.now
        )
        self.assertFalse(invalid.ready)
        self.assertEqual(invalid.reason, "heartbeat_invalid")

        future = self.heartbeat(self.now + timedelta(minutes=1))
        future.mark_ready()
        invalid_future = inspect_bot_heartbeat(
            self.path, max_age_seconds=45, now=self.now
        )
        self.assertFalse(invalid_future.ready)
        self.assertEqual(invalid_future.reason, "heartbeat_invalid")

    def test_missing_heartbeat_and_configuration_are_fail_closed(self):
        readiness = inspect_bot_heartbeat(
            self.path, max_age_seconds=45, now=self.now
        )
        self.assertFalse(readiness.ready)
        self.assertEqual(readiness.reason, "heartbeat_missing")

        with patch.dict(os.environ, {"BOT_HEARTBEAT_MAX_AGE_SECONDS": "60"}):
            self.assertEqual(configured_max_age_seconds(), 60)
        with patch.dict(os.environ, {"BOT_HEARTBEAT_MAX_AGE_SECONDS": "5"}):
            with self.assertRaises(RuntimeError):
                configured_max_age_seconds()

    def test_heartbeat_path_supports_explicit_shared_runtime_location(self):
        default = Path(self.temp_dir.name) / "data"
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(
                heartbeat_path(default), default / "bot-heartbeat.json"
            )
        with patch.dict(
            os.environ, {"BOT_HEARTBEAT_PATH": str(self.path)}, clear=True
        ):
            self.assertEqual(heartbeat_path(default), self.path)


class BotPollingReadinessTest(unittest.IsolatedAsyncioTestCase):
    def test_public_command_menu_has_at_most_seven_contextual_commands(self):
        base = bot.build_bot_commands(ai_enabled=False)
        with_ai = bot.build_bot_commands(ai_enabled=True)

        self.assertEqual(
            [command.command for command in base],
            ["start", "learn", "lang", "stats", "privacy", "help"],
        )
        self.assertEqual(
            [command.command for command in with_ai],
            ["start", "learn", "lang", "stats", "ai", "privacy", "help"],
        )
        self.assertLessEqual(len(base), 7)
        self.assertLessEqual(len(with_ai), 7)

    async def test_polling_publishes_lifecycle_and_closes_resources(self):
        store = SimpleNamespace(
            database_url="sqlite:///test.db",
            recover_stale_ai_usage=MagicMock(return_value=0),
            close=MagicMock(),
        )
        telegram_bot = SimpleNamespace(
            delete_webhook=AsyncMock(),
            set_my_commands=AsyncMock(),
            set_my_name=AsyncMock(),
            set_my_short_description=AsyncMock(),
            set_my_description=AsyncMock(),
            get_updates=AsyncMock(side_effect=[[], asyncio.CancelledError()]),
        )
        application = SimpleNamespace(
            bot=telegram_bot,
            add_handler=MagicMock(),
            initialize=AsyncMock(),
            start=AsyncMock(),
            stop=AsyncMock(),
            shutdown=AsyncMock(),
            process_update=AsyncMock(),
        )
        builder = MagicMock()
        builder.token.return_value.build.return_value = application
        heartbeat = MagicMock()
        profile = {
            "bot_name": "MY DICTIONARY",
            "bot_short_description": "Learn words",
            "bot_description": "Learn words with focused blocks",
        }

        with (
            patch.object(bot, "get_store", return_value=store),
            patch.object(bot.Application, "builder", return_value=builder),
            patch.object(bot, "BOT_HEARTBEAT", heartbeat),
            patch.object(bot, "get_bot_profile", return_value=profile),
        ):
            with self.assertRaises(asyncio.CancelledError):
                await bot.manual_polling()

        heartbeat.mark_starting.assert_called_once_with()
        heartbeat.mark_ready.assert_called_once_with()
        heartbeat.mark_stopped.assert_called_once_with()
        application.stop.assert_awaited_once_with()
        application.shutdown.assert_awaited_once_with()
        store.close.assert_called_once_with()

    def test_httpx_request_logging_is_not_enabled(self):
        self.assertGreaterEqual(logging.getLogger("httpx").level, logging.WARNING)

    async def test_profile_rate_limit_does_not_block_polling_or_leak_token(self):
        store = SimpleNamespace(
            database_url="sqlite:///test.db",
            recover_stale_ai_usage=MagicMock(return_value=0),
            close=MagicMock(),
        )
        telegram_bot = SimpleNamespace(
            delete_webhook=AsyncMock(),
            set_my_commands=AsyncMock(),
            set_my_name=AsyncMock(
                side_effect=RetryAfter(timedelta(seconds=60))
            ),
            set_my_short_description=AsyncMock(),
            set_my_description=AsyncMock(),
            get_updates=AsyncMock(side_effect=[[], asyncio.CancelledError()]),
        )
        application = SimpleNamespace(
            bot=telegram_bot,
            add_handler=MagicMock(),
            initialize=AsyncMock(),
            start=AsyncMock(),
            stop=AsyncMock(),
            shutdown=AsyncMock(),
            process_update=AsyncMock(),
        )
        builder = MagicMock()
        builder.token.return_value.build.return_value = application
        heartbeat = MagicMock()
        profile = {
            "bot_name": "MY DICTIONARY",
            "bot_short_description": "Learn words",
            "bot_description": "Learn words with focused blocks",
        }

        with (
            patch.object(bot, "get_store", return_value=store),
            patch.object(bot.Application, "builder", return_value=builder),
            patch.object(bot, "BOT_HEARTBEAT", heartbeat),
            patch.object(bot, "get_bot_profile", return_value=profile),
            self.assertLogs(bot.logger, level="WARNING") as captured,
        ):
            with self.assertRaises(asyncio.CancelledError):
                await bot.manual_polling()

        telegram_bot.get_updates.assert_awaited()
        telegram_bot.set_my_short_description.assert_awaited_once_with(
            profile["bot_short_description"]
        )
        telegram_bot.set_my_description.assert_awaited_once_with(
            profile["bot_description"]
        )
        logs = "\n".join(captured.output)
        self.assertIn("operation=name error_type=RetryAfter", logs)
        self.assertNotIn("TESTTOKEN", logs)


if __name__ == "__main__":
    unittest.main()
