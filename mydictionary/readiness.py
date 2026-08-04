"""Privacy-safe runtime heartbeat shared by the bot and admin service."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import tempfile
from typing import Any, Callable


HEARTBEAT_FILENAME = "bot-heartbeat.json"
HEARTBEAT_SCHEMA_VERSION = 1
DEFAULT_MAX_AGE_SECONDS = 45
HEARTBEAT_STATES = {"starting", "ready", "stopped"}


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def heartbeat_path(data_dir: Path) -> Path:
    configured = os.environ.get("BOT_HEARTBEAT_PATH", "").strip()
    return Path(configured).expanduser() if configured else data_dir / HEARTBEAT_FILENAME


def configured_max_age_seconds() -> int:
    raw_value = os.environ.get(
        "BOT_HEARTBEAT_MAX_AGE_SECONDS", str(DEFAULT_MAX_AGE_SECONDS)
    )
    try:
        value = int(raw_value)
    except ValueError as exc:
        raise RuntimeError("BOT_HEARTBEAT_MAX_AGE_SECONDS must be an integer") from exc
    if not 15 <= value <= 300:
        raise RuntimeError(
            "BOT_HEARTBEAT_MAX_AGE_SECONDS must be between 15 and 300"
        )
    return value


@dataclass(frozen=True)
class BotReadiness:
    ready: bool
    state: str
    reason: str
    age_seconds: float | None = None
    release_sha: str = "unknown"
    access_mode: str = "unknown"


class BotHeartbeat:
    def __init__(
        self,
        path: Path,
        *,
        release_sha: str,
        access_mode: str,
        now: Callable[[], datetime] = utcnow,
    ):
        self.path = Path(path)
        self.release_sha = release_sha.strip() or "unknown"
        self.access_mode = access_mode.strip() or "unknown"
        self.now = now
        self.started_at = self.now()

    def mark_starting(self) -> None:
        self._write("starting")

    def mark_ready(self) -> None:
        self._write("ready")

    def mark_stopped(self) -> None:
        self._write("stopped")

    def _write(self, state: str) -> None:
        if state not in HEARTBEAT_STATES:
            raise ValueError("Unknown heartbeat state")
        observed_at = self.now()
        payload = {
            "schema_version": HEARTBEAT_SCHEMA_VERSION,
            "state": state,
            "started_at": self.started_at.isoformat(),
            "heartbeat_at": observed_at.isoformat(),
            "pid": os.getpid(),
            "release_sha": self.release_sha,
            "access_mode": self.access_mode,
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=self.path.parent,
                prefix=f".{self.path.name}.",
                delete=False,
            ) as handle:
                temporary_path = Path(handle.name)
                os.chmod(temporary_path, 0o600)
                json.dump(payload, handle, ensure_ascii=True, separators=(",", ":"))
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary_path, self.path)
        finally:
            if temporary_path is not None and temporary_path.exists():
                temporary_path.unlink()


def inspect_bot_heartbeat(
    path: Path,
    *,
    max_age_seconds: int,
    now: datetime | None = None,
) -> BotReadiness:
    if not 1 <= max_age_seconds <= 3600:
        raise ValueError("Heartbeat max age is outside valid bounds")
    try:
        payload: Any = json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError:
        return BotReadiness(False, "missing", "heartbeat_missing")
    except (OSError, UnicodeError, json.JSONDecodeError):
        return BotReadiness(False, "invalid", "heartbeat_invalid")
    if not isinstance(payload, dict):
        return BotReadiness(False, "invalid", "heartbeat_invalid")
    state = str(payload.get("state") or "")
    if (
        payload.get("schema_version") != HEARTBEAT_SCHEMA_VERSION
        or state not in HEARTBEAT_STATES
    ):
        return BotReadiness(False, "invalid", "heartbeat_invalid")
    try:
        heartbeat_at = datetime.fromisoformat(str(payload["heartbeat_at"]))
        if heartbeat_at.tzinfo is None:
            raise ValueError
        age_seconds = (
            (now or utcnow()) - heartbeat_at.astimezone(timezone.utc)
        ).total_seconds()
        if age_seconds < -5:
            raise ValueError
        age_seconds = max(0.0, age_seconds)
    except (KeyError, TypeError, ValueError):
        return BotReadiness(False, "invalid", "heartbeat_invalid")
    release_sha = str(payload.get("release_sha") or "unknown")[:64]
    access_mode = str(payload.get("access_mode") or "unknown")[:32]
    if state != "ready":
        return BotReadiness(
            False,
            state,
            f"bot_{state}",
            age_seconds,
            release_sha,
            access_mode,
        )
    if age_seconds > max_age_seconds:
        return BotReadiness(
            False,
            state,
            "heartbeat_stale",
            age_seconds,
            release_sha,
            access_mode,
        )
    return BotReadiness(
        True,
        state,
        "ready",
        age_seconds,
        release_sha,
        access_mode,
    )
