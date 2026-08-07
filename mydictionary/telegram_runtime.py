"""Fail-closed Telegram production and dedicated-test runtime binding."""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import re
from typing import Any, Mapping

from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError


SAFE_IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
SAFE_DATABASE_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]{2,62}$")


class TelegramRuntimeConfigurationError(RuntimeError):
    """Raised when Telegram production and test resources could be mixed."""


def _boolean(value: str, name: str) -> bool:
    normalized = str(value).strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off", ""}:
        return False
    raise TelegramRuntimeConfigurationError(f"{name} must be a boolean")


def _user_ids(values: Mapping[str, str]) -> set[int]:
    raw_values = [values.get("ALLOWED_USER_ID", "")]
    raw_values.extend(values.get("ALLOWED_USER_IDS", "").split(","))
    try:
        return {int(value.strip()) for value in raw_values if value.strip()}
    except ValueError as exc:
        raise TelegramRuntimeConfigurationError(
            "Telegram allowlist must contain numeric user IDs"
        ) from exc


@dataclass(frozen=True)
class TelegramRuntimeSettings:
    environment: str = "production"
    test_run_id: str | None = None
    test_user_id: int | None = None
    test_database_name: str | None = None
    test_data_dir: Path | None = None
    token_from_environment: bool = False

    @property
    def is_test(self) -> bool:
        return self.environment == "test"

    @property
    def bot_api_base_url(self) -> str:
        if self.is_test:
            return "https://api.telegram.org/bot{token}/test"
        return "https://api.telegram.org/bot"

    @property
    def bot_file_base_url(self) -> str:
        if self.is_test:
            return "https://api.telegram.org/file/bot{token}/test"
        return "https://api.telegram.org/file/bot"

    def configure_builder(self, builder: Any) -> Any:
        if not self.is_test:
            return builder
        return builder.base_url(self.bot_api_base_url).base_file_url(
            self.bot_file_base_url
        )

    def bot_kwargs(self) -> dict[str, str]:
        if not self.is_test:
            return {}
        return {
            "base_url": self.bot_api_base_url,
            "base_file_url": self.bot_file_base_url,
        }

    @classmethod
    def from_env(
        cls, values: Mapping[str, str] | None = None
    ) -> "TelegramRuntimeSettings":
        env = values if values is not None else os.environ
        environment = env.get("TELEGRAM_API_ENVIRONMENT", "production").strip().lower()
        if environment not in {"production", "test"}:
            raise TelegramRuntimeConfigurationError(
                "TELEGRAM_API_ENVIRONMENT must be production or test"
            )
        if environment == "production":
            return cls(
                environment=environment,
                token_from_environment=bool(env.get("BOT_TOKEN", "").strip()),
            )

        run_id = env.get("TELEGRAM_TEST_RUN_ID", "").strip()
        if not SAFE_IDENTIFIER_RE.fullmatch(run_id):
            raise TelegramRuntimeConfigurationError(
                "Test Telegram runtime requires a safe TELEGRAM_TEST_RUN_ID"
            )
        user_id_raw = env.get("TELEGRAM_TEST_USER_ID", "").strip()
        try:
            user_id = int(user_id_raw)
        except ValueError as exc:
            raise TelegramRuntimeConfigurationError(
                "Test Telegram runtime requires TELEGRAM_TEST_USER_ID"
            ) from exc
        if user_id <= 0:
            raise TelegramRuntimeConfigurationError(
                "TELEGRAM_TEST_USER_ID must be positive"
            )
        database_name = env.get("TELEGRAM_TEST_DATABASE_NAME", "").strip()
        if not SAFE_DATABASE_RE.fullmatch(database_name):
            raise TelegramRuntimeConfigurationError(
                "Test Telegram runtime requires a safe TELEGRAM_TEST_DATABASE_NAME"
            )
        data_dir_raw = env.get("TELEGRAM_TEST_DATA_DIR", "").strip()
        data_dir = Path(data_dir_raw).expanduser()
        if not data_dir_raw or not data_dir.is_absolute():
            raise TelegramRuntimeConfigurationError(
                "TELEGRAM_TEST_DATA_DIR must be an absolute path"
            )
        return cls(
            environment=environment,
            test_run_id=run_id,
            test_user_id=user_id,
            test_database_name=database_name,
            test_data_dir=data_dir.resolve(),
            token_from_environment=bool(env.get("BOT_TOKEN", "").strip()),
        )

    def validate_billing_process(
        self,
        values: Mapping[str, str] | None = None,
        *,
        billing_enabled: bool,
        terms_version: str,
    ) -> None:
        env = values if values is not None else os.environ
        ai_enabled = _boolean(
            env.get("AI_TUTOR_ENABLED", "false"), "AI_TUTOR_ENABLED"
        )
        voice_enabled = _boolean(
            env.get("VOICE_TUTOR_ENABLED", "false"), "VOICE_TUTOR_ENABLED"
        )
        if not self.is_test:
            if billing_enabled and not ai_enabled:
                raise TelegramRuntimeConfigurationError(
                    "Production Stars checkout requires AI_TUTOR_ENABLED=true"
                )
            return

        if not self.token_from_environment:
            raise TelegramRuntimeConfigurationError(
                "Test Telegram runtime requires a dedicated BOT_TOKEN environment value"
            )
        if env.get("BOT_ACCESS_MODE", "allowlist").strip().lower() != "allowlist":
            raise TelegramRuntimeConfigurationError(
                "Test Telegram runtime requires BOT_ACCESS_MODE=allowlist"
            )
        if _user_ids(env) != {self.test_user_id}:
            raise TelegramRuntimeConfigurationError(
                "Test Telegram runtime must allowlist only TELEGRAM_TEST_USER_ID"
            )
        if not billing_enabled:
            raise TelegramRuntimeConfigurationError(
                "Test Telegram runtime requires TELEGRAM_STARS_ENABLED=true"
            )
        if ai_enabled or voice_enabled:
            raise TelegramRuntimeConfigurationError(
                "Test Stars runtime requires AI and voice providers to remain disabled"
            )
        if not str(terms_version).startswith("stars-test-"):
            raise TelegramRuntimeConfigurationError(
                "Test Stars runtime requires a stars-test-* terms version"
            )

        database_url = env.get("DATABASE_URL", "").strip()
        try:
            database = make_url(database_url).database if database_url else None
        except ArgumentError as exc:
            raise TelegramRuntimeConfigurationError(
                "Test Telegram runtime DATABASE_URL is invalid"
            ) from exc
        if database != self.test_database_name or database == "mydictionary":
            raise TelegramRuntimeConfigurationError(
                "Test Telegram runtime must use its exact isolated database"
            )

        configured_data_dir = Path(env.get("DATA_DIR", "")).expanduser()
        if (
            not env.get("DATA_DIR", "").strip()
            or not configured_data_dir.is_absolute()
            or configured_data_dir.resolve() != self.test_data_dir
        ):
            raise TelegramRuntimeConfigurationError(
                "Test Telegram runtime DATA_DIR must equal TELEGRAM_TEST_DATA_DIR"
            )

    def safe_summary(self) -> dict[str, str | bool]:
        return {
            "telegram_environment": self.environment,
            "test_run_id": self.test_run_id or "",
            "test_database_name": self.test_database_name or "",
            "dedicated_token_configured": self.token_from_environment,
            "bot_api_path": "/test" if self.is_test else "/production",
        }
