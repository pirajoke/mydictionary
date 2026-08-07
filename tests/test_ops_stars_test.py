import importlib.util
from datetime import datetime, timezone
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "mydictionary_stars_test", ROOT / "ops" / "mydictionary_stars_test.py"
)
stars_test = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(stars_test)


def environment():
    return {
        "TELEGRAM_API_ENVIRONMENT": "test",
        "TELEGRAM_TEST_RUN_ID": "stars-gate4-20260807",
        "TELEGRAM_TEST_USER_ID": "7001",
        "TELEGRAM_TEST_DATABASE_NAME": "mydictionary_stars_test",
        "TELEGRAM_TEST_DATA_DIR": "/private/tmp/mydictionary-stars-test",
        "BOT_TOKEN": "123456:TEST_ONLY_TOKEN",
        "BOT_ACCESS_MODE": "allowlist",
        "ALLOWED_USER_ID": "7001",
        "DATABASE_URL": (
            "postgresql+psycopg://tester@/mydictionary_stars_test?host=/tmp"
        ),
        "DATA_DIR": "/private/tmp/mydictionary-stars-test",
        "TELEGRAM_STARS_ENABLED": "true",
        "AI_TUTOR_ENABLED": "false",
        "VOICE_TUTOR_ENABLED": "false",
        "BILLING_PAYLOAD_SECRET": "s" * 40,
        "BILLING_SUPPORT_CONTACT": "@test_support",
        "BILLING_TERMS_TEXT": "Test-only Telegram Stars terms",
        "BILLING_TERMS_VERSION": "stars-test-2026-08-07",
        "BILLING_TERMS_APPROVED": "true",
        "BILLING_NET_MICRO_USD_PER_XTR": "1000",
        "BILLING_ECONOMICS_REVIEWED_ON": datetime.now(timezone.utc)
        .date()
        .isoformat(),
    }


class StarsTestPreflightTest(unittest.TestCase):
    def test_check_returns_only_safe_test_metadata(self):
        result = stars_test.check(environment())
        rendered = str(result)
        self.assertTrue(result["ok"])
        self.assertEqual(result["telegram_environment"], "test")
        self.assertEqual(result["bot_api_path"], "/test")
        self.assertNotIn("TEST_ONLY_TOKEN", rendered)
        self.assertNotIn("7001", rendered)
        self.assertNotIn("postgresql", rendered)

    def test_check_rejects_production_runtime(self):
        with self.assertRaisesRegex(RuntimeError, "requires TELEGRAM_API_ENVIRONMENT"):
            stars_test.check({})


if __name__ == "__main__":
    unittest.main()
