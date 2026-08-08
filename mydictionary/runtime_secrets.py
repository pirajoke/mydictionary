"""Owner-only runtime secret files used without exposing values to launchd."""

from __future__ import annotations

import json
import os
from pathlib import Path
import re
import stat
from typing import Mapping


TELEGRAM_BOT_TOKEN_RE = re.compile(r"^[0-9]{5,12}:[A-Za-z0-9_-]{20,128}$")


class RuntimeSecretError(RuntimeError):
    """Raised when a runtime secret file is missing or unsafe."""


def _private_regular_file(raw_path: object, *, label: str) -> Path:
    value = str(raw_path or "").strip()
    path = Path(value).expanduser()
    if not value or not path.is_absolute():
        raise RuntimeSecretError(f"{label} path must be absolute")
    if path.is_symlink():
        raise RuntimeSecretError(f"{label} file cannot be a symlink")
    return path


def _read_private_bytes(path: Path, *, label: str) -> bytes:
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise RuntimeSecretError(f"{label} file cannot be opened safely") from exc
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            raise RuntimeSecretError(f"{label} path must be a regular file")
        if stat.S_IMODE(metadata.st_mode) & 0o077:
            raise RuntimeSecretError(f"{label} file permissions must be 0600")
        if hasattr(os, "getuid") and metadata.st_uid != os.getuid():
            raise RuntimeSecretError(
                f"{label} file must be owned by the service user"
            )
        with os.fdopen(descriptor, "rb") as handle:
            descriptor = -1
            return handle.read(16 * 1024 + 1)
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def read_private_json(raw_path: object, *, label: str) -> dict[str, object]:
    path = _private_regular_file(raw_path, label=label)
    payload = _read_private_bytes(path, label=label)
    if len(payload) > 16 * 1024:
        raise RuntimeSecretError(f"{label} file is too large")
    try:
        value = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeSecretError(f"{label} file must contain valid JSON") from exc
    if not isinstance(value, dict):
        raise RuntimeSecretError(f"{label} file must contain an object")
    return value


def validate_telegram_bot_token(value: object) -> str:
    token = str(value or "")
    if token != token.strip() or not TELEGRAM_BOT_TOKEN_RE.fullmatch(token):
        raise RuntimeSecretError("Telegram bot token format is invalid")
    return token


def load_bot_token_file(values: Mapping[str, str]) -> dict[str, str]:
    """Return a copied environment with BOT_TOKEN loaded from BOT_TOKEN_FILE."""

    result = dict(values)
    raw_path = str(result.get("BOT_TOKEN_FILE") or "").strip()
    if not raw_path:
        return result
    if str(result.get("BOT_TOKEN") or "").strip():
        raise RuntimeSecretError(
            "BOT_TOKEN and BOT_TOKEN_FILE cannot both be configured"
        )
    path = _private_regular_file(raw_path, label="Telegram bot token")
    payload = _read_private_bytes(path, label="Telegram bot token")
    if len(payload) > 1024:
        raise RuntimeSecretError("Telegram bot token file is too large")
    try:
        token = payload.decode("ascii")
    except UnicodeDecodeError as exc:
        raise RuntimeSecretError("Telegram bot token must be ASCII") from exc
    if token.endswith("\n"):
        token = token[:-1]
    result["BOT_TOKEN"] = validate_telegram_bot_token(token)
    return result


def load_telegram_test_credentials_file(
    values: Mapping[str, str],
) -> dict[str, str]:
    """Load one dedicated test bot token and user ID from a private bundle."""

    result = dict(values)
    raw_path = str(result.get("TELEGRAM_TEST_CREDENTIALS_FILE") or "").strip()
    if not raw_path:
        return result
    if str(result.get("BOT_TOKEN") or "").strip() or str(
        result.get("TELEGRAM_TEST_USER_ID") or ""
    ).strip():
        raise RuntimeSecretError(
            "Test credential file cannot be mixed with inline Telegram credentials"
        )
    payload = read_private_json(raw_path, label="Telegram test credentials")
    if set(payload) != {"bot_token", "test_user_id"}:
        raise RuntimeSecretError(
            "Telegram test credentials must contain only bot_token and test_user_id"
        )
    token = validate_telegram_bot_token(payload["bot_token"])
    user_id = payload["test_user_id"]
    try:
        if isinstance(user_id, bool):
            raise ValueError
        parsed_user_id = int(user_id)
        if parsed_user_id <= 0 or str(parsed_user_id) != str(user_id):
            raise ValueError
    except (TypeError, ValueError) as exc:
        raise RuntimeSecretError(
            "Telegram test credentials require a positive numeric test_user_id"
        ) from exc
    result["BOT_TOKEN"] = token
    result["TELEGRAM_TEST_USER_ID"] = str(parsed_user_id)
    return result


def load_runtime_secret_files(values: Mapping[str, str]) -> dict[str, str]:
    result = load_bot_token_file(values)
    return load_telegram_test_credentials_file(result)
