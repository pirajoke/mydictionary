"""Persistent, privacy-minimized abuse controls for Telegram handlers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import math
import os
import re
from typing import Callable, Mapping
from uuid import uuid4

from sqlalchemy import select

from mydictionary.storage import AbuseEvent, DatabaseStore, RateLimitBucket, utcnow


SCOPE_RE = re.compile(r"^[a-z][a-z0-9_]{1,31}$")


class SafetyConfigurationError(RuntimeError):
    """Raised when an abuse-control setting is unsafe or malformed."""


def _bool(value: str, *, name: str) -> bool:
    normalized = str(value).strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off", ""}:
        return False
    raise SafetyConfigurationError(f"{name} must be a boolean")


def _bounded_int(
    values: Mapping[str, str],
    name: str,
    *,
    default: int,
    minimum: int,
    maximum: int,
) -> int:
    try:
        value = int(values.get(name, str(default)))
    except ValueError as exc:
        raise SafetyConfigurationError(f"{name} must be an integer") from exc
    if not minimum <= value <= maximum:
        raise SafetyConfigurationError(f"{name} is outside the allowed range")
    return value


@dataclass(frozen=True)
class RateLimitPolicy:
    limit: int
    window_seconds: int
    block_seconds: int


@dataclass(frozen=True)
class SafetySettings:
    enabled: bool
    default: RateLimitPolicy
    learning: RateLimitPolicy
    ai: RateLimitPolicy
    billing: RateLimitPolicy

    @classmethod
    def from_env(
        cls, values: Mapping[str, str] | None = None
    ) -> "SafetySettings":
        env = values if values is not None else os.environ
        enabled = _bool(
            env.get("SAFETY_RATE_LIMITS_ENABLED", "true"),
            name="SAFETY_RATE_LIMITS_ENABLED",
        )
        window = _bounded_int(
            env,
            "SAFETY_RATE_LIMIT_WINDOW_SECONDS",
            default=60,
            minimum=10,
            maximum=3600,
        )
        block = _bounded_int(
            env,
            "SAFETY_RATE_LIMIT_BLOCK_SECONDS",
            default=120,
            minimum=10,
            maximum=86400,
        )

        def policy(name: str, default: int) -> RateLimitPolicy:
            return RateLimitPolicy(
                limit=_bounded_int(
                    env,
                    name,
                    default=default,
                    minimum=1,
                    maximum=10000,
                ),
                window_seconds=window,
                block_seconds=block,
            )

        return cls(
            enabled=enabled,
            default=policy("SAFETY_DEFAULT_REQUESTS_PER_WINDOW", 90),
            learning=policy("SAFETY_LEARNING_REQUESTS_PER_WINDOW", 60),
            ai=policy("SAFETY_AI_REQUESTS_PER_WINDOW", 8),
            billing=policy("SAFETY_BILLING_REQUESTS_PER_WINDOW", 6),
        )

    def for_handler(self, handler_name: str) -> tuple[str, RateLimitPolicy]:
        name = str(handler_name).lower()
        if "buy" in name or "subscription" in name:
            return "billing", self.billing
        if name in {"cmd_ai", "block_ai_cb"} or name.startswith("voice"):
            return "ai", self.ai
        if any(
            marker in name
            for marker in (
                "quiz",
                "type",
                "flash",
                "smart",
                "poll",
                "learn",
                "block_",
            )
        ):
            return "learning", self.learning
        return "default", self.default


@dataclass(frozen=True)
class RateLimitDecision:
    allowed: bool
    scope: str
    remaining: int
    retry_after_seconds: int


def _aware(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


class PersistentRateLimiter:
    def __init__(
        self,
        store: DatabaseStore,
        *,
        now: Callable[[], datetime] = utcnow,
    ):
        self.store = store
        self.now = now

    def consume(
        self,
        *,
        user_id: int,
        scope: str,
        policy: RateLimitPolicy,
    ) -> RateLimitDecision:
        scope = str(scope).strip().lower()
        if not SCOPE_RE.fullmatch(scope):
            raise ValueError("Invalid rate-limit scope")
        if policy.limit < 1 or policy.window_seconds < 1 or policy.block_seconds < 1:
            raise ValueError("Invalid rate-limit policy")
        observed_at = _aware(self.now())
        self.store.ensure_user_id(int(user_id))
        with self.store.Session.begin() as session:
            row = session.execute(
                select(RateLimitBucket)
                .where(
                    RateLimitBucket.telegram_user_id == int(user_id),
                    RateLimitBucket.scope == scope,
                )
                .with_for_update()
            ).scalar_one_or_none()
            if row is None:
                session.add(
                    RateLimitBucket(
                        telegram_user_id=int(user_id),
                        scope=scope,
                        window_started_at=observed_at,
                        attempts=1,
                        updated_at=observed_at,
                    )
                )
                return RateLimitDecision(True, scope, policy.limit - 1, 0)

            if row.blocked_until is not None:
                blocked_until = _aware(row.blocked_until)
                if blocked_until > observed_at:
                    retry_after = max(
                        1, math.ceil((blocked_until - observed_at).total_seconds())
                    )
                    return RateLimitDecision(False, scope, 0, retry_after)
                row.blocked_until = None
                row.window_started_at = observed_at
                row.attempts = 1
                row.updated_at = observed_at
                return RateLimitDecision(True, scope, policy.limit - 1, 0)

            window_end = _aware(row.window_started_at) + timedelta(
                seconds=policy.window_seconds
            )
            if window_end <= observed_at:
                row.window_started_at = observed_at
                row.attempts = 1
                row.updated_at = observed_at
                return RateLimitDecision(True, scope, policy.limit - 1, 0)

            row.attempts += 1
            row.updated_at = observed_at
            if row.attempts <= policy.limit:
                return RateLimitDecision(
                    True, scope, policy.limit - row.attempts, 0
                )

            row.blocked_until = observed_at + timedelta(
                seconds=policy.block_seconds
            )
            session.add(
                AbuseEvent(
                    event_id=str(uuid4()),
                    telegram_user_id=int(user_id),
                    scope=scope,
                    rule="rate_limit_exceeded",
                    limit_value=policy.limit,
                    observed_count=row.attempts,
                    occurred_at=observed_at,
                )
            )
            return RateLimitDecision(False, scope, 0, policy.block_seconds)
