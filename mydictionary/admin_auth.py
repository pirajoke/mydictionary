"""Fail-closed settings and provider adapters for admin authentication."""

from __future__ import annotations

from dataclasses import dataclass
from email.message import EmailMessage
import os
from pathlib import Path
import smtplib
import ssl
import stat
from typing import Any, Mapping, Protocol
from urllib.parse import urlparse

import httpx


class ResetMailer(Protocol):
    def send_password_reset(self, *, recipient: str, reset_url: str) -> None: ...


class GoogleHTTPClient(Protocol):
    def post(self, url: str, *, data: Mapping[str, str], timeout: float): ...

    def get(self, url: str, *, params: Mapping[str, str], timeout: float): ...


def _value(config: Mapping[str, Any], name: str) -> str:
    return str(config.get(name) or "").strip()


def _protected_secret(path_value: str, *, label: str) -> str:
    path = Path(path_value).expanduser()
    if not path.is_absolute():
        raise RuntimeError(f"{label} secret file must be absolute")
    try:
        metadata = path.lstat()
    except OSError as exc:
        raise RuntimeError(f"{label} secret file is unavailable") from exc
    if path.is_symlink() or not stat.S_ISREG(metadata.st_mode):
        raise RuntimeError(f"{label} secret file must be a regular file")
    if metadata.st_uid != os.geteuid():
        raise RuntimeError(f"{label} secret file must be owned by this user")
    if stat.S_IMODE(metadata.st_mode) & 0o077:
        raise RuntimeError(f"{label} secret file permissions are unsafe")
    if metadata.st_size <= 0 or metadata.st_size > 1024:
        raise RuntimeError(f"{label} secret file size is invalid")
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise RuntimeError(f"{label} secret file is unreadable") from exc
    try:
        opened = os.fstat(descriptor)
        if not stat.S_ISREG(opened.st_mode):
            raise RuntimeError(f"{label} secret file must be a regular file")
        if opened.st_uid != os.geteuid():
            raise RuntimeError(f"{label} secret file must be owned by this user")
        if stat.S_IMODE(opened.st_mode) & 0o077:
            raise RuntimeError(f"{label} secret file permissions are unsafe")
        if opened.st_size <= 0 or opened.st_size > 1024:
            raise RuntimeError(f"{label} secret file size is invalid")
        if (metadata.st_dev, metadata.st_ino) != (opened.st_dev, opened.st_ino):
            raise RuntimeError(f"{label} secret file changed while opening")
        payload = os.read(descriptor, 1025)
    finally:
        os.close(descriptor)
    try:
        value = payload.decode("utf-8").strip()
    except UnicodeDecodeError as exc:
        raise RuntimeError(f"{label} secret file is unreadable") from exc
    if not value:
        raise RuntimeError(f"{label} secret file is empty")
    return value


def _public_url(config: Mapping[str, Any]) -> str:
    value = _value(config, "ADMIN_PUBLIC_URL")
    parsed = urlparse(value)
    if (
        parsed.scheme != "https"
        or not parsed.netloc
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or parsed.path not in {"", "/"}
    ):
        raise RuntimeError("ADMIN_PUBLIC_URL must be an HTTPS origin")
    return f"https://{parsed.netloc}"


@dataclass(frozen=True)
class SMTPResetMailer:
    host: str
    port: int
    username: str
    password: str
    sender: str

    def send_password_reset(self, *, recipient: str, reset_url: str) -> None:
        message = EmailMessage()
        message["Subject"] = "Сброс пароля Lexi"
        message["From"] = self.sender
        message["To"] = recipient
        message.set_content(
            "Чтобы задать новый пароль администратора, откройте ссылку:\n\n"
            f"{reset_url}\n\nСсылка действует ограниченное время."
        )
        with smtplib.SMTP(self.host, self.port, timeout=10) as client:
            client.starttls(context=ssl.create_default_context())
            client.login(self.username, self.password)
            client.send_message(message)


@dataclass(frozen=True)
class AdminAuthSettings:
    email: str = ""
    public_url: str = ""
    reset_enabled: bool = False
    reset_ttl_seconds: int = 900
    reset_rate_limit_attempts: int = 5
    reset_mailer: ResetMailer | None = None
    google_enabled: bool = False
    google_client_id: str = ""
    google_client_secret: str = ""
    google_http_client: GoogleHTTPClient | None = None
    google_tokeninfo_post: bool = False

    @classmethod
    def from_mapping(cls, config: Mapping[str, Any]) -> "AdminAuthSettings":
        shared_names = ("ADMIN_EMAIL", "ADMIN_PUBLIC_URL")
        reset_names = (
            "ADMIN_SMTP_HOST",
            "ADMIN_SMTP_PORT",
            "ADMIN_SMTP_USERNAME",
            "ADMIN_SMTP_PASSWORD_FILE",
            "ADMIN_SMTP_FROM",
            "ADMIN_RESET_TOKEN_TTL_SECONDS",
            "ADMIN_RESET_RATE_LIMIT_ATTEMPTS",
            "ADMIN_RESET_MAILER",
        )
        google_names = (
            "ADMIN_GOOGLE_CLIENT_ID",
            "ADMIN_GOOGLE_CLIENT_SECRET_FILE",
            "ADMIN_GOOGLE_HTTP_CLIENT",
        )
        shared_present = any(config.get(name) not in (None, "") for name in shared_names)
        reset_present = any(config.get(name) not in (None, "") for name in reset_names)
        google_present = any(config.get(name) not in (None, "") for name in google_names)
        if not shared_present and not reset_present and not google_present:
            return cls()
        if not reset_present and not google_present:
            raise RuntimeError("Admin authentication configuration is incomplete")

        email = _value(config, "ADMIN_EMAIL").casefold()
        if not email or "@" not in email:
            raise RuntimeError("ADMIN_EMAIL is required")
        public_url = _public_url(config)

        reset_mailer: ResetMailer | None = None
        ttl = 900
        attempts = 5
        if reset_present:
            required_reset = {
                name: _value(config, name)
                for name in (
                    "ADMIN_SMTP_HOST",
                    "ADMIN_SMTP_PORT",
                    "ADMIN_SMTP_USERNAME",
                    "ADMIN_SMTP_PASSWORD_FILE",
                    "ADMIN_SMTP_FROM",
                )
            }
            if not all(required_reset.values()):
                raise RuntimeError("Admin SMTP configuration is incomplete")
            try:
                port = int(required_reset["ADMIN_SMTP_PORT"])
                ttl = int(_value(config, "ADMIN_RESET_TOKEN_TTL_SECONDS") or "900")
                attempts = int(
                    _value(config, "ADMIN_RESET_RATE_LIMIT_ATTEMPTS") or "5"
                )
            except ValueError as exc:
                raise RuntimeError("Admin reset settings must be integers") from exc
            if not 1 <= port <= 65535:
                raise RuntimeError("ADMIN_SMTP_PORT is outside the allowed range")
            if not 300 <= ttl <= 3600:
                raise RuntimeError("Admin reset token lifetime is outside the allowed range")
            if not 1 <= attempts <= 20:
                raise RuntimeError("Admin reset rate limit is outside the allowed range")
            smtp_password = _protected_secret(
                required_reset["ADMIN_SMTP_PASSWORD_FILE"], label="SMTP"
            )
            reset_mailer = config.get("ADMIN_RESET_MAILER") or SMTPResetMailer(
                host=required_reset["ADMIN_SMTP_HOST"],
                port=port,
                username=required_reset["ADMIN_SMTP_USERNAME"],
                password=smtp_password,
                sender=required_reset["ADMIN_SMTP_FROM"],
            )

        google_client_id = ""
        google_secret = ""
        google_http_client: GoogleHTTPClient | None = None
        if google_present:
            google_client_id = _value(config, "ADMIN_GOOGLE_CLIENT_ID")
            google_secret_file = _value(config, "ADMIN_GOOGLE_CLIENT_SECRET_FILE")
            if not google_client_id or not google_secret_file:
                raise RuntimeError("Admin Google configuration is incomplete")
            google_secret = _protected_secret(google_secret_file, label="Google")
            injected_http_client = config.get("ADMIN_GOOGLE_HTTP_CLIENT")
            google_http_client = injected_http_client or httpx.Client()

        return cls(
            email=email,
            public_url=public_url,
            reset_enabled=reset_present,
            reset_ttl_seconds=ttl,
            reset_rate_limit_attempts=attempts,
            reset_mailer=reset_mailer,
            google_enabled=google_present,
            google_client_id=google_client_id,
            google_client_secret=google_secret,
            google_http_client=google_http_client,
            google_tokeninfo_post=bool(
                google_present and injected_http_client is None
            ),
        )
