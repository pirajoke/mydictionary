"""Data retention and account erasure without touching financial records."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
import hashlib
import json
import os
from typing import Mapping

from sqlalchemy import delete, func, select

from mydictionary.storage import (
    AIAllowance,
    AIUsage,
    AbuseEvent,
    AdminAuditLog,
    AnalyticsEvent,
    DataImport,
    DatabaseStore,
    RateLimitBucket,
    User,
    UserPackEnrollment,
    UserProgress,
    WordProgress,
    utcnow,
)


class PrivacyStateError(RuntimeError):
    """Raised when a retention or deletion action is not permitted."""


def _bounded_days(
    values: Mapping[str, str],
    name: str,
    *,
    default: int,
    minimum: int,
    maximum: int = 3650,
) -> int:
    try:
        value = int(values.get(name, str(default)))
    except ValueError as exc:
        raise PrivacyStateError(f"{name} must be an integer") from exc
    if not minimum <= value <= maximum:
        raise PrivacyStateError(f"{name} is outside the allowed range")
    return value


@dataclass(frozen=True)
class RetentionPolicy:
    analytics_days: int
    ai_usage_days: int
    abuse_days: int
    rate_limit_days: int

    @classmethod
    def from_env(
        cls, values: Mapping[str, str] | None = None
    ) -> "RetentionPolicy":
        env = values if values is not None else os.environ
        return cls(
            analytics_days=_bounded_days(
                env, "RETENTION_ANALYTICS_DAYS", default=180, minimum=30
            ),
            ai_usage_days=_bounded_days(
                env, "RETENTION_AI_USAGE_DAYS", default=365, minimum=30
            ),
            abuse_days=_bounded_days(
                env, "RETENTION_ABUSE_DAYS", default=180, minimum=30
            ),
            rate_limit_days=_bounded_days(
                env, "RETENTION_RATE_LIMIT_DAYS", default=7, minimum=1
            ),
        )


@dataclass(frozen=True)
class RetentionReport:
    analytics_events: int = 0
    ai_usage: int = 0
    abuse_events: int = 0
    rate_limit_buckets: int = 0

    @property
    def total(self) -> int:
        return sum(asdict(self).values())


@dataclass(frozen=True)
class PrivacyDeletionResult:
    user_reference: str
    deleted_rows: int
    already_erased: bool


def _cutoffs(
    policy: RetentionPolicy, observed_at: datetime
) -> dict[str, datetime]:
    return {
        "analytics": observed_at - timedelta(days=policy.analytics_days),
        "ai_usage": observed_at - timedelta(days=policy.ai_usage_days),
        "abuse": observed_at - timedelta(days=policy.abuse_days),
        "rate_limit": observed_at - timedelta(days=policy.rate_limit_days),
    }


def retention_report(
    store: DatabaseStore,
    policy: RetentionPolicy,
    *,
    now: datetime | None = None,
) -> RetentionReport:
    cutoffs = _cutoffs(policy, now or utcnow())
    with store.Session() as session:
        return RetentionReport(
            analytics_events=int(
                session.scalar(
                    select(func.count()).select_from(AnalyticsEvent).where(
                        AnalyticsEvent.occurred_at < cutoffs["analytics"]
                    )
                )
                or 0
            ),
            ai_usage=int(
                session.scalar(
                    select(func.count()).select_from(AIUsage).where(
                        AIUsage.created_at < cutoffs["ai_usage"],
                        AIUsage.status.in_({"completed", "failed"}),
                    )
                )
                or 0
            ),
            abuse_events=int(
                session.scalar(
                    select(func.count()).select_from(AbuseEvent).where(
                        AbuseEvent.occurred_at < cutoffs["abuse"]
                    )
                )
                or 0
            ),
            rate_limit_buckets=int(
                session.scalar(
                    select(func.count()).select_from(RateLimitBucket).where(
                        RateLimitBucket.updated_at < cutoffs["rate_limit"]
                    )
                )
                or 0
            ),
        )


def apply_retention(
    store: DatabaseStore,
    policy: RetentionPolicy,
    *,
    now: datetime | None = None,
) -> RetentionReport:
    observed_at = now or utcnow()
    cutoffs = _cutoffs(policy, observed_at)
    with store.Session.begin() as session:
        analytics = session.execute(
            delete(AnalyticsEvent).where(
                AnalyticsEvent.occurred_at < cutoffs["analytics"]
            )
        ).rowcount
        ai_usage = session.execute(
            delete(AIUsage).where(
                AIUsage.created_at < cutoffs["ai_usage"],
                AIUsage.status.in_({"completed", "failed"}),
            )
        ).rowcount
        abuse = session.execute(
            delete(AbuseEvent).where(
                AbuseEvent.occurred_at < cutoffs["abuse"]
            )
        ).rowcount
        buckets = session.execute(
            delete(RateLimitBucket).where(
                RateLimitBucket.updated_at < cutoffs["rate_limit"]
            )
        ).rowcount
        report = RetentionReport(
            analytics_events=int(analytics or 0),
            ai_usage=int(ai_usage or 0),
            abuse_events=int(abuse or 0),
            rate_limit_buckets=int(buckets or 0),
        )
        session.add(
            AdminAuditLog(
                actor="retention-job",
                action="retention_applied",
                target_type="privacy",
                target_id=observed_at.date().isoformat(),
                details_json=json.dumps(asdict(report), sort_keys=True),
            )
        )
    return report


def _user_reference(user_id: int) -> str:
    return hashlib.sha256(f"user:{int(user_id)}".encode("ascii")).hexdigest()[:16]


def erase_user_learning_data(
    store: DatabaseStore,
    *,
    user_id: int,
    actor: str,
) -> PrivacyDeletionResult:
    """Erase product data while retaining immutable billing and audit records."""
    reference = _user_reference(user_id)
    with store.Session.begin() as session:
        user = session.execute(
            select(User)
            .where(User.telegram_user_id == int(user_id))
            .with_for_update()
        ).scalar_one_or_none()
        if user is None:
            raise PrivacyStateError("Telegram user does not exist")
        if user.role == "admin":
            raise PrivacyStateError("Administrator data cannot be self-erased")
        if user.privacy_status == "erased":
            return PrivacyDeletionResult(reference, 0, True)

        deleted_rows = 0
        for model in (
            WordProgress,
            UserPackEnrollment,
            UserProgress,
            AnalyticsEvent,
            AIUsage,
            AIAllowance,
            RateLimitBucket,
            AbuseEvent,
        ):
            deleted_rows += int(
                session.execute(
                    delete(model).where(model.telegram_user_id == int(user_id))
                ).rowcount
                or 0
            )
        deleted_rows += int(
            session.execute(
                delete(DataImport).where(
                    DataImport.telegram_user_id == int(user_id)
                )
            ).rowcount
            or 0
        )

        user.username = None
        user.first_name = None
        user.last_name = None
        user.language_code = None
        user.native_language = None
        user.learning_goal = None
        user.acquisition_source = None
        user.onboarding_completed_at = None
        user.daily_word_goal = 10
        user.access_status = "blocked"
        user.access_status_updated_at = utcnow()
        user.privacy_status = "erased"
        user.privacy_deleted_at = utcnow()
        user.updated_at = utcnow()
        session.add(
            AdminAuditLog(
                actor=str(actor)[:64],
                action="user_learning_data_erased",
                target_type="privacy_reference",
                target_id=reference,
                details_json=json.dumps(
                    {"deleted_rows": deleted_rows}, sort_keys=True
                ),
            )
        )
    return PrivacyDeletionResult(reference, deleted_rows, False)
