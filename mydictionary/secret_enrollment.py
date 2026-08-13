"""Fail-closed, one-time enrollment and loading of provider credentials."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import os
from pathlib import Path
import re
import stat
from typing import Mapping


OPENAI_PROJECT_KEY_RE = re.compile(r"sk-[A-Za-z0-9_-]{16,508}")
GROQ_PROJECT_KEY_RE = re.compile(r"gsk_[A-Za-z0-9_-]{16,508}")
TRUE_VALUES = {"1", "true", "yes", "on"}
FALSE_VALUES = {"0", "false", "no", "off", ""}
MAX_SECRET_BYTES = 1024


@dataclass(frozen=True)
class _ProviderSecret:
    provider: str
    display_name: str
    enrollment_prefix: str
    direct_setting: str
    file_setting: str
    pattern: re.Pattern[str]


_PROVIDERS = {
    "openai": _ProviderSecret(
        provider="openai",
        display_name="OpenAI",
        enrollment_prefix="AI_KEY_ENROLLMENT",
        direct_setting="OPENAI_API_KEY",
        file_setting="OPENAI_API_KEY_FILE",
        pattern=OPENAI_PROJECT_KEY_RE,
    ),
    "groq": _ProviderSecret(
        provider="groq",
        display_name="Groq",
        enrollment_prefix="GROQ_KEY_ENROLLMENT",
        direct_setting="GROQ_API_KEY",
        file_setting="GROQ_API_KEY_FILE",
        pattern=GROQ_PROJECT_KEY_RE,
    ),
}


class SecretEnrollmentError(RuntimeError):
    """Raised when enrollment or credential loading is unsafe."""


def _provider(provider: str) -> _ProviderSecret:
    try:
        return _PROVIDERS[str(provider).strip().lower()]
    except KeyError as exc:
        raise SecretEnrollmentError("Unsupported credential provider") from exc


def _parse_enabled(value: object, *, label: str) -> bool:
    normalized = str(value or "").strip().lower()
    if normalized in TRUE_VALUES:
        return True
    if normalized in FALSE_VALUES:
        return False
    raise SecretEnrollmentError(f"{label} key enrollment flag must be a boolean")


def _parse_expiry(value: object, *, label: str) -> datetime:
    normalized = str(value or "").strip()
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise SecretEnrollmentError(
            f"{label} key enrollment expiry must use ISO 8601"
        ) from exc
    if parsed.tzinfo is None:
        raise SecretEnrollmentError(
            f"{label} key enrollment expiry must include timezone"
        )
    return parsed.astimezone(timezone.utc)


def _validate_value(value: str, provider: _ProviderSecret) -> str:
    if value != value.strip() or not provider.pattern.fullmatch(value):
        raise SecretEnrollmentError(
            f"{provider.display_name} project key format is invalid"
        )
    return value


def _validate_file_metadata(
    metadata: os.stat_result,
    *,
    provider: _ProviderSecret,
) -> None:
    label = provider.display_name
    if not stat.S_ISREG(metadata.st_mode):
        raise SecretEnrollmentError(f"{label} key file must be a regular file")
    if metadata.st_uid != os.geteuid():
        raise SecretEnrollmentError(f"{label} key file must be owned by this user")
    if stat.S_IMODE(metadata.st_mode) & 0o077:
        raise SecretEnrollmentError(f"{label} key file permissions are unsafe")
    if metadata.st_size <= 0 or metadata.st_size > MAX_SECRET_BYTES:
        raise SecretEnrollmentError(f"{label} key file size is invalid")


def load_provider_api_key(
    values: Mapping[str, object],
    *,
    provider: str,
) -> str | None:
    """Load one provider key from a direct value or a private regular file."""

    configured = _provider(provider)
    direct = str(values.get(configured.direct_setting) or "")
    raw_file = str(values.get(configured.file_setting) or "").strip()
    if direct and raw_file:
        raise SecretEnrollmentError(
            f"{configured.direct_setting} and {configured.file_setting} "
            "are mutually exclusive"
        )
    if direct:
        return _validate_value(direct, configured)
    if not raw_file:
        return None

    key_path = Path(raw_file).expanduser()
    if not key_path.is_absolute():
        raise SecretEnrollmentError(
            f"{configured.file_setting} must be an absolute path"
        )
    try:
        before = key_path.lstat()
    except OSError as exc:
        raise SecretEnrollmentError(
            f"{configured.display_name} key file is unavailable"
        ) from exc
    _validate_file_metadata(before, provider=configured)

    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(key_path, flags)
    except OSError as exc:
        raise SecretEnrollmentError(
            f"{configured.display_name} key file must be a regular file"
        ) from exc
    try:
        after = os.fstat(descriptor)
        _validate_file_metadata(after, provider=configured)
        if (before.st_dev, before.st_ino) != (after.st_dev, after.st_ino):
            raise SecretEnrollmentError(
                f"{configured.display_name} key file changed while opening"
            )
        payload = os.read(descriptor, MAX_SECRET_BYTES + 1)
    finally:
        os.close(descriptor)
    if len(payload) > MAX_SECRET_BYTES:
        raise SecretEnrollmentError(
            f"{configured.display_name} key file size is invalid"
        )
    try:
        value = payload.decode("ascii")
    except UnicodeDecodeError as exc:
        raise SecretEnrollmentError(
            f"{configured.display_name} project key format is invalid"
        ) from exc
    return _validate_value(value, configured)


@dataclass(frozen=True)
class SecretEnrollmentSettings:
    enabled: bool
    destination: Path | None = None
    expires_at: datetime | None = None
    provider: str = "openai"

    @classmethod
    def from_mapping(
        cls,
        values: Mapping[str, object],
        *,
        now: datetime | None = None,
        allowed_directory: Path | None = None,
        provider: str = "openai",
    ) -> "SecretEnrollmentSettings":
        configured = _provider(provider)
        prefix = configured.enrollment_prefix
        enabled = _parse_enabled(
            values.get(f"{prefix}_ENABLED", "false"),
            label="AI" if configured.provider == "openai" else configured.display_name,
        )
        if not enabled:
            return cls(enabled=False, provider=configured.provider)
        raw_path = str(values.get(f"{prefix}_PATH") or "").strip()
        if not raw_path:
            raise SecretEnrollmentError(
                f"{configured.display_name} key enrollment path is required"
            )
        destination = Path(raw_path).expanduser()
        if not destination.is_absolute():
            raise SecretEnrollmentError(
                f"{configured.display_name} key enrollment path must be absolute"
            )
        if (
            allowed_directory is not None
            and destination.parent.resolve()
            != Path(allowed_directory).expanduser().resolve()
        ):
            raise SecretEnrollmentError(
                f"{configured.display_name} key enrollment path must stay "
                "in local-config"
            )
        expires_at = _parse_expiry(
            values.get(f"{prefix}_EXPIRES_AT"),
            label="AI" if configured.provider == "openai" else configured.display_name,
        )
        current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
        if expires_at > current + timedelta(hours=1):
            raise SecretEnrollmentError(
                f"{configured.display_name} key enrollment window cannot "
                "exceed one hour"
            )
        return cls(
            enabled=True,
            destination=destination,
            expires_at=expires_at,
            provider=configured.provider,
        )

    def status(self, *, now: datetime | None = None) -> str:
        if not self.enabled:
            return "disabled"
        if self.destination is None or self.expires_at is None:
            return "disabled"
        if self.destination.exists() or self.destination.is_symlink():
            return "consumed"
        current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
        if current >= self.expires_at:
            return "expired"
        return "ready"

    def enroll(self, value: str, *, now: datetime | None = None) -> str:
        configured = _provider(self.provider)
        state = self.status(now=now)
        if state != "ready":
            raise SecretEnrollmentError(
                f"{configured.display_name} key enrollment is {state}"
            )
        _validate_value(value, configured)
        destination = self.destination
        if destination is None:
            raise SecretEnrollmentError(
                f"{configured.display_name} key enrollment is disabled"
            )
        parent = destination.parent
        if not parent.is_dir() or parent.is_symlink():
            raise SecretEnrollmentError(
                f"{configured.display_name} key enrollment directory is unavailable"
            )
        if parent.stat().st_mode & 0o022:
            raise SecretEnrollmentError(
                f"{configured.display_name} key enrollment directory must not "
                "be group or world writable"
            )
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        flags |= getattr(os, "O_CLOEXEC", 0)
        flags |= getattr(os, "O_NOFOLLOW", 0)
        try:
            descriptor = os.open(destination, flags, 0o600)
        except FileExistsError as exc:
            raise SecretEnrollmentError(
                f"{configured.display_name} key enrollment is consumed"
            ) from exc
        try:
            with os.fdopen(descriptor, "wb") as secret_file:
                secret_file.write(value.encode("ascii"))
                secret_file.flush()
                os.fsync(secret_file.fileno())
        except BaseException:
            # A partial file intentionally consumes the one-time window.
            raise
        if destination.stat().st_mode & 0o077:
            raise SecretEnrollmentError(
                f"{configured.display_name} key file permissions are unsafe"
            )
        return hashlib.sha256(value.encode("ascii")).hexdigest()[:12]
