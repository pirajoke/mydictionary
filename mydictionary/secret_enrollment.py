"""Fail-closed, one-time enrollment for a short-lived provider credential."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import os
from pathlib import Path
import re
from typing import Mapping


OPENAI_PROJECT_KEY_RE = re.compile(r"sk-[A-Za-z0-9_-]{16,508}")
TRUE_VALUES = {"1", "true", "yes", "on"}
FALSE_VALUES = {"0", "false", "no", "off", ""}


class SecretEnrollmentError(RuntimeError):
    """Raised when enrollment is unavailable or a credential is invalid."""


def _parse_enabled(value: object) -> bool:
    normalized = str(value or "").strip().lower()
    if normalized in TRUE_VALUES:
        return True
    if normalized in FALSE_VALUES:
        return False
    raise SecretEnrollmentError("AI key enrollment flag must be a boolean")


def _parse_expiry(value: object) -> datetime:
    normalized = str(value or "").strip()
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise SecretEnrollmentError(
            "AI key enrollment expiry must use ISO 8601"
        ) from exc
    if parsed.tzinfo is None:
        raise SecretEnrollmentError("AI key enrollment expiry must include timezone")
    return parsed.astimezone(timezone.utc)


@dataclass(frozen=True)
class SecretEnrollmentSettings:
    enabled: bool
    destination: Path | None = None
    expires_at: datetime | None = None

    @classmethod
    def from_mapping(
        cls,
        values: Mapping[str, object],
        *,
        now: datetime | None = None,
        allowed_directory: Path | None = None,
    ) -> "SecretEnrollmentSettings":
        enabled = _parse_enabled(values.get("AI_KEY_ENROLLMENT_ENABLED", "false"))
        if not enabled:
            return cls(enabled=False)
        raw_path = str(values.get("AI_KEY_ENROLLMENT_PATH") or "").strip()
        if not raw_path:
            raise SecretEnrollmentError("AI key enrollment path is required")
        destination = Path(raw_path).expanduser()
        if not destination.is_absolute():
            raise SecretEnrollmentError("AI key enrollment path must be absolute")
        if (
            allowed_directory is not None
            and destination.parent.resolve()
            != Path(allowed_directory).expanduser().resolve()
        ):
            raise SecretEnrollmentError(
                "AI key enrollment path must stay in local-config"
            )
        expires_at = _parse_expiry(values.get("AI_KEY_ENROLLMENT_EXPIRES_AT"))
        current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
        if expires_at > current + timedelta(hours=1):
            raise SecretEnrollmentError(
                "AI key enrollment window cannot exceed one hour"
            )
        return cls(
            enabled=True,
            destination=destination,
            expires_at=expires_at,
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
        state = self.status(now=now)
        if state != "ready":
            raise SecretEnrollmentError(f"AI key enrollment is {state}")
        if value != value.strip() or not OPENAI_PROJECT_KEY_RE.fullmatch(value):
            raise SecretEnrollmentError("OpenAI project key format is invalid")
        destination = self.destination
        if destination is None:
            raise SecretEnrollmentError("AI key enrollment is disabled")
        parent = destination.parent
        if not parent.is_dir() or parent.is_symlink():
            raise SecretEnrollmentError(
                "AI key enrollment directory is unavailable"
            )
        if parent.stat().st_mode & 0o022:
            raise SecretEnrollmentError(
                "AI key enrollment directory must not be group or world writable"
            )
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        flags |= getattr(os, "O_CLOEXEC", 0)
        flags |= getattr(os, "O_NOFOLLOW", 0)
        try:
            descriptor = os.open(destination, flags, 0o600)
        except FileExistsError as exc:
            raise SecretEnrollmentError("AI key enrollment is consumed") from exc
        try:
            with os.fdopen(descriptor, "wb") as secret_file:
                secret_file.write(value.encode("ascii"))
                secret_file.flush()
                os.fsync(secret_file.fileno())
        except BaseException:
            # A partial file intentionally consumes the one-time window.
            raise
        if destination.stat().st_mode & 0o077:
            raise SecretEnrollmentError("AI key file permissions are unsafe")
        return hashlib.sha256(value.encode("ascii")).hexdigest()[:12]
