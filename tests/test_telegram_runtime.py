import unittest
from unittest.mock import MagicMock

from mydictionary.telegram_runtime import (
    TelegramRuntimeConfigurationError,
    TelegramRuntimeSettings,
)


def environment_values(**overrides):
    values = {
        "TELEGRAM_API_ENVIRONMENT": "test",
        "TELEGRAM_TEST_RUN_ID": "stars-gate4-20260807",
        "TELEGRAM_TEST_USER_ID": "7001",
        "TELEGRAM_TEST_DATABASE_NAME": "mydictionary_stars_test",
        "TELEGRAM_TEST_DATA_DIR": "/private/tmp/mydictionary-stars-test",
        "BOT_TOKEN": "123456:TEST_ONLY_TOKEN",
        "BOT_ACCESS_MODE": "allowlist",
        "ALLOWED_USER_IDS": "7001",
        "DATABASE_URL": (
            "postgresql+psycopg://tester@/mydictionary_stars_test?host=/tmp"
        ),
        "DATA_DIR": "/private/tmp/mydictionary-stars-test",
        "TELEGRAM_STARS_ENABLED": "true",
        "AI_TUTOR_ENABLED": "false",
        "VOICE_TUTOR_ENABLED": "false",
    }
    values.update(overrides)
    return values


class TelegramRuntimeSettingsTest(unittest.TestCase):
    def test_production_defaults_keep_standard_bot_api(self):
        settings = TelegramRuntimeSettings.from_env({})
        self.assertFalse(settings.is_test)
        self.assertEqual(settings.bot_kwargs(), {})

    def test_test_environment_uses_official_test_bot_api_paths(self):
        settings = TelegramRuntimeSettings.from_env(environment_values())
        self.assertTrue(settings.is_test)
        self.assertEqual(
            settings.bot_api_base_url,
            "https://api.telegram.org/bot{token}/test",
        )
        self.assertEqual(
            settings.bot_file_base_url,
            "https://api.telegram.org/file/bot{token}/test",
        )
        builder = MagicMock()
        builder.base_url.return_value = builder
        builder.base_file_url.return_value = builder
        self.assertIs(settings.configure_builder(builder), builder)
        builder.base_url.assert_called_once_with(settings.bot_api_base_url)
        builder.base_file_url.assert_called_once_with(settings.bot_file_base_url)

    def test_test_billing_accepts_only_isolated_disabled_ai_runtime(self):
        values = environment_values()
        settings = TelegramRuntimeSettings.from_env(values)
        settings.validate_billing_process(
            values,
            billing_enabled=True,
            terms_version="stars-test-2026-08-07",
        )

    def test_test_billing_rejects_production_database(self):
        values = environment_values(
            DATABASE_URL="postgresql+psycopg://pirajoke@/mydictionary?host=/tmp"
        )
        settings = TelegramRuntimeSettings.from_env(values)
        with self.assertRaisesRegex(
            TelegramRuntimeConfigurationError, "isolated database"
        ):
            settings.validate_billing_process(
                values,
                billing_enabled=True,
                terms_version="stars-test-2026-08-07",
            )

    def test_test_billing_rejects_extra_users_and_provider_activation(self):
        for overrides, message in (
            ({"ALLOWED_USER_IDS": "7001,7002"}, "only TELEGRAM_TEST_USER_ID"),
            ({"AI_TUTOR_ENABLED": "true"}, "providers to remain disabled"),
            ({"VOICE_TUTOR_ENABLED": "true"}, "providers to remain disabled"),
            ({"BOT_ACCESS_MODE": "pilot"}, "BOT_ACCESS_MODE=allowlist"),
        ):
            with self.subTest(overrides=overrides):
                values = environment_values(**overrides)
                settings = TelegramRuntimeSettings.from_env(values)
                with self.assertRaisesRegex(
                    TelegramRuntimeConfigurationError, message
                ):
                    settings.validate_billing_process(
                        values,
                        billing_enabled=True,
                        terms_version="stars-test-2026-08-07",
                    )

    def test_test_billing_rejects_production_terms_and_data_dir(self):
        values = environment_values()
        settings = TelegramRuntimeSettings.from_env(values)
        with self.assertRaisesRegex(
            TelegramRuntimeConfigurationError, "stars-test"
        ):
            settings.validate_billing_process(
                values,
                billing_enabled=True,
                terms_version="stars-production-1",
            )
        changed = environment_values(DATA_DIR="/private/tmp/other")
        settings = TelegramRuntimeSettings.from_env(changed)
        with self.assertRaisesRegex(
            TelegramRuntimeConfigurationError, "TELEGRAM_TEST_DATA_DIR"
        ):
            settings.validate_billing_process(
                changed,
                billing_enabled=True,
                terms_version="stars-test-2026-08-07",
            )

    def test_production_billing_still_requires_ai(self):
        settings = TelegramRuntimeSettings.from_env({})
        with self.assertRaisesRegex(
            TelegramRuntimeConfigurationError, "AI_TUTOR_ENABLED"
        ):
            settings.validate_billing_process(
                {"AI_TUTOR_ENABLED": "false"},
                billing_enabled=True,
                terms_version="production-1",
            )


if __name__ == "__main__":
    unittest.main()
