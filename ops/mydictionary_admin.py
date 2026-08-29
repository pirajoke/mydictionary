#!/usr/bin/env python3
"""Start the admin server from the active MY DICTIONARY release."""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
import re
import stat

from mydictionary.miniapp import MiniAppConfigurationError, MiniAppSettings


SHA_PATTERN = re.compile(r"^[0-9a-f]{40}$")
TRUE_VALUES = {"1", "true", "yes", "on"}
FALSE_VALUES = {"0", "false", "no", "off"}
GROQ_PROJECT_KEY_RE = re.compile(r"gsk_[A-Za-z0-9_-]{16,508}")


def required(values: dict[str, str], name: str) -> str:
    value = str(values.get(name) or "").strip()
    if not value:
        raise RuntimeError(f"Missing required setting: {name}")
    return value


def required_secret(values: dict[str, object], name: str) -> str:
    raw_value = values.get(name)
    if not isinstance(raw_value, str):
        raise RuntimeError(f"Missing admin secret: {name}")
    value = raw_value.strip()
    if not value:
        raise RuntimeError(f"Missing admin secret: {name}")
    return value


def active_release(current: Path) -> Path:
    if not current.is_symlink():
        raise RuntimeError("Current release path must be a symlink")
    release = current.resolve()
    if release.parent != (current.parent / "releases").resolve():
        raise RuntimeError("Current release must stay inside the versioned release tree")
    if not SHA_PATTERN.fullmatch(release.name) or not release.is_dir():
        raise RuntimeError("Current release directory is not a commit SHA")
    return release


def active_release_sha(current: Path) -> str:
    return active_release(current).name


def _groq_file_configured(raw_path: str) -> bool:
    if not raw_path:
        return False
    path = Path(raw_path).expanduser()
    if not path.is_absolute():
        raise RuntimeError("GROQ_API_KEY_FILE must be an absolute path")
    try:
        metadata = path.lstat()
    except FileNotFoundError:
        return False
    if not stat.S_ISREG(metadata.st_mode) or path.is_symlink():
        raise RuntimeError("Groq key file must be a regular file")
    if metadata.st_uid != os.geteuid():
        raise RuntimeError("Groq key file must be owned by this user")
    if stat.S_IMODE(metadata.st_mode) & 0o077:
        raise RuntimeError("Groq key file permissions are unsafe")
    if metadata.st_size <= 0 or metadata.st_size > 1024:
        raise RuntimeError("Groq key file size is invalid")
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise RuntimeError("Groq key file is unreadable") from exc
    try:
        opened = os.fstat(descriptor)
        if not stat.S_ISREG(opened.st_mode):
            raise RuntimeError("Groq key file must be a regular file")
        if opened.st_uid != os.geteuid():
            raise RuntimeError("Groq key file must be owned by this user")
        if stat.S_IMODE(opened.st_mode) & 0o077:
            raise RuntimeError("Groq key file permissions are unsafe")
        if opened.st_size <= 0 or opened.st_size > 1024:
            raise RuntimeError("Groq key file size is invalid")
        if (metadata.st_dev, metadata.st_ino) != (opened.st_dev, opened.st_ino):
            raise RuntimeError("Groq key file changed while opening")
        payload = os.read(descriptor, 1025)
    finally:
        os.close(descriptor)
    try:
        value = payload.decode("ascii")
    except UnicodeDecodeError as exc:
        raise RuntimeError("Groq key file is unreadable") from exc
    if not GROQ_PROJECT_KEY_RE.fullmatch(value):
        raise RuntimeError("Groq key file format is invalid")
    return True


def _validate_bounded_enrollment(
    environment: dict[str, str],
    *,
    prefix: str,
    label: str,
    app_root: Path,
) -> None:
    enabled_name = f"{prefix}_ENABLED"
    enrollment_enabled = environment[enabled_name].lower()
    if enrollment_enabled not in TRUE_VALUES | FALSE_VALUES:
        raise RuntimeError(f"{enabled_name} must be a boolean")
    if enrollment_enabled not in TRUE_VALUES:
        return
    raw_target = required(environment, f"{prefix}_PATH")
    target = Path(raw_target).expanduser()
    if not target.is_absolute():
        raise RuntimeError(f"{label} key enrollment path must be absolute")
    local_config = (app_root / "local-config").resolve()
    if not local_config.is_dir() or local_config.is_symlink():
        raise RuntimeError(f"{label} key enrollment directory is unavailable")
    if stat.S_IMODE(local_config.stat().st_mode) & 0o022:
        raise RuntimeError(
            f"{label} key enrollment directory permissions are unsafe"
        )
    if target.parent.resolve() != local_config:
        raise RuntimeError(
            f"{label} key enrollment path must stay in local-config"
        )
    raw_expiry = required(environment, f"{prefix}_EXPIRES_AT")
    normalized_expiry = (
        raw_expiry[:-1] + "+00:00" if raw_expiry.endswith("Z") else raw_expiry
    )
    try:
        expires_at = datetime.fromisoformat(normalized_expiry)
    except ValueError as exc:
        raise RuntimeError(
            f"{label} key enrollment expiry must use ISO 8601"
        ) from exc
    if expires_at.tzinfo is None:
        raise RuntimeError(
            f"{label} key enrollment expiry must include timezone"
        )
    if expires_at.astimezone(timezone.utc) > datetime.now(
        timezone.utc
    ) + timedelta(hours=1):
        raise RuntimeError(
            f"{label} key enrollment window cannot exceed one hour"
        )


def _validate_stars_launch_enrollment(
    environment: dict[str, str], *, app_root: Path
) -> None:
    enabled = environment["STARS_LAUNCH_ENROLLMENT_ENABLED"].lower()
    if enabled not in TRUE_VALUES | FALSE_VALUES:
        raise RuntimeError("STARS_LAUNCH_ENROLLMENT_ENABLED must be a boolean")
    if enabled not in TRUE_VALUES:
        return
    local_config = (app_root / "local-config").resolve()
    if not local_config.is_dir() or local_config.is_symlink():
        raise RuntimeError("Stars launch enrollment directory is unavailable")
    if stat.S_IMODE(local_config.stat().st_mode) & 0o022:
        raise RuntimeError("Stars launch enrollment directory permissions are unsafe")
    targets = []
    for name in (
        "STARS_LAUNCH_PROFILE_PATH",
        "STARS_TEST_CREDENTIALS_PATH",
        "STARS_TEST_RECEIPT_PATH",
    ):
        target = Path(required(environment, name)).expanduser()
        if not target.is_absolute():
            raise RuntimeError(f"{name} must be absolute")
        if target.parent.resolve() != local_config:
            raise RuntimeError(f"{name} must stay in local-config")
        targets.append(target)
    if len(set(targets)) != len(targets):
        raise RuntimeError("Stars launch files require separate destinations")
    raw_expiry = required(environment, "STARS_LAUNCH_ENROLLMENT_EXPIRES_AT")
    normalized = (
        raw_expiry[:-1] + "+00:00" if raw_expiry.endswith("Z") else raw_expiry
    )
    try:
        expires_at = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise RuntimeError(
            "Stars launch enrollment expiry must use ISO 8601"
        ) from exc
    if expires_at.tzinfo is None:
        raise RuntimeError("Stars launch enrollment expiry must include timezone")
    if expires_at.astimezone(timezone.utc) > datetime.now(
        timezone.utc
    ) + timedelta(hours=1):
        raise RuntimeError("Stars launch enrollment window cannot exceed one hour")


def build_process(
    values: dict[str, str] | None = None,
) -> tuple[Path, list[str], dict[str, str], Path]:
    source = dict(os.environ if values is None else values)
    app_root = Path(required(source, "MYDICTIONARY_APP_ROOT")).expanduser().resolve()
    current = app_root / "current"
    secrets_path = Path(
        source.get("MYDICTIONARY_ADMIN_SECRETS", "").strip()
        or app_root / "admin-secrets.json"
    ).expanduser().resolve()
    secrets = json.loads(secrets_path.read_text(encoding="utf-8"))
    if not isinstance(secrets, dict):
        raise RuntimeError("Admin secrets file must contain an object")
    if stat.S_IMODE(secrets_path.stat().st_mode) & 0o077:
        raise RuntimeError("Admin secrets file must not be group or world readable")
    release = active_release(current)
    release_sha = release.name
    release_python = release / ".venv" / "bin" / "python3"
    if not release_python.is_file():
        raise RuntimeError("Release Python is missing")

    voice_provider = source.get("VOICE_PROVIDER", "openai").strip().lower()
    if voice_provider not in {"openai", "groq"}:
        raise RuntimeError("VOICE_PROVIDER must be openai or groq")
    groq_direct = source.get("GROQ_API_KEY", "")
    groq_file = source.get("GROQ_API_KEY_FILE", "").strip()
    if groq_direct and groq_file:
        raise RuntimeError(
            "GROQ_API_KEY and GROQ_API_KEY_FILE are mutually exclusive"
        )
    if groq_direct and not GROQ_PROJECT_KEY_RE.fullmatch(groq_direct):
        raise RuntimeError("GROQ_API_KEY format is invalid")
    groq_configured = bool(groq_direct) or _groq_file_configured(groq_file)

    environment = {
        key: source[key]
        for key in ("HOME", "PATH", "LANG", "LC_ALL", "TMPDIR")
        if source.get(key)
    }
    database_url = required(source, "DATABASE_URL")
    if not database_url.startswith(
        ("postgres://", "postgresql://", "postgresql+psycopg://")
    ):
        raise RuntimeError("Admin launcher requires PostgreSQL")
    environment.update(
        {
            "PYTHONUNBUFFERED": "1",
            "DATABASE_URL": database_url,
            "DATA_DIR": str(app_root),
            "ADMIN_USERNAME": required_secret(secrets, "username"),
            "ADMIN_PASSWORD_HASH": required_secret(secrets, "password_hash"),
            "ADMIN_SESSION_SECRET": required_secret(secrets, "session_secret"),
            "ADMIN_HOST": source.get("ADMIN_HOST", "127.0.0.1").strip(),
            "ADMIN_PORT": source.get("ADMIN_PORT", "8791").strip(),
            "ADMIN_COOKIE_SECURE": source.get(
                "ADMIN_COOKIE_SECURE", "true"
            ).strip(),
            "MINIAPP_ENABLED": source.get("MINIAPP_ENABLED", "false").strip(),
            "MINIAPP_PUBLIC_URL": source.get("MINIAPP_PUBLIC_URL", "").strip(),
            "MINIAPP_BOT_USERNAME": source.get(
                "MINIAPP_BOT_USERNAME", ""
            ).strip(),
            "MINIAPP_AUTH_MAX_AGE_SECONDS": source.get(
                "MINIAPP_AUTH_MAX_AGE_SECONDS", "300"
            ).strip(),
            "BOT_TOKEN_FILE": source.get("BOT_TOKEN_FILE", "").strip(),
            "AI_TUTOR_ENABLED": source.get("AI_TUTOR_ENABLED", "false").strip(),
            "AI_INITIAL_CREDITS": source.get("AI_INITIAL_CREDITS", "0").strip(),
            "AI_KEY_ENROLLMENT_ENABLED": source.get(
                "AI_KEY_ENROLLMENT_ENABLED", "false"
            ).strip(),
            "GROQ_KEY_ENROLLMENT_ENABLED": source.get(
                "GROQ_KEY_ENROLLMENT_ENABLED", "false"
            ).strip(),
            "STARS_LAUNCH_ENROLLMENT_ENABLED": source.get(
                "STARS_LAUNCH_ENROLLMENT_ENABLED", "false"
            ).strip(),
            "AI_PROVIDER_CONFIGURED": str(
                bool(source.get("OPENAI_API_KEY", "").strip())
            ).lower(),
            "VOICE_TUTOR_ENABLED": source.get(
                "VOICE_TUTOR_ENABLED", "false"
            ).strip(),
            "VOICE_PROVIDER": voice_provider,
            "VOICE_PROVIDER_CONFIGURED": str(
                groq_configured
                if voice_provider == "groq"
                else bool(source.get("OPENAI_API_KEY", "").strip())
            ).lower(),
            "VOICE_TRANSCRIPTION_MODEL": source.get(
                "VOICE_TRANSCRIPTION_MODEL",
                (
                    "whisper-large-v3"
                    if voice_provider == "groq"
                    else "gpt-4o-transcribe"
                ),
            ).strip(),
            "TELEGRAM_STARS_ENABLED": source.get(
                "TELEGRAM_STARS_ENABLED", "false"
            ).strip(),
            "RELEASE_SHA": release_sha,
        }
    )
    for name in (
        "BILLING_PAYLOAD_SECRET",
        "BILLING_SUPPORT_CONTACT",
        "BILLING_SELLER_LEGAL_NAME",
        "BILLING_SELLER_ADDRESS",
        "BILLING_SELLER_EMAIL",
        "BILLING_SELLER_PHONE",
        "BILLING_TERMS_TEXT",
        "BILLING_TERMS_VERSION",
        "BILLING_TERMS_SHA256",
        "BILLING_TERMS_APPROVED",
        "BILLING_ORDER_TTL_SECONDS",
        "BILLING_NET_MICRO_USD_PER_XTR",
        "BILLING_ECONOMICS_REVIEWED_ON",
        "BILLING_ECONOMICS_MAX_AGE_DAYS",
        "BILLING_PRIVATE_CHAT_TOPICS_ENABLED",
        "AI_PROVIDER",
        "AI_MODEL",
        "AI_SERVICE_TIER",
        "AI_CREDITS_PER_REQUEST",
        "AI_INPUT_USD_PER_MILLION",
        "AI_CACHED_INPUT_USD_PER_MILLION",
        "AI_CACHE_WRITE_USD_PER_MILLION",
        "AI_OUTPUT_USD_PER_MILLION",
        "AI_PRICING_REVIEWED_ON",
        "AI_PRICING_MAX_AGE_DAYS",
        "AI_ECONOMICS_SNAPSHOT_PATH",
        "AI_ECONOMICS_SNAPSHOT_ID",
        "AI_ECONOMICS_SNAPSHOT_SHA256",
        "AI_MAX_DAILY_REQUESTS_PER_USER",
        "VOICE_TRANSLATION_MAX_DAILY_REQUESTS_PER_USER",
        "AI_MAX_PREFLIGHT_COST_MICRO_USD_PER_REQUEST",
        "AI_RETROSPECTIVE_BREAKER_MICRO_USD_PER_RESPONSE",
        "AI_MAX_PROJECT_COST_MICRO_USD_PER_DAY",
        "AI_MAX_PROJECT_COST_MICRO_USD_PER_MONTH",
        "AI_MAX_IN_FLIGHT_COST_MICRO_USD",
        "AI_MAX_PROVIDER_INPUT_CHARS",
        "AI_MAX_OUTPUT_TOKENS",
        "AI_METERING_JOURNAL_PATH",
        "AI_KEY_ENROLLMENT_PATH",
        "AI_KEY_ENROLLMENT_EXPIRES_AT",
        "GROQ_API_KEY_FILE",
        "GROQ_KEY_ENROLLMENT_PATH",
        "GROQ_KEY_ENROLLMENT_EXPIRES_AT",
        "STARS_LAUNCH_PROFILE_PATH",
        "STARS_TEST_CREDENTIALS_PATH",
        "STARS_TEST_RECEIPT_PATH",
        "STARS_LAUNCH_ENROLLMENT_EXPIRES_AT",
        "BILLING_LAUNCH_PROFILE_FILE",
        "TELEGRAM_TEST_CREDENTIALS_FILE",
        "STARS_TEST_RECEIPT_FILE",
        "STARS_TEST_RECEIPT_MAX_AGE_DAYS",
        "ADMIN_EMAIL",
        "ADMIN_PUBLIC_URL",
        "ADMIN_GOOGLE_CLIENT_ID",
        "ADMIN_GOOGLE_CLIENT_SECRET_FILE",
        "ADMIN_SMTP_HOST",
        "ADMIN_SMTP_PORT",
        "ADMIN_SMTP_USERNAME",
        "ADMIN_SMTP_PASSWORD_FILE",
        "ADMIN_SMTP_FROM",
        "ADMIN_RESET_TOKEN_TTL_SECONDS",
        "ADMIN_RESET_RATE_LIMIT_ATTEMPTS",
        "AI_RESERVATION_TIMEOUT_SECONDS",
        "VOICE_CONSENT_VERSION",
        "VOICE_PROCESSING_NOTICE",
        "VOICE_GROQ_ZDR_VERIFIED",
        "VOICE_MINIMUM_BILLABLE_SECONDS",
        "VOICE_COST_MICRO_USD_PER_MINUTE",
        "VOICE_CREDITS_PER_REQUEST",
        "VOICE_MAX_AUDIO_BYTES",
        "VOICE_MAX_DURATION_SECONDS",
        "VOICE_SESSION_TTL_MINUTES",
        "VOICE_TRANSCRIPT_RETENTION_DAYS",
        "VOICE_TRANSLATION_ENABLED",
        "VOICE_TRANSLATION_PROVIDER",
        "VOICE_TRANSLATION_MODEL",
        "VOICE_TRANSLATION_SERVICE_TIER",
        "VOICE_TRANSLATION_CONSENT_VERSION",
        "VOICE_TRANSLATION_PROCESSING_NOTICE",
        "VOICE_TRANSLATION_STT_MICRO_USD_PER_MINUTE",
        "VOICE_TRANSLATION_STT_MINIMUM_BILLABLE_SECONDS",
        "VOICE_TRANSLATION_INPUT_USD_PER_MILLION",
        "VOICE_TRANSLATION_OUTPUT_USD_PER_MILLION",
        "VOICE_TRANSLATION_PRICING_REVIEWED_ON",
        "VOICE_TRANSLATION_MAX_PREFLIGHT_COST_MICRO_USD",
        "VOICE_TRANSLATION_STT_CREDITS_PER_REQUEST",
        "VOICE_TRANSLATION_CREDITS_PER_REQUEST",
    ):
        if source.get(name):
            environment[name] = str(source[name]).strip()
    if len(environment["ADMIN_SESSION_SECRET"]) < 32:
        raise RuntimeError("Admin session secret must contain at least 32 characters")
    try:
        MiniAppSettings.from_env(
            {
                name: environment[name]
                for name in (
                    "MINIAPP_ENABLED",
                    "MINIAPP_PUBLIC_URL",
                    "MINIAPP_BOT_USERNAME",
                    "MINIAPP_AUTH_MAX_AGE_SECONDS",
                    "BOT_TOKEN_FILE",
                )
            }
        )
    except MiniAppConfigurationError as exc:
        raise RuntimeError(str(exc)) from exc
    if environment["ADMIN_HOST"] not in {"127.0.0.1", "localhost", "::1"}:
        raise RuntimeError("Admin host must remain loopback")
    if environment["AI_TUTOR_ENABLED"].lower() not in {
        "0",
        "1",
        "false",
        "true",
        "no",
        "yes",
        "off",
        "on",
    }:
        raise RuntimeError("AI_TUTOR_ENABLED must be a boolean")
    _validate_bounded_enrollment(
        environment,
        prefix="AI_KEY_ENROLLMENT",
        label="AI",
        app_root=app_root,
    )
    _validate_bounded_enrollment(
        environment,
        prefix="GROQ_KEY_ENROLLMENT",
        label="Groq",
        app_root=app_root,
    )
    _validate_stars_launch_enrollment(environment, app_root=app_root)
    if environment["VOICE_TUTOR_ENABLED"].lower() not in {
        "0",
        "1",
        "false",
        "true",
        "no",
        "yes",
        "off",
        "on",
    }:
        raise RuntimeError("VOICE_TUTOR_ENABLED must be a boolean")
    if environment["TELEGRAM_STARS_ENABLED"].lower() not in {
        "0",
        "1",
        "false",
        "true",
        "no",
        "yes",
        "off",
        "on",
    }:
        raise RuntimeError("TELEGRAM_STARS_ENABLED must be a boolean")
    if environment["ADMIN_COOKIE_SECURE"].lower() not in {
        "0",
        "1",
        "false",
        "true",
        "no",
        "yes",
        "off",
        "on",
    }:
        raise RuntimeError("ADMIN_COOKIE_SECURE must be a boolean")
    try:
        port = int(environment["ADMIN_PORT"])
    except ValueError as exc:
        raise RuntimeError("ADMIN_PORT must be an integer") from exc
    if not 1024 <= port <= 65535:
        raise RuntimeError("ADMIN_PORT is outside the allowed range")

    arguments = [
        str(release_python),
        "-m",
        "gunicorn",
        "--workers",
        "1",
        "--threads",
        "4",
        "--bind",
        f"{environment['ADMIN_HOST']}:{port}",
        "--access-logfile",
        "-",
        "--error-logfile",
        "-",
        "mydictionary.admin:create_app()",
    ]
    return release_python, arguments, environment, release


def main() -> None:
    executable, arguments, environment, working_directory = build_process()
    os.chdir(working_directory)
    os.execve(str(executable), arguments, environment)


if __name__ == "__main__":
    main()
