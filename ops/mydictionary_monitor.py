#!/usr/bin/env python3
"""Check MY DICTIONARY readiness and emit deduplicated operator alerts."""

from __future__ import annotations

import argparse
import asyncio
from dataclasses import asdict, dataclass
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
from typing import Any, Mapping
from urllib.parse import urlparse
from urllib.request import HTTPRedirectHandler, build_opener

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from telegram import Bot

from mydictionary.readiness import inspect_bot_heartbeat
from ops import mydictionary_backup as backup


class MonitorConfigurationError(RuntimeError):
    """Monitoring cannot run safely with the supplied settings."""


@dataclass(frozen=True)
class Config:
    heartbeat_path: Path
    heartbeat_max_age_seconds: int
    health_url: str
    timeout_seconds: int
    failure_threshold: int
    state_file: Path
    alerts_enabled: bool
    alert_bot_token: str | None
    alert_chat_id: int | None

    @classmethod
    def from_env(cls, values: Mapping[str, str] | None = None) -> "Config":
        env = values if values is not None else os.environ
        app_root = Path(_required(env, "MYDICTIONARY_APP_ROOT")).expanduser().resolve()
        health_url = str(
            env.get("MYDICTIONARY_HEALTH_URL") or "http://127.0.0.1:8791/health"
        ).strip()
        parsed = urlparse(health_url)
        if (
            parsed.scheme != "http"
            or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
        ):
            raise MonitorConfigurationError(
                "MYDICTIONARY_HEALTH_URL must be a local HTTP endpoint"
            )
        alerts_enabled = _bool(
            env.get("MYDICTIONARY_MONITOR_ALERTS_ENABLED", "false"),
            "MYDICTIONARY_MONITOR_ALERTS_ENABLED",
        )
        token = str(env.get("MYDICTIONARY_MONITOR_BOT_TOKEN") or "").strip() or None
        raw_chat = str(env.get("MYDICTIONARY_MONITOR_CHAT_ID") or "").strip()
        try:
            chat_id = int(raw_chat) if raw_chat else None
        except ValueError as exc:
            raise MonitorConfigurationError(
                "MYDICTIONARY_MONITOR_CHAT_ID must be an integer"
            ) from exc
        if alerts_enabled and (not token or chat_id is None):
            raise MonitorConfigurationError(
                "Enabled alerts require monitor bot token and chat ID"
            )
        return cls(
            heartbeat_path=Path(
                env.get("BOT_HEARTBEAT_PATH") or app_root / "bot-heartbeat.json"
            ).expanduser().resolve(),
            heartbeat_max_age_seconds=_bounded_int(
                env, "BOT_HEARTBEAT_MAX_AGE_SECONDS", 45, 15, 300
            ),
            health_url=health_url,
            timeout_seconds=_bounded_int(
                env, "MYDICTIONARY_MONITOR_TIMEOUT_SECONDS", 5, 1, 30
            ),
            failure_threshold=_bounded_int(
                env, "MYDICTIONARY_MONITOR_FAILURE_THRESHOLD", 2, 1, 10
            ),
            state_file=Path(
                env.get("MYDICTIONARY_MONITOR_STATE_FILE")
                or app_root / ".monitor-state.json"
            ).expanduser().resolve(),
            alerts_enabled=alerts_enabled,
            alert_bot_token=token,
            alert_chat_id=chat_id,
        )


@dataclass(frozen=True)
class CheckResult:
    name: str
    ok: bool
    reason: str


@dataclass(frozen=True)
class MonitorState:
    consecutive_failures: int = 0
    active_fingerprint: str | None = None


@dataclass(frozen=True)
class Evaluation:
    state: MonitorState
    notification: str | None
    healthy: bool


def _required(values: Mapping[str, str], name: str) -> str:
    value = str(values.get(name) or "").strip()
    if not value:
        raise MonitorConfigurationError(f"Missing required setting: {name}")
    return value


def _bool(value: str, name: str) -> bool:
    normalized = str(value).strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off", ""}:
        return False
    raise MonitorConfigurationError(f"{name} must be a boolean")


def _bounded_int(
    values: Mapping[str, str], name: str, default: int, minimum: int, maximum: int
) -> int:
    try:
        value = int(values.get(name, str(default)))
    except ValueError as exc:
        raise MonitorConfigurationError(f"{name} must be an integer") from exc
    if not minimum <= value <= maximum:
        raise MonitorConfigurationError(f"{name} is outside the allowed range")
    return value


def _health_check(config: Config) -> CheckResult:
    try:
        opener = build_opener(_RejectRedirects())
        with opener.open(config.health_url, timeout=config.timeout_seconds) as response:
            payload: Any = json.loads(response.read(65536).decode("utf-8"))
            ok = response.status == 200 and isinstance(payload, dict) and bool(
                payload.get("ready", payload.get("status") == "ok")
            )
        return CheckResult("admin_health", ok, "ready" if ok else "not_ready")
    except Exception as exc:
        return CheckResult("admin_health", False, type(exc).__name__)


class _RejectRedirects(HTTPRedirectHandler):
    def redirect_request(self, request, file_pointer, code, message, headers, url):
        return None


def collect_checks(
    config: Config, backup_config: backup.Config
) -> tuple[CheckResult, ...]:
    heartbeat = inspect_bot_heartbeat(
        config.heartbeat_path,
        max_age_seconds=config.heartbeat_max_age_seconds,
    )
    results = [
        CheckResult("bot_heartbeat", heartbeat.ready, heartbeat.reason),
        _health_check(config),
    ]
    try:
        backup.verify_latest(backup_config)
        results.append(CheckResult("database_backup", True, "verified"))
    except Exception as exc:
        results.append(CheckResult("database_backup", False, type(exc).__name__))
    return tuple(results)


def evaluate(
    checks: tuple[CheckResult, ...],
    previous: MonitorState,
    *,
    failure_threshold: int,
) -> Evaluation:
    failures = sorted(f"{row.name}:{row.reason}" for row in checks if not row.ok)
    if not failures:
        notification = (
            "MY DICTIONARY восстановлен: все readiness-проверки пройдены."
            if previous.active_fingerprint
            else None
        )
        return Evaluation(MonitorState(), notification, True)
    fingerprint = hashlib.sha256("\n".join(failures).encode("utf-8")).hexdigest()[:16]
    count = previous.consecutive_failures + 1
    notification = None
    active = previous.active_fingerprint
    if count >= failure_threshold and fingerprint != previous.active_fingerprint:
        notification = "MY DICTIONARY alert: " + "; ".join(failures)
        active = fingerprint
    return Evaluation(MonitorState(count, active), notification, False)


def load_state(path: Path) -> MonitorState:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return MonitorState(
            consecutive_failures=max(0, int(payload["consecutive_failures"])),
            active_fingerprint=(
                str(payload["active_fingerprint"])
                if payload.get("active_fingerprint")
                else None
            ),
        )
    except FileNotFoundError:
        return MonitorState()
    except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
        raise MonitorConfigurationError("Monitor state is invalid") from exc


def save_state(path: Path, state: MonitorState) -> None:
    if path.is_symlink():
        raise MonitorConfigurationError("Monitor state cannot be a symlink")
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=path.parent,
        prefix=f".{path.name}.",
        delete=False,
    ) as handle:
        temporary = Path(handle.name)
        os.chmod(temporary, 0o600)
        json.dump(asdict(state), handle, sort_keys=True)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


async def _send_alert(config: Config, text: str) -> None:
    if not config.alerts_enabled:
        return
    await Bot(token=str(config.alert_bot_token)).send_message(
        chat_id=int(config.alert_chat_id), text=text[:4000]
    )


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--execute", action="store_true")
    return result


def main() -> int:
    args = parser().parse_args()
    config = Config.from_env()
    checks = collect_checks(config, backup.Config.from_env())
    evaluation = evaluate(
        checks,
        load_state(config.state_file),
        failure_threshold=config.failure_threshold,
    )
    for check in checks:
        print(f"{check.name}={'ok' if check.ok else 'failed'} reason={check.reason}")
    if args.execute:
        save_state(config.state_file, evaluation.state)
        if evaluation.notification:
            asyncio.run(_send_alert(config, evaluation.notification))
    else:
        print("mode=preview")
    return 0 if evaluation.healthy else 1


if __name__ == "__main__":
    raise SystemExit(main())
