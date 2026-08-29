"""Transactional multi-user persistence for learner progress."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import re
from typing import Any, Mapping
from uuid import uuid4

from alembic import command
from alembic.config import Config
from sqlalchemy import (
    and_,
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    case,
    create_engine,
    delete,
    func,
    or_,
    select,
    text,
)
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

from mydictionary.catalog import PACK_ID_RE
from mydictionary.content import target_text, vocabulary_progress_id


PROFILE_FIELDS = (
    "total_correct",
    "total_wrong",
    "sessions",
    "xp",
    "level",
    "streak",
    "streak_best",
    "last_activity_date",
    "today_xp",
    "today_date",
    "active_lang",
    "active_pack_id",
)
WORD_PROGRESS_FIELDS = (
    "correct_count",
    "wrong_count",
    "last_seen",
    "interval",
    "next_review",
)
WORD_PROGRESS_DEFAULTS = {
    "correct_count": 0,
    "wrong_count": 0,
    "last_seen": None,
    "interval": 1,
    "next_review": None,
}
METERED_PROVIDER_ACTIONS = (
    "block_tutor",
    "voice_transcription",
    "voice_translation",
)
INTERFACE_LOCALES = frozenset({"en", "fr", "de", "ja", "ar", "zh", "ru", "es"})


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def vocabulary_id_for(word: Mapping[str, Any]) -> str:
    """Return the stable content identity used by persisted learner progress."""
    return vocabulary_progress_id(word)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint(
            "privacy_status IN ('active', 'erased')",
            name="ck_user_privacy_status",
        ),
    )

    telegram_user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    username: Mapped[str | None] = mapped_column(String(255), nullable=True)
    first_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    last_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    language_code: Mapped[str | None] = mapped_column(String(32), nullable=True)
    role: Mapped[str] = mapped_column(String(16), default="learner")
    native_language: Mapped[str | None] = mapped_column(String(16), nullable=True)
    learning_goal: Mapped[str | None] = mapped_column(String(32), nullable=True)
    daily_word_goal: Mapped[int] = mapped_column(Integer, default=10)
    onboarding_completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    acquisition_source: Mapped[str | None] = mapped_column(String(64), nullable=True)
    access_status: Mapped[str] = mapped_column(String(16), default="pending")
    access_status_updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    privacy_status: Mapped[str] = mapped_column(String(16), default="active")
    privacy_deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class UserProgress(Base):
    __tablename__ = "user_progress"

    telegram_user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.telegram_user_id", ondelete="CASCADE"),
        primary_key=True,
    )
    total_correct: Mapped[int] = mapped_column(Integer, default=0)
    total_wrong: Mapped[int] = mapped_column(Integer, default=0)
    sessions: Mapped[int] = mapped_column(Integer, default=0)
    xp: Mapped[int] = mapped_column(Integer, default=0)
    level: Mapped[int] = mapped_column(Integer, default=1)
    streak: Mapped[int] = mapped_column(Integer, default=0)
    streak_best: Mapped[int] = mapped_column(Integer, default=0)
    last_activity_date: Mapped[str | None] = mapped_column(String(10), nullable=True)
    today_xp: Mapped[int] = mapped_column(Integer, default=0)
    today_date: Mapped[str | None] = mapped_column(String(10), nullable=True)
    active_lang: Mapped[str] = mapped_column(String(16), default="en")
    active_pack_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class WordProgress(Base):
    __tablename__ = "word_progress"

    telegram_user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.telegram_user_id", ondelete="CASCADE"),
        primary_key=True,
    )
    language: Mapped[str] = mapped_column(String(16), primary_key=True)
    vocabulary_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    term: Mapped[str] = mapped_column(String(512))
    word_index: Mapped[int] = mapped_column(Integer)
    correct_count: Mapped[int] = mapped_column(Integer, default=0)
    wrong_count: Mapped[int] = mapped_column(Integer, default=0)
    last_seen: Mapped[str | None] = mapped_column(String(64), nullable=True)
    interval: Mapped[int] = mapped_column(Integer, default=1)
    next_review: Mapped[str | None] = mapped_column(String(64), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class UserPackEnrollment(Base):
    __tablename__ = "user_pack_enrollments"

    telegram_user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.telegram_user_id", ondelete="CASCADE"),
        primary_key=True,
    )
    pack_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    active: Mapped[bool] = mapped_column(default=True)
    enrolled_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )


class AnalyticsEvent(Base):
    __tablename__ = "analytics_events"

    event_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    telegram_user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.telegram_user_id", ondelete="CASCADE"),
        nullable=False,
    )
    event_name: Mapped[str] = mapped_column(String(64), nullable=False)
    session_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    source: Mapped[str | None] = mapped_column(String(64), nullable=True)
    properties_json: Mapped[str] = mapped_column(Text, default="{}")
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )


class TelegramNotification(Base):
    __tablename__ = "telegram_notifications"
    __table_args__ = (
        CheckConstraint(
            "kind IN ('pilot_access_approved')",
            name="ck_telegram_notification_kind",
        ),
        CheckConstraint(
            "status IN ('pending', 'processing', 'sent', 'failed', 'cancelled')",
            name="ck_telegram_notification_status",
        ),
        CheckConstraint("attempts >= 0", name="ck_telegram_notification_attempts"),
        UniqueConstraint(
            "idempotency_key", name="uq_telegram_notification_idempotency"
        ),
    )

    notification_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    telegram_user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.telegram_user_id", ondelete="CASCADE"),
        nullable=False,
    )
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="pending")
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    available_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )
    lease_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    sent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_error_code: Mapped[str | None] = mapped_column(
        String(64), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class UserConsent(Base):
    __tablename__ = "user_consents"
    __table_args__ = (
        CheckConstraint(
            "consent_type IN ('billing_terms', 'voice_processing', "
            "'voice_translation_processing', 'ai_processing')",
            name="ck_user_consent_type",
        ),
        UniqueConstraint(
            "telegram_user_id",
            "consent_type",
            "document_version",
            name="uq_user_consent_version",
        ),
    )

    consent_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    telegram_user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.telegram_user_id", ondelete="CASCADE"),
        nullable=False,
    )
    consent_type: Mapped[str] = mapped_column(String(32), nullable=False)
    document_version: Mapped[str] = mapped_column(String(64), nullable=False)
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    granted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class RateLimitBucket(Base):
    __tablename__ = "rate_limit_buckets"
    __table_args__ = (
        CheckConstraint("attempts >= 0", name="ck_rate_limit_attempts"),
    )

    telegram_user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.telegram_user_id", ondelete="CASCADE"),
        primary_key=True,
    )
    scope: Mapped[str] = mapped_column(String(32), primary_key=True)
    window_started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    blocked_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class AbuseEvent(Base):
    __tablename__ = "abuse_events"

    event_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    telegram_user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.telegram_user_id", ondelete="CASCADE"),
        nullable=False,
    )
    scope: Mapped[str] = mapped_column(String(32), nullable=False)
    rule: Mapped[str] = mapped_column(String(64), nullable=False)
    limit_value: Mapped[int] = mapped_column(Integer, nullable=False)
    observed_count: Mapped[int] = mapped_column(Integer, nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )


class VoiceSession(Base):
    __tablename__ = "voice_sessions"
    __table_args__ = (
        CheckConstraint(
            "status IN ('active', 'completed', 'cancelled', 'expired')",
            name="ck_voice_session_status",
        ),
        CheckConstraint(
            "mode IN ('pronunciation', 'conversation')",
            name="ck_voice_session_mode",
        ),
        CheckConstraint("turn_count >= 0", name="ck_voice_session_turn_count"),
        CheckConstraint("next_position >= 0", name="ck_voice_session_position"),
    )

    session_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    telegram_user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.telegram_user_id", ondelete="CASCADE"),
        nullable=False,
    )
    pack_id: Mapped[str] = mapped_column(String(64), nullable=False)
    language: Mapped[str] = mapped_column(String(16), nullable=False)
    topic: Mapped[str | None] = mapped_column(String(64), nullable=True)
    block_session_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    mode: Mapped[str] = mapped_column(String(16), nullable=False)
    vocabulary_ids_json: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="active")
    turn_count: Mapped[int] = mapped_column(Integer, default=0)
    next_position: Mapped[int] = mapped_column(Integer, default=0)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )
    ended_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class VoiceTurn(Base):
    __tablename__ = "voice_turns"
    __table_args__ = (
        CheckConstraint(
            "feedback_code IN ('exact', 'close', 'retry')",
            name="ck_voice_turn_feedback",
        ),
        CheckConstraint(
            "similarity_bps >= 0 AND similarity_bps <= 10000",
            name="ck_voice_turn_similarity",
        ),
        UniqueConstraint("request_id", name="uq_voice_turn_request"),
    )

    turn_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    session_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("voice_sessions.session_id", ondelete="CASCADE"),
        nullable=False,
    )
    telegram_user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.telegram_user_id", ondelete="CASCADE"),
        nullable=False,
    )
    request_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("ai_usage.request_id", ondelete="SET NULL"), nullable=True
    )
    expected_vocabulary_id: Mapped[str] = mapped_column(String(64), nullable=False)
    matched_vocabulary_id: Mapped[str | None] = mapped_column(
        String(64), nullable=True
    )
    transcript: Mapped[str] = mapped_column(Text, nullable=False)
    feedback_code: Mapped[str] = mapped_column(String(16), nullable=False)
    similarity_bps: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class MirrorDialogueTurn(Base):
    __tablename__ = "mirror_dialogue_turns"
    __table_args__ = (
        CheckConstraint(
            "role IN ('user', 'assistant')", name="ck_mirror_dialogue_turn_role"
        ),
        CheckConstraint(
            "turn_index IN (0, 1)", name="ck_mirror_dialogue_turn_index"
        ),
        UniqueConstraint(
            "exchange_id", "turn_index", name="uq_mirror_dialogue_exchange_turn"
        ),
    )

    turn_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    exchange_id: Mapped[str] = mapped_column(String(36), nullable=False)
    turn_index: Mapped[int] = mapped_column(Integer, nullable=False)
    telegram_user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.telegram_user_id", ondelete="CASCADE"),
        nullable=False,
    )
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class DataImport(Base):
    __tablename__ = "data_imports"

    import_key: Mapped[str] = mapped_column(String(255), primary_key=True)
    telegram_user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    details: Mapped[str | None] = mapped_column(Text, nullable=True)
    completed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AIAllowance(Base):
    __tablename__ = "ai_allowances"
    __table_args__ = (
        CheckConstraint("available_credits >= 0", name="ck_ai_allowance_available"),
        CheckConstraint("reserved_credits >= 0", name="ck_ai_allowance_reserved"),
        CheckConstraint("spent_credits >= 0", name="ck_ai_allowance_spent"),
    )

    telegram_user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.telegram_user_id", ondelete="CASCADE"),
        primary_key=True,
    )
    available_credits: Mapped[int] = mapped_column(Integer, default=0)
    reserved_credits: Mapped[int] = mapped_column(Integer, default=0)
    spent_credits: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class AIUsage(Base):
    __tablename__ = "ai_usage"
    __table_args__ = (
        CheckConstraint(
            "status IN ('reserved', 'completed', 'failed')",
            name="ck_ai_usage_status",
        ),
        CheckConstraint("reserved_credits >= 0", name="ck_ai_usage_reserved"),
        CheckConstraint("billed_credits >= 0", name="ck_ai_usage_billed"),
        CheckConstraint(
            "provider_attempts BETWEEN 0 AND 1",
            name="ck_ai_usage_provider_attempts",
        ),
        CheckConstraint(
            "projected_cost_micro_usd >= 0",
            name="ck_ai_usage_projected_cost",
        ),
    )

    request_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    telegram_user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.telegram_user_id", ondelete="CASCADE"),
        nullable=False,
    )
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    model: Mapped[str] = mapped_column(String(128), nullable=False)
    requested_service_tier: Mapped[str] = mapped_column(
        String(32), default="default"
    )
    returned_service_tier: Mapped[str | None] = mapped_column(
        String(32), nullable=True
    )
    economics_snapshot_id: Mapped[str] = mapped_column(
        String(128), default="legacy"
    )
    economics_snapshot_sha256: Mapped[str] = mapped_column(
        String(64), default="0" * 64
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    provider_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    provider_attempts: Mapped[int] = mapped_column(Integer, default=0)
    provider_response_received: Mapped[bool] = mapped_column(Boolean, default=False)
    cost_is_estimate: Mapped[bool] = mapped_column(Boolean, default=True)
    context_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    reserved_credits: Mapped[int] = mapped_column(Integer, default=0)
    billed_credits: Mapped[int] = mapped_column(Integer, default=0)
    projected_cost_micro_usd: Mapped[int] = mapped_column(BigInteger, default=0)
    provider_response_id: Mapped[str | None] = mapped_column(
        String(128), nullable=True
    )
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cached_input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cache_write_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    reasoning_tokens: Mapped[int] = mapped_column(Integer, default=0)
    total_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cost_micro_usd: Mapped[int] = mapped_column(BigInteger, default=0)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    error_code: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    provider_completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class MirrorPolicySnapshot(Base):
    __tablename__ = "mirror_policy_snapshots"

    snapshot_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    policy_version: Mapped[str] = mapped_column(String(64), nullable=False)
    enabled_modes_json: Mapped[str] = mapped_column(Text, nullable=False)
    default_mode: Mapped[str] = mapped_column(String(16), nullable=False)
    answer_depth: Mapped[str] = mapped_column(String(16), nullable=False)
    learner_level: Mapped[str] = mapped_column(String(16), nullable=False)
    mode_guidance_json: Mapped[str] = mapped_column(Text, nullable=False)
    config_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    actor: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )


class MirrorResponseQuality(Base):
    __tablename__ = "mirror_response_quality"

    request_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("ai_usage.request_id", ondelete="CASCADE"),
        primary_key=True,
    )
    telegram_user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.telegram_user_id", ondelete="CASCADE"),
        nullable=False,
    )
    task: Mapped[str] = mapped_column(String(32), nullable=False)
    mode: Mapped[str] = mapped_column(String(16), nullable=False)
    depth: Mapped[str] = mapped_column(String(16), nullable=False)
    level: Mapped[str] = mapped_column(String(16), nullable=False)
    contract_version: Mapped[str] = mapped_column(String(64), nullable=False)
    response_length: Mapped[int] = mapped_column(Integer, nullable=False)
    evidence_count: Mapped[int] = mapped_column(Integer, nullable=False)
    example_count: Mapped[int] = mapped_column(Integer, nullable=False)
    has_next_step: Mapped[bool] = mapped_column(Boolean, nullable=False)
    deterministic_score_bps: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )


class MirrorResponseFeedback(Base):
    __tablename__ = "mirror_response_feedback"

    request_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("ai_usage.request_id", ondelete="CASCADE"),
        primary_key=True,
    )
    telegram_user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.telegram_user_id", ondelete="CASCADE"),
        nullable=False,
    )
    helpful: Mapped[bool] = mapped_column(Boolean, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )


class AIBudgetState(Base):
    __tablename__ = "ai_budget_state"
    __table_args__ = (
        CheckConstraint("id = 1", name="ck_ai_budget_singleton"),
        CheckConstraint(
            "in_flight_micro_usd >= 0", name="ck_ai_budget_in_flight"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    in_flight_micro_usd: Mapped[int] = mapped_column(BigInteger, default=0)
    breaker_open: Mapped[bool] = mapped_column(Boolean, default=False)
    breaker_reason: Mapped[str | None] = mapped_column(String(128), nullable=True)
    breaker_opened_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    breaker_acknowledged_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    breaker_acknowledged_by: Mapped[str | None] = mapped_column(
        String(64), nullable=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class AppSetting(Base):
    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    updated_by: Mapped[str] = mapped_column(String(64), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class AdminCredential(Base):
    __tablename__ = "admin_credentials"

    singleton_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(64), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(512), nullable=False)
    session_version: Mapped[int] = mapped_column(Integer, default=1)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class AdminPasswordReset(Base):
    __tablename__ = "admin_password_resets"

    reset_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    token_digest: Mapped[str] = mapped_column(
        String(64), nullable=False, unique=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    activated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    invalidated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class AdminAuditLog(Base):
    __tablename__ = "admin_audit_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    actor: Mapped[str] = mapped_column(String(64), nullable=False)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    target_type: Mapped[str] = mapped_column(String(64), nullable=False)
    target_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    details_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AICreditLedger(Base):
    __tablename__ = "ai_credit_ledger"
    __table_args__ = (
        CheckConstraint("delta != 0", name="ck_ai_credit_ledger_delta"),
        CheckConstraint(
            "balance_after >= 0", name="ck_ai_credit_ledger_balance"
        ),
    )

    entry_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    telegram_user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.telegram_user_id", ondelete="CASCADE"),
        nullable=False,
    )
    delta: Mapped[int] = mapped_column(Integer, nullable=False)
    balance_after: Mapped[int] = mapped_column(Integer, nullable=False)
    reason: Mapped[str] = mapped_column(String(255), nullable=False)
    actor: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AIWallet(Base):
    __tablename__ = "ai_wallets"
    __table_args__ = (
        CheckConstraint("balance_credits >= 0", name="ck_ai_wallet_balance"),
        CheckConstraint("reserved_credits >= 0", name="ck_ai_wallet_reserved"),
        CheckConstraint("spent_credits >= 0", name="ck_ai_wallet_spent"),
        CheckConstraint(
            "reserved_credits <= balance_credits",
            name="ck_ai_wallet_reserved_balance",
        ),
    )

    telegram_user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.telegram_user_id", ondelete="CASCADE"),
        primary_key=True,
    )
    balance_credits: Mapped[int] = mapped_column(Integer, default=0)
    reserved_credits: Mapped[int] = mapped_column(Integer, default=0)
    spent_credits: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class BillingProduct(Base):
    __tablename__ = "billing_products"
    __table_args__ = (
        CheckConstraint("credits > 0", name="ck_billing_product_credits"),
        CheckConstraint("price_xtr > 0", name="ck_billing_product_price"),
        CheckConstraint(
            "status IN ('draft', 'active', 'archived')",
            name="ck_billing_product_status",
        ),
        CheckConstraint(
            "estimated_cost_micro_usd >= 0",
            name="ck_billing_product_cost",
        ),
        CheckConstraint(
            "target_margin_bps >= 0 AND target_margin_bps <= 10000",
            name="ck_billing_product_margin",
        ),
        CheckConstraint(
            "billing_mode IN ('one_time', 'subscription')",
            name="ck_billing_product_mode",
        ),
        CheckConstraint(
            "(billing_mode = 'one_time' AND subscription_period_seconds IS NULL) "
            "OR (billing_mode = 'subscription' AND "
            "subscription_period_seconds = 2592000)",
            name="ck_billing_product_subscription_period",
        ),
    )

    product_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    title: Mapped[str] = mapped_column(String(32), nullable=False)
    description: Mapped[str] = mapped_column(String(255), nullable=False)
    credits: Mapped[int] = mapped_column(Integer, nullable=False)
    price_xtr: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="draft")
    estimated_cost_micro_usd: Mapped[int] = mapped_column(BigInteger, default=0)
    target_margin_bps: Mapped[int] = mapped_column(Integer, default=0)
    display_order: Mapped[int] = mapped_column(Integer, default=0)
    billing_mode: Mapped[str] = mapped_column(String(16), default="one_time")
    subscription_period_seconds: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class PaymentOrder(Base):
    __tablename__ = "payment_orders"
    __table_args__ = (
        CheckConstraint("credits_snapshot > 0", name="ck_payment_order_credits"),
        CheckConstraint("amount_xtr > 0", name="ck_payment_order_amount"),
        CheckConstraint("currency = 'XTR'", name="ck_payment_order_currency"),
        CheckConstraint(
            "status IN ('created', 'prechecked', 'paid', 'expired', "
            "'cancelled', 'refund_pending', 'refunded', "
            "'subscription_active', 'subscription_cancelled')",
            name="ck_payment_order_status",
        ),
        CheckConstraint(
            "billing_mode IN ('one_time', 'subscription')",
            name="ck_payment_order_mode",
        ),
        CheckConstraint(
            "(billing_mode = 'one_time' AND subscription_period_seconds IS NULL) "
            "OR (billing_mode = 'subscription' AND "
            "subscription_period_seconds = 2592000)",
            name="ck_payment_order_subscription_period",
        ),
        UniqueConstraint("invoice_payload", name="uq_payment_order_payload"),
    )

    order_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    telegram_user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.telegram_user_id", ondelete="CASCADE"),
        nullable=False,
    )
    product_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("billing_products.product_id"), nullable=False
    )
    product_title: Mapped[str] = mapped_column(String(32), nullable=False)
    product_description: Mapped[str] = mapped_column(String(255), nullable=False)
    credits_snapshot: Mapped[int] = mapped_column(Integer, nullable=False)
    amount_xtr: Mapped[int] = mapped_column(Integer, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="XTR")
    terms_version: Mapped[str] = mapped_column(String(64), default="unversioned")
    invoice_payload: Mapped[str] = mapped_column(String(128), nullable=False)
    billing_mode: Mapped[str] = mapped_column(String(16), default="one_time")
    subscription_period_seconds: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )
    status: Mapped[str] = mapped_column(String(24), default="created")
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    prechecked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    refunded_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class StarsPayment(Base):
    __tablename__ = "stars_payments"
    __table_args__ = (
        CheckConstraint("total_amount > 0", name="ck_stars_payment_amount"),
        CheckConstraint("currency = 'XTR'", name="ck_stars_payment_currency"),
        CheckConstraint(
            "status IN ('paid', 'refund_pending', 'refunded')",
            name="ck_stars_payment_status",
        ),
        UniqueConstraint(
            "telegram_payment_charge_id", name="uq_stars_payment_charge"
        ),
    )

    payment_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    order_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("payment_orders.order_id"), nullable=False
    )
    telegram_user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.telegram_user_id", ondelete="RESTRICT"),
        nullable=False,
    )
    currency: Mapped[str] = mapped_column(String(3), default="XTR")
    total_amount: Mapped[int] = mapped_column(Integer, nullable=False)
    telegram_payment_charge_id: Mapped[str] = mapped_column(
        String(255), nullable=False
    )
    provider_payment_charge_id: Mapped[str | None] = mapped_column(
        String(255), nullable=True
    )
    subscription_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("stars_subscriptions.subscription_id"), nullable=True
    )
    is_recurring: Mapped[bool] = mapped_column(Boolean, default=False)
    is_first_recurring: Mapped[bool] = mapped_column(Boolean, default=False)
    subscription_expiration_date: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    status: Mapped[str] = mapped_column(String(24), default="paid")
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    refunded_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class StarsSubscription(Base):
    __tablename__ = "stars_subscriptions"
    __table_args__ = (
        CheckConstraint(
            "status IN ('active', 'cancelled', 'expired')",
            name="ck_stars_subscription_status",
        ),
        CheckConstraint(
            "period_seconds = 2592000",
            name="ck_stars_subscription_period",
        ),
        UniqueConstraint("order_id", name="uq_stars_subscription_order"),
        UniqueConstraint(
            "telegram_payment_charge_id", name="uq_stars_subscription_charge"
        ),
    )

    subscription_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    order_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("payment_orders.order_id"), nullable=False
    )
    telegram_user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.telegram_user_id", ondelete="RESTRICT"),
        nullable=False,
    )
    product_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("billing_products.product_id"), nullable=False
    )
    telegram_payment_charge_id: Mapped[str] = mapped_column(
        String(255), nullable=False
    )
    status: Mapped[str] = mapped_column(String(16), default="active")
    period_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    current_period_end: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    cancelled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class BillingCreditLedger(Base):
    __tablename__ = "billing_credit_ledger"
    __table_args__ = (
        CheckConstraint("delta != 0", name="ck_billing_credit_ledger_delta"),
        CheckConstraint(
            "balance_after >= 0", name="ck_billing_credit_ledger_balance"
        ),
        UniqueConstraint(
            "idempotency_key", name="uq_billing_credit_ledger_idempotency"
        ),
    )

    entry_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    telegram_user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.telegram_user_id", ondelete="CASCADE"),
        nullable=False,
    )
    delta: Mapped[int] = mapped_column(Integer, nullable=False)
    balance_after: Mapped[int] = mapped_column(Integer, nullable=False)
    entry_type: Mapped[str] = mapped_column(String(32), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False)
    reference_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    reference_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    reason: Mapped[str] = mapped_column(String(255), nullable=False)
    actor: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class RefundRequest(Base):
    __tablename__ = "refund_requests"
    __table_args__ = (
        CheckConstraint("credits > 0", name="ck_refund_request_credits"),
        CheckConstraint(
            "status IN ('requested', 'processing', 'completed', 'failed', "
            "'cancelled')",
            name="ck_refund_request_status",
        ),
        UniqueConstraint("payment_id", name="uq_refund_request_payment"),
    )

    refund_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    payment_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("stars_payments.payment_id"), nullable=False
    )
    telegram_user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.telegram_user_id", ondelete="RESTRICT"),
        nullable=False,
    )
    credits: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="requested")
    reason: Mapped[str] = mapped_column(String(255), nullable=False)
    requested_by: Mapped[str] = mapped_column(String(64), nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class AIQuotaExceeded(RuntimeError):
    """Raised when credits, request limits, or the cost breaker block AI use."""


class AICreditExhausted(AIQuotaExceeded):
    """Raised only when a learner wallet cannot fund an AI reservation."""


class AIUsageStateError(RuntimeError):
    """Raised when an AI usage transition is invalid or duplicated."""


USER_ROLES = {"learner", "admin"}
ACCESS_STATUSES = {"pending", "active", "blocked"}
TELEGRAM_NOTIFICATION_STATUSES = {
    "pending",
    "processing",
    "sent",
    "failed",
    "cancelled",
}
EVENT_NAME_RE = re.compile(r"^[a-z][a-z0-9_]{1,63}$")
EVENT_PROPERTY_KEYS = {
    "amount_xtr",
    "correct_count",
    "consent_type",
    "credits",
    "daily_word_goal",
    "document_version",
    "goal",
    "language",
    "lesson_kind",
    "mode",
    "pack_id",
    "position",
    "product_id",
    "rating",
    "retry",
    "topic",
    "word_count",
    "word_index",
    "wrong_count",
}
EVENT_DIMENSION_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}$")
CONSENT_TYPES = {
    "billing_terms",
    "voice_processing",
    "voice_translation_processing",
    "ai_processing",
}


def run_migrations(database_url: str) -> None:
    """Upgrade a database using the repository's versioned Alembic migrations."""
    root = Path(__file__).resolve().parents[1]
    config = Config(str(root / "alembic.ini"))
    # The application already owns logging. Alembic's CLI configuration would
    # otherwise replace the root logger and hide all subsequent bot INFO logs.
    config.attributes["configure_logging"] = False
    config.set_main_option("script_location", str(root / "migrations"))
    config.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))
    command.upgrade(config, "head")


def _profile_values(progress: Mapping[str, Any]) -> dict[str, Any]:
    return {field: progress[field] for field in PROFILE_FIELDS if field in progress}


def _word_values(word: Mapping[str, Any]) -> dict[str, Any]:
    return {
        field: word.get(field, WORD_PROGRESS_DEFAULTS[field])
        for field in WORD_PROGRESS_FIELDS
    }


class DatabaseStore:
    """Small synchronous repository used by the Telegram application services."""

    def __init__(self, database_url: str, *, migrate: bool = True):
        self.database_url = database_url
        if migrate:
            run_migrations(database_url)
        connect_args = (
            {"check_same_thread": False}
            if database_url.startswith("sqlite")
            else {}
        )
        self.engine = create_engine(
            database_url,
            connect_args=connect_args,
            pool_pre_ping=not database_url.startswith("sqlite"),
        )
        self.Session = sessionmaker(self.engine, expire_on_commit=False)

    def close(self) -> None:
        self.engine.dispose()

    def ensure_user(
        self,
        telegram_user: Any,
        *,
        role: str | None = None,
        acquisition_source: str | None = None,
    ) -> None:
        if role is not None and role not in USER_ROLES:
            raise ValueError("Unknown user role")
        if acquisition_source is not None and not EVENT_DIMENSION_RE.fullmatch(
            str(acquisition_source)
        ):
            raise ValueError("Invalid acquisition source")
        user_id = int(telegram_user.id)
        with self.Session.begin() as session:
            user = session.get(User, user_id)
            if user is None:
                user = User(
                    telegram_user_id=user_id,
                    role=role or "learner",
                    access_status="active" if role == "admin" else "pending",
                    access_status_updated_at=utcnow() if role == "admin" else None,
                )
                session.add(user)
            elif role == "admin":
                # Runtime configuration may promote an owner but never downgrades one.
                user.role = "admin"
                user.access_status = "active"
                user.access_status_updated_at = utcnow()
            for field in ("username", "first_name", "last_name", "language_code"):
                value = getattr(telegram_user, field, None)
                if value is not None:
                    setattr(user, field, str(value))
            if acquisition_source and not user.acquisition_source:
                user.acquisition_source = str(acquisition_source)[:64]
            user.updated_at = utcnow()
            if session.get(UserProgress, user_id) is None:
                session.add(UserProgress(telegram_user_id=user_id))

    def ensure_user_id(self, user_id: int) -> None:
        telegram_user = type("TelegramUser", (), {"id": int(user_id)})()
        self.ensure_user(telegram_user)

    def get_mirror_response_mode(self, user_id: int) -> str:
        self.ensure_user_id(user_id)
        with self.engine.connect() as connection:
            row = connection.execute(
                text(
                    "SELECT privacy_status, mirror_response_mode FROM users "
                    "WHERE telegram_user_id = :user_id"
                ),
                {"user_id": int(user_id)},
            ).mappings().one()
        if row["privacy_status"] != "active":
            return "text"
        mode = str(row["mirror_response_mode"] or "text")
        return mode if mode in {"text", "voice", "both"} else "text"

    def set_interface_locale(self, user_id: int, locale: str) -> str:
        """Persist a bot-interface locale without changing Telegram metadata."""
        normalized = str(locale).strip()
        if normalized not in INTERFACE_LOCALES:
            raise ValueError("Unsupported interface locale")
        with self.engine.begin() as connection:
            row = connection.execute(
                text(
                    "SELECT privacy_status, access_status, interface_locale "
                    "FROM users WHERE telegram_user_id = :user_id"
                ),
                {"user_id": int(user_id)},
            ).mappings().one_or_none()
            if (
                row is None
                or row["privacy_status"] != "active"
                or row["access_status"] != "active"
            ):
                raise PermissionError("Learner cannot change interface locale")
            if row["interface_locale"] != normalized:
                connection.execute(
                    text(
                        "UPDATE users SET interface_locale = :locale, "
                        "updated_at = :updated_at WHERE telegram_user_id = :user_id"
                    ),
                    {
                        "locale": normalized,
                        "updated_at": utcnow(),
                        "user_id": int(user_id),
                    },
                )
        return normalized

    def set_mirror_response_mode(self, user_id: int, mode: str) -> str:
        normalized = str(mode).strip().lower()
        if normalized not in {"text", "voice", "both"}:
            raise ValueError("Mirror response mode must be text, voice, or both")
        self.ensure_user_id(user_id)
        with self.engine.begin() as connection:
            privacy_status = connection.execute(
                text(
                    "SELECT privacy_status FROM users "
                    "WHERE telegram_user_id = :user_id"
                ),
                {"user_id": int(user_id)},
            ).scalar_one()
            if privacy_status != "active":
                raise ValueError("Erased users cannot change response preferences")
            connection.execute(
                text(
                    "UPDATE users SET mirror_response_mode = :mode, "
                    "updated_at = :updated_at WHERE telegram_user_id = :user_id"
                ),
                {
                    "mode": normalized,
                    "updated_at": utcnow(),
                    "user_id": int(user_id),
                },
            )
        return normalized

    def get_mirror_style(self, user_id: int) -> str:
        self.ensure_user_id(user_id)
        with self.engine.connect() as connection:
            row = connection.execute(
                text(
                    "SELECT privacy_status, mirror_style FROM users "
                    "WHERE telegram_user_id = :user_id"
                ),
                {"user_id": int(user_id)},
            ).mappings().one()
        if row["privacy_status"] != "active":
            return "teacher"
        style = str(row["mirror_style"] or "teacher")
        return (
            style
            if style in {"teacher", "conversation", "brief", "practice"}
            else "teacher"
        )

    def set_mirror_style(self, user_id: int, style: str) -> str:
        normalized = str(style).strip().lower()
        if normalized not in {"teacher", "conversation", "brief", "practice"}:
            raise ValueError("Unknown Mirror style")
        self.ensure_user_id(user_id)
        with self.engine.begin() as connection:
            privacy_status = connection.execute(
                text(
                    "SELECT privacy_status FROM users "
                    "WHERE telegram_user_id = :user_id"
                ),
                {"user_id": int(user_id)},
            ).scalar_one()
            if privacy_status != "active":
                raise ValueError("Erased users cannot change Mirror style")
            connection.execute(
                text(
                    "UPDATE users SET mirror_style = :style, updated_at = :updated_at "
                    "WHERE telegram_user_id = :user_id"
                ),
                {
                    "style": normalized,
                    "updated_at": utcnow(),
                    "user_id": int(user_id),
                },
            )
        return normalized

    def get_mirror_preferences(self, user_id: int) -> dict[str, str]:
        """Return bounded learner-facing Mirror preferences."""
        defaults = {
            "mode": "teacher",
            "depth": "balanced",
            "level": "adaptive",
        }
        self.ensure_user_id(user_id)
        with self.engine.connect() as connection:
            row = connection.execute(
                text(
                    "SELECT privacy_status, mirror_style, mirror_depth, mirror_level "
                    "FROM users WHERE telegram_user_id = :user_id"
                ),
                {"user_id": int(user_id)},
            ).mappings().one()
        if row["privacy_status"] != "active":
            return defaults
        mode = str(row["mirror_style"] or defaults["mode"])
        depth = str(row["mirror_depth"] or defaults["depth"])
        level = str(row["mirror_level"] or defaults["level"])
        return {
            "mode": mode
            if mode
            in {"teacher", "conversation", "coach", "practice", "brief", "exam"}
            else defaults["mode"],
            "depth": depth
            if depth in {"compact", "balanced", "deep"}
            else defaults["depth"],
            "level": level
            if level in {"adaptive", "a1", "a2", "b1", "b2", "c1"}
            else defaults["level"],
        }

    def set_mirror_preferences(
        self,
        user_id: int,
        *,
        mode: str,
        depth: str,
        level: str,
    ) -> dict[str, str]:
        values = {
            "mode": str(mode).strip().lower(),
            "depth": str(depth).strip().lower(),
            "level": str(level).strip().lower(),
        }
        if values["mode"] not in {
            "teacher",
            "conversation",
            "coach",
            "practice",
            "brief",
            "exam",
        }:
            raise ValueError("Unknown Mirror communication mode")
        if values["depth"] not in {"compact", "balanced", "deep"}:
            raise ValueError("Unknown Mirror answer depth")
        if values["level"] not in {
            "adaptive",
            "a1",
            "a2",
            "b1",
            "b2",
            "c1",
        }:
            raise ValueError("Unknown Mirror learner level")
        self.ensure_user_id(user_id)
        with self.engine.begin() as connection:
            privacy_status = connection.execute(
                text(
                    "SELECT privacy_status FROM users "
                    "WHERE telegram_user_id = :user_id"
                ),
                {"user_id": int(user_id)},
            ).scalar_one()
            if privacy_status != "active":
                raise ValueError("Erased users cannot change Mirror preferences")
            connection.execute(
                text(
                    "UPDATE users SET mirror_style = :mode, "
                    "mirror_depth = :depth, mirror_level = :level, "
                    "updated_at = :updated_at WHERE telegram_user_id = :user_id"
                ),
                {
                    **values,
                    "updated_at": utcnow(),
                    "user_id": int(user_id),
                },
            )
        return values

    def record_mirror_quality(
        self,
        *,
        request_id: str,
        user_id: int,
        task: str,
        mode: str,
        depth: str,
        level: str,
        contract_version: str,
        response_length: int,
        evidence_count: int,
        example_count: int,
        has_next_step: bool,
        deterministic_score_bps: int,
    ) -> dict[str, Any]:
        score = int(deterministic_score_bps)
        if not 0 <= score <= 10000:
            raise ValueError("Mirror quality score must be 0-10000")
        with self.Session.begin() as session:
            usage = session.get(AIUsage, str(request_id))
            if usage is None or usage.telegram_user_id != int(user_id):
                raise PermissionError("Mirror quality request owner mismatch")
            existing = session.get(MirrorResponseQuality, str(request_id))
            if existing is not None:
                row = existing
            else:
                row = MirrorResponseQuality(
                    request_id=str(request_id),
                    telegram_user_id=int(user_id),
                    task=str(task)[:32],
                    mode=str(mode)[:16],
                    depth=str(depth)[:16],
                    level=str(level)[:16],
                    contract_version=str(contract_version)[:64],
                    response_length=max(0, int(response_length)),
                    evidence_count=max(0, int(evidence_count)),
                    example_count=max(0, int(example_count)),
                    has_next_step=bool(has_next_step),
                    deterministic_score_bps=score,
                )
                session.add(row)
        return self.mirror_quality_for_request(str(request_id))

    def mirror_quality_for_request(self, request_id: str) -> dict[str, Any]:
        with self.Session() as session:
            row = session.get(MirrorResponseQuality, str(request_id))
            if row is None:
                return {}
            return {
                column.name: getattr(row, column.name)
                for column in MirrorResponseQuality.__table__.columns
            }

    def rate_mirror_response(
        self, user_id: int, *, request_id: str, helpful: bool
    ) -> bool:
        with self.Session.begin() as session:
            usage = session.get(AIUsage, str(request_id))
            if usage is None or usage.telegram_user_id != int(user_id):
                raise PermissionError("Mirror response owner mismatch")
            existing = session.get(MirrorResponseFeedback, str(request_id))
            if existing is not None:
                return False
            session.add(
                MirrorResponseFeedback(
                    request_id=str(request_id),
                    telegram_user_id=int(user_id),
                    helpful=bool(helpful),
                )
            )
        return True

    def mirror_feedback_for_request(self, request_id: str) -> dict[str, Any]:
        with self.Session() as session:
            row = session.get(MirrorResponseFeedback, str(request_id))
            if row is None:
                return {}
            return {
                column.name: getattr(row, column.name)
                for column in MirrorResponseFeedback.__table__.columns
            }

    def append_mirror_exchange(
        self,
        user_id: int,
        *,
        question: str,
        answer: str,
        retention_days: int,
        now: datetime | None = None,
    ) -> None:
        days = int(retention_days)
        if not 1 <= days <= 30:
            raise ValueError("Mirror dialogue retention must be 1-30 days")
        clean_question = str(question).strip()
        clean_answer = str(answer).strip()
        if not clean_question or not clean_answer:
            raise ValueError("Mirror exchange text cannot be empty")
        clean_question = clean_question[:500]
        clean_answer = clean_answer[:500]
        observed_at = now or utcnow()
        if observed_at.tzinfo is None:
            observed_at = observed_at.replace(tzinfo=timezone.utc)
        self.ensure_user_id(user_id)
        exchange_id = str(uuid4())
        expires_at = observed_at + timedelta(days=days)
        with self.Session.begin() as session:
            user = session.execute(
                select(User)
                .where(User.telegram_user_id == int(user_id))
                .with_for_update()
            ).scalar_one_or_none()
            if user is None or user.privacy_status != "active":
                raise ValueError("Erased users cannot store Mirror dialogue")
            session.add_all(
                [
                    MirrorDialogueTurn(
                        turn_id=str(uuid4()),
                        exchange_id=exchange_id,
                        turn_index=0,
                        telegram_user_id=int(user_id),
                        role="user",
                        text=clean_question,
                        created_at=observed_at,
                        expires_at=expires_at,
                    ),
                    MirrorDialogueTurn(
                        turn_id=str(uuid4()),
                        exchange_id=exchange_id,
                        turn_index=1,
                        telegram_user_id=int(user_id),
                        role="assistant",
                        text=clean_answer,
                        created_at=observed_at,
                        expires_at=expires_at,
                    ),
                ]
            )
            session.flush()
            stale_exchange_ids = session.execute(
                select(MirrorDialogueTurn.exchange_id)
                .where(MirrorDialogueTurn.telegram_user_id == int(user_id))
                .group_by(MirrorDialogueTurn.exchange_id)
                .order_by(
                    func.max(MirrorDialogueTurn.created_at).desc(),
                    MirrorDialogueTurn.exchange_id.desc(),
                )
                .offset(10)
            ).scalars().all()
            if stale_exchange_ids:
                session.execute(
                    delete(MirrorDialogueTurn).where(
                        MirrorDialogueTurn.telegram_user_id == int(user_id),
                        MirrorDialogueTurn.exchange_id.in_(stale_exchange_ids),
                    )
                )

    def get_mirror_dialogue(
        self,
        user_id: int,
        *,
        limit: int = 20,
        now: datetime | None = None,
    ) -> list[dict[str, str]]:
        bounded_limit = int(limit)
        if not 1 <= bounded_limit <= 20:
            raise ValueError("Mirror dialogue limit must be 1-20 turns")
        observed_at = now or utcnow()
        if observed_at.tzinfo is None:
            observed_at = observed_at.replace(tzinfo=timezone.utc)
        with self.Session.begin() as session:
            user = session.get(User, int(user_id))
            if user is None or user.privacy_status != "active":
                return []
            session.execute(
                delete(MirrorDialogueTurn).where(
                    MirrorDialogueTurn.telegram_user_id == int(user_id),
                    MirrorDialogueTurn.expires_at <= observed_at,
                )
            )
            rows = session.execute(
                select(MirrorDialogueTurn)
                .where(
                    MirrorDialogueTurn.telegram_user_id == int(user_id),
                    MirrorDialogueTurn.expires_at > observed_at,
                )
                .order_by(
                    MirrorDialogueTurn.created_at.desc(),
                    MirrorDialogueTurn.turn_index.desc(),
                    MirrorDialogueTurn.turn_id.desc(),
                )
                .limit(bounded_limit)
            ).scalars().all()
        rows.reverse()
        return [{"role": row.role, "text": row.text} for row in rows]

    def clear_mirror_dialogue(self, user_id: int) -> int:
        with self.Session.begin() as session:
            deleted = session.execute(
                delete(MirrorDialogueTurn).where(
                    MirrorDialogueTurn.telegram_user_id == int(user_id)
                )
            ).rowcount
        return int(deleted or 0)

    def product_profile(self, user_id: int) -> dict[str, Any]:
        self.ensure_user_id(user_id)
        with self.Session() as session:
            user = session.get(User, int(user_id))
            progress = session.get(UserProgress, int(user_id))
            interface_locale = session.execute(
                text(
                    "SELECT interface_locale FROM users "
                    "WHERE telegram_user_id = :user_id"
                ),
                {"user_id": int(user_id)},
            ).scalar_one()
            return {
                "role": user.role,
                "native_language": user.native_language,
                "learning_goal": user.learning_goal,
                "daily_word_goal": user.daily_word_goal,
                "onboarding_completed_at": user.onboarding_completed_at,
                "acquisition_source": user.acquisition_source,
                "access_status": user.access_status,
                "access_status_updated_at": user.access_status_updated_at,
                "active_pack_id": progress.active_pack_id if progress else None,
                "active_lang": progress.active_lang if progress else "en",
                "mirror_style": self.get_mirror_style(user_id),
                "interface_locale": interface_locale,
            }

    def access_profile(self, user_id: int) -> dict[str, Any] | None:
        """Return access state without creating a record for denied traffic."""
        with self.Session() as session:
            user = session.get(User, int(user_id))
            if user is None:
                return None
            interface_locale = session.execute(
                text(
                    "SELECT interface_locale FROM users "
                    "WHERE telegram_user_id = :user_id"
                ),
                {"user_id": int(user_id)},
            ).scalar_one()
            return {
                "role": user.role,
                "access_status": user.access_status,
                "access_status_updated_at": user.access_status_updated_at,
                "language_code": user.language_code,
                "interface_locale": interface_locale,
            }

    def activate_user_access(self, user_id: int) -> None:
        """Activate users admitted by public or emergency configuration."""
        with self.Session.begin() as session:
            user = session.get(User, int(user_id))
            if user is None:
                raise ValueError("Telegram user does not exist")
            if user.access_status == "blocked" and user.role != "admin":
                raise PermissionError("Blocked user access cannot be activated")
            if user.access_status != "active":
                user.access_status = "active"
                user.access_status_updated_at = utcnow()
                user.updated_at = utcnow()

    def update_product_profile(
        self,
        user_id: int,
        *,
        native_language: str | None = None,
        learning_goal: str | None = None,
        daily_word_goal: int | None = None,
        acquisition_source: str | None = None,
        complete_onboarding: bool = False,
    ) -> dict[str, Any]:
        self.ensure_user_id(user_id)
        if native_language is not None and not 2 <= len(native_language) <= 16:
            raise ValueError("Invalid native language")
        if learning_goal is not None and not 2 <= len(learning_goal) <= 32:
            raise ValueError("Invalid learning goal")
        if daily_word_goal is not None and daily_word_goal not in {5, 10, 20}:
            raise ValueError("Daily word goal must be 5, 10, or 20")
        if acquisition_source is not None and not EVENT_DIMENSION_RE.fullmatch(
            str(acquisition_source)
        ):
            raise ValueError("Invalid acquisition source")
        with self.Session.begin() as session:
            user = session.get(User, int(user_id))
            if native_language is not None:
                user.native_language = native_language
            if learning_goal is not None:
                user.learning_goal = learning_goal
            if daily_word_goal is not None:
                user.daily_word_goal = int(daily_word_goal)
            if acquisition_source and not user.acquisition_source:
                user.acquisition_source = str(acquisition_source)[:64]
            if complete_onboarding and user.onboarding_completed_at is None:
                user.onboarding_completed_at = utcnow()
            user.updated_at = utcnow()
        return self.product_profile(user_id)

    def activate_pack(
        self,
        user_id: int,
        *,
        pack_id: str,
        language: str,
        source: str,
    ) -> None:
        self.ensure_user_id(user_id)
        if not PACK_ID_RE.fullmatch(pack_id := str(pack_id)):
            raise ValueError("Invalid pack id")
        if not re.fullmatch(r"^[a-z]{2,3}$", language):
            raise ValueError("Invalid pack language")
        clean_source = str(source).strip()[:32]
        if not clean_source:
            raise ValueError("Pack enrollment source is required")
        with self.Session.begin() as session:
            rows = session.execute(
                select(UserPackEnrollment).where(
                    UserPackEnrollment.telegram_user_id == int(user_id)
                )
            ).scalars().all()
            for row in rows:
                row.active = row.pack_id == pack_id
            enrollment = session.get(UserPackEnrollment, (int(user_id), pack_id))
            if enrollment is None:
                enrollment = UserPackEnrollment(
                    telegram_user_id=int(user_id),
                    pack_id=pack_id,
                    source=clean_source,
                    active=True,
                )
                session.add(enrollment)
            else:
                enrollment.active = True
            progress = session.get(UserProgress, int(user_id))
            progress.active_pack_id = pack_id
            progress.active_lang = language
            progress.updated_at = utcnow()

    def enrolled_pack_ids(self, user_id: int) -> set[str]:
        with self.Session() as session:
            return set(
                session.execute(
                    select(UserPackEnrollment.pack_id).where(
                        UserPackEnrollment.telegram_user_id == int(user_id)
                    )
                ).scalars()
            )

    def record_event(
        self,
        user_id: int,
        event_name: str,
        *,
        properties: Mapping[str, Any] | None = None,
        session_id: str | None = None,
        source: str | None = None,
    ) -> str:
        """Store an allowlisted product event without message or prompt content."""
        if not EVENT_NAME_RE.fullmatch(event_name):
            raise ValueError("Invalid analytics event name")
        clean_properties: dict[str, Any] = {}
        for key, value in (properties or {}).items():
            normalized_key = str(key).strip().lower()
            if (
                len(clean_properties) >= 20
                or normalized_key not in EVENT_PROPERTY_KEYS
            ):
                raise ValueError("Analytics properties contain a forbidden key")
            if value is not None and type(value) not in {str, int, bool}:
                raise ValueError("Analytics properties must contain scalars")
            clean_properties[normalized_key] = (
                value[:128] if isinstance(value, str) else value
            )
        encoded = json.dumps(
            clean_properties, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        )
        if len(encoded.encode("utf-8")) > 2048:
            raise ValueError("Analytics properties are too large")
        for label, value in (("session_id", session_id), ("source", source)):
            if value is not None and not EVENT_DIMENSION_RE.fullmatch(str(value)):
                raise ValueError(f"Invalid analytics {label}")
        self.ensure_user_id(user_id)
        event_id = str(uuid4())
        with self.Session.begin() as session:
            session.add(
                AnalyticsEvent(
                    event_id=event_id,
                    telegram_user_id=int(user_id),
                    event_name=event_name,
                    session_id=str(session_id) if session_id else None,
                    source=str(source) if source else None,
                    properties_json=encoded,
                )
            )
        return event_id

    def claim_telegram_notifications(
        self,
        *,
        limit: int = 10,
        lease_seconds: int = 60,
        now: datetime | None = None,
    ) -> list[dict[str, Any]]:
        """Lease due notifications for at-least-once Telegram delivery."""
        limit = max(1, min(int(limit), 50))
        lease_seconds = max(10, min(int(lease_seconds), 300))
        observed_at = now or utcnow()
        statement = (
            select(TelegramNotification)
            .join(
                User,
                User.telegram_user_id == TelegramNotification.telegram_user_id,
            )
            .where(
                User.access_status == "active",
                User.privacy_status == "active",
                TelegramNotification.available_at <= observed_at,
                or_(
                    TelegramNotification.status == "pending",
                    and_(
                        TelegramNotification.status == "processing",
                        TelegramNotification.lease_until.is_not(None),
                        TelegramNotification.lease_until <= observed_at,
                    ),
                ),
            )
            .order_by(
                TelegramNotification.available_at,
                TelegramNotification.created_at,
            )
            .limit(limit)
        )
        if self.engine.dialect.name == "postgresql":
            statement = statement.with_for_update(
                of=TelegramNotification,
                skip_locked=True,
            )
        else:
            statement = statement.with_for_update()
        leased: list[dict[str, Any]] = []
        with self.Session.begin() as session:
            rows = session.execute(statement).scalars().all()
            for row in rows:
                row.status = "processing"
                row.attempts += 1
                row.lease_until = observed_at + timedelta(seconds=lease_seconds)
                row.updated_at = observed_at
                leased.append(
                    {
                        "notification_id": row.notification_id,
                        "telegram_user_id": row.telegram_user_id,
                        "kind": row.kind,
                        "attempts": row.attempts,
                    }
                )
        return leased

    def complete_telegram_notification(
        self, notification_id: str, *, now: datetime | None = None
    ) -> bool:
        observed_at = now or utcnow()
        with self.Session.begin() as session:
            row = session.execute(
                select(TelegramNotification)
                .where(TelegramNotification.notification_id == str(notification_id))
                .with_for_update()
            ).scalar_one_or_none()
            if row is None or row.status != "processing":
                return False
            row.status = "sent"
            row.sent_at = observed_at
            row.lease_until = None
            row.last_error_code = None
            row.updated_at = observed_at
            return True

    def retry_telegram_notification(
        self,
        notification_id: str,
        *,
        error_code: str,
        retry_seconds: int,
        maximum_attempts: int = 5,
        now: datetime | None = None,
    ) -> str:
        observed_at = now or utcnow()
        retry_seconds = max(1, min(int(retry_seconds), 3600))
        maximum_attempts = max(1, min(int(maximum_attempts), 20))
        clean_error = re.sub(r"[^A-Za-z0-9_.-]", "_", str(error_code))[:64]
        with self.Session.begin() as session:
            row = session.execute(
                select(TelegramNotification)
                .where(TelegramNotification.notification_id == str(notification_id))
                .with_for_update()
            ).scalar_one_or_none()
            if row is None or row.status != "processing":
                raise ValueError("Telegram notification is not processing")
            row.status = "failed" if row.attempts >= maximum_attempts else "pending"
            row.available_at = observed_at + timedelta(seconds=retry_seconds)
            row.lease_until = None
            row.last_error_code = clean_error or "unknown"
            row.updated_at = observed_at
            return row.status

    def cancel_telegram_notification(
        self, notification_id: str, *, now: datetime | None = None
    ) -> bool:
        observed_at = now or utcnow()
        with self.Session.begin() as session:
            row = session.execute(
                select(TelegramNotification)
                .where(TelegramNotification.notification_id == str(notification_id))
                .with_for_update()
            ).scalar_one_or_none()
            if row is None or row.status in {"sent", "failed", "cancelled"}:
                return False
            row.status = "cancelled"
            row.lease_until = None
            row.updated_at = observed_at
            return True

    def grant_consent(
        self,
        user_id: int,
        *,
        consent_type: str,
        document_version: str,
        source: str,
    ) -> bool:
        """Grant one versioned consent and return whether its state changed."""
        if consent_type not in CONSENT_TYPES:
            raise ValueError("Unknown consent type")
        if not EVENT_DIMENSION_RE.fullmatch(str(document_version)):
            raise ValueError("Invalid consent document version")
        if (
            not EVENT_DIMENSION_RE.fullmatch(str(source))
            or len(str(source)) > 32
        ):
            raise ValueError("Invalid consent source")
        self.ensure_user_id(user_id)
        with self.Session.begin() as session:
            insert_for_dialect = (
                postgresql_insert
                if self.engine.dialect.name == "postgresql"
                else sqlite_insert
            )
            observed_at = utcnow()
            created = session.execute(
                insert_for_dialect(UserConsent)
                .values(
                    consent_id=str(uuid4()),
                    telegram_user_id=int(user_id),
                    consent_type=consent_type,
                    document_version=str(document_version),
                    source=str(source),
                    granted_at=observed_at,
                    revoked_at=None,
                )
                .on_conflict_do_nothing(
                    index_elements=[
                        UserConsent.telegram_user_id,
                        UserConsent.consent_type,
                        UserConsent.document_version,
                    ]
                )
                .returning(UserConsent.consent_id)
            ).scalar_one_or_none()
            if created is not None:
                return True
            row = session.execute(
                select(UserConsent)
                .where(
                    UserConsent.telegram_user_id == int(user_id),
                    UserConsent.consent_type == consent_type,
                    UserConsent.document_version == str(document_version),
                )
                .with_for_update()
            ).scalar_one_or_none()
            if row.revoked_at is None:
                return False
            row.source = str(source)
            row.granted_at = observed_at
            row.revoked_at = None
        return True

    def has_consent(
        self,
        user_id: int,
        *,
        consent_type: str,
        document_version: str,
    ) -> bool:
        if consent_type not in CONSENT_TYPES:
            raise ValueError("Unknown consent type")
        if not EVENT_DIMENSION_RE.fullmatch(str(document_version)):
            raise ValueError("Invalid consent document version")
        with self.Session() as session:
            return bool(
                session.scalar(
                    select(func.count())
                    .select_from(UserConsent)
                    .where(
                        UserConsent.telegram_user_id == int(user_id),
                        UserConsent.consent_type == consent_type,
                        UserConsent.document_version == str(document_version),
                        UserConsent.revoked_at.is_(None),
                    )
                )
            )

    def revoke_consent(self, user_id: int, *, consent_type: str) -> int:
        """Revoke all active versions of one consent type."""
        if consent_type not in CONSENT_TYPES:
            raise ValueError("Unknown consent type")
        changed = 0
        with self.Session.begin() as session:
            rows = session.execute(
                select(UserConsent)
                .where(
                    UserConsent.telegram_user_id == int(user_id),
                    UserConsent.consent_type == consent_type,
                    UserConsent.revoked_at.is_(None),
                )
                .with_for_update()
            ).scalars().all()
            observed_at = utcnow()
            for row in rows:
                row.revoked_at = observed_at
                changed += 1
            if consent_type == "ai_processing":
                session.execute(
                    delete(MirrorDialogueTurn).where(
                        MirrorDialogueTurn.telegram_user_id == int(user_id)
                    )
                )
        return changed

    def load_profile(
        self, user_id: int, defaults: Mapping[str, Any]
    ) -> dict[str, Any]:
        self.ensure_user_id(user_id)
        with self.Session() as session:
            row = session.get(UserProgress, int(user_id))
            result = dict(defaults)
            if row is not None:
                for field in PROFILE_FIELDS:
                    result[field] = getattr(row, field)
            return result

    def save_profile(self, user_id: int, progress: Mapping[str, Any]) -> None:
        self.ensure_user_id(user_id)
        with self.Session.begin() as session:
            row = session.get(UserProgress, int(user_id))
            if row is None:
                row = UserProgress(telegram_user_id=int(user_id))
                session.add(row)
            for field, value in _profile_values(progress).items():
                setattr(row, field, value)
            row.updated_at = utcnow()

    def load_word_progress(
        self, user_id: int, language: str
    ) -> dict[str, dict[str, Any]]:
        with self.Session() as session:
            rows = (
                session.query(WordProgress)
                .filter_by(telegram_user_id=int(user_id), language=language)
                .all()
            )
            return {
                row.vocabulary_id: {
                    field: getattr(row, field) for field in WORD_PROGRESS_FIELDS
                }
                for row in rows
            }

    def _upsert_word(
        self,
        session: Any,
        user_id: int,
        language: str,
        word_index: int,
        word: Mapping[str, Any],
    ) -> None:
        term = target_text(word)
        vocabulary_id = vocabulary_id_for(word)
        key = (int(user_id), language, vocabulary_id)
        row = session.get(WordProgress, key)
        if row is None:
            row = WordProgress(
                telegram_user_id=int(user_id),
                language=language,
                vocabulary_id=vocabulary_id,
                term=term,
            )
            session.add(row)
        row.word_index = int(word_index)
        for field, value in _word_values(word).items():
            setattr(row, field, value)
        row.updated_at = utcnow()

    def save_learning_state(
        self,
        user_id: int,
        progress: Mapping[str, Any],
        language: str,
        word_index: int,
        word: Mapping[str, Any],
    ) -> None:
        """Persist one answer and the aggregate profile atomically."""
        self.ensure_user_id(user_id)
        with self.Session.begin() as session:
            profile = session.get(UserProgress, int(user_id))
            if profile is None:
                profile = UserProgress(telegram_user_id=int(user_id))
                session.add(profile)
            for field, value in _profile_values(progress).items():
                setattr(profile, field, value)
            profile.updated_at = utcnow()
            self._upsert_word(session, user_id, language, word_index, word)

    def import_legacy_state(
        self,
        user_id: int,
        progress: Mapping[str, Any],
        words_by_language: Mapping[str, list[Mapping[str, Any]]],
        *,
        import_key: str,
        details: str,
    ) -> bool:
        """Import legacy JSON exactly once for one Telegram user."""
        self.ensure_user_id(user_id)
        with self.Session.begin() as session:
            if session.get(DataImport, import_key) is not None:
                return False
            profile = session.get(UserProgress, int(user_id))
            if profile is None:
                profile = UserProgress(telegram_user_id=int(user_id))
                session.add(profile)
            for field, value in _profile_values(progress).items():
                setattr(profile, field, value)
            for language, words in words_by_language.items():
                for word_index, word in enumerate(words):
                    values = _word_values(word)
                    if values != WORD_PROGRESS_DEFAULTS:
                        self._upsert_word(
                            session, user_id, language, word_index, word
                        )
            session.add(
                DataImport(
                    import_key=import_key,
                    telegram_user_id=int(user_id),
                    details=details,
                )
            )
            return True

    def _ensure_ai_wallet(
        self, session: Any, user_id: int, *, initial_credits: int = 0
    ) -> AIWallet:
        if initial_credits < 0:
            raise ValueError("Initial AI credits cannot be negative")
        insert_for_dialect = (
            postgresql_insert
            if self.engine.dialect.name == "postgresql"
            else sqlite_insert
        )
        created = session.execute(
            insert_for_dialect(AIWallet)
            .values(
                telegram_user_id=int(user_id),
                balance_credits=int(initial_credits),
                reserved_credits=0,
                spent_credits=0,
                updated_at=utcnow(),
            )
            .on_conflict_do_nothing(index_elements=[AIWallet.telegram_user_id])
            .returning(AIWallet.telegram_user_id)
        ).scalar_one_or_none() is not None
        wallet = session.execute(
            select(AIWallet)
            .where(AIWallet.telegram_user_id == int(user_id))
            .with_for_update()
        ).scalar_one()
        if created and initial_credits:
            session.add(
                BillingCreditLedger(
                    entry_id=str(uuid4()),
                    telegram_user_id=int(user_id),
                    delta=int(initial_credits),
                    balance_after=int(initial_credits),
                    entry_type="initial_grant",
                    idempotency_key=f"initial-grant:{int(user_id)}",
                    reference_type="user",
                    reference_id=str(int(user_id)),
                    reason="Initial AI credit grant",
                    actor="system",
                )
            )
        return wallet

    @staticmethod
    def _wallet_summary(wallet: AIWallet) -> dict[str, int]:
        return {
            "available_credits": wallet.balance_credits - wallet.reserved_credits,
            "reserved_credits": wallet.reserved_credits,
            "spent_credits": wallet.spent_credits,
            "balance_credits": wallet.balance_credits,
        }

    def ai_charge_credits(self, user_id: int, configured_credits: int) -> int:
        """Return the durable role-aware credit charge for one provider action."""
        configured = int(configured_credits)
        if configured <= 0:
            raise ValueError("Configured AI credits must be positive")
        self.ensure_user_id(user_id)
        with self.Session() as session:
            role = session.execute(
                select(User.role).where(User.telegram_user_id == int(user_id))
            ).scalar_one()
        return 0 if role == "admin" else configured

    def _ensure_ai_budget_state(self, session: Any) -> AIBudgetState:
        insert_for_dialect = (
            postgresql_insert
            if self.engine.dialect.name == "postgresql"
            else sqlite_insert
        )
        session.execute(
            insert_for_dialect(AIBudgetState)
            .values(
                id=1,
                in_flight_micro_usd=0,
                breaker_open=False,
                updated_at=utcnow(),
            )
            .on_conflict_do_nothing(index_elements=[AIBudgetState.id])
        )
        return session.execute(
            select(AIBudgetState)
            .where(AIBudgetState.id == 1)
            .with_for_update()
        ).scalar_one()

    @staticmethod
    def _ai_period_start(now: datetime, *, month: bool) -> datetime:
        return datetime(
            now.year,
            now.month,
            1 if month else now.day,
            tzinfo=timezone.utc,
        )

    @staticmethod
    def _ai_actual_spend(session: Any, *, since: datetime) -> int:
        value = session.execute(
            select(func.sum(AIUsage.cost_micro_usd)).where(
                AIUsage.action.in_(METERED_PROVIDER_ACTIONS),
                or_(
                    AIUsage.provider_response_received.is_(True),
                    and_(
                        AIUsage.provider_attempts == 1,
                        AIUsage.status == "failed",
                        AIUsage.cost_is_estimate.is_(True),
                    ),
                ),
                AIUsage.provider_completed_at >= since,
            )
        ).scalar_one()
        return int(value or 0)

    @staticmethod
    def _open_ai_breaker_locked(
        state: AIBudgetState,
        *,
        reason: str,
        now: datetime | None = None,
    ) -> None:
        opened_at = now or utcnow()
        state.breaker_open = True
        state.breaker_reason = str(reason)[:128]
        state.breaker_opened_at = opened_at
        state.breaker_acknowledged_at = None
        state.breaker_acknowledged_by = None
        state.updated_at = opened_at

    @staticmethod
    def _release_ai_budget_locked(
        state: AIBudgetState,
        *,
        projected_cost_micro_usd: int,
    ) -> None:
        projected = max(0, int(projected_cost_micro_usd))
        if state.in_flight_micro_usd < projected:
            raise AIUsageStateError("AI in-flight budget cannot release reservation")
        state.in_flight_micro_usd -= projected
        state.updated_at = utcnow()

    def adjust_ai_wallet(
        self,
        user_id: int,
        *,
        delta: int,
        reason: str,
        actor: str,
        idempotency_key: str,
    ) -> dict[str, int]:
        """Apply one idempotent manual adjustment to the financial wallet."""
        if delta == 0:
            raise ValueError("Credit adjustment cannot be zero")
        if not idempotency_key or len(idempotency_key) > 255:
            raise ValueError("A valid idempotency key is required")
        with self.Session.begin() as session:
            existing_user = session.execute(
                select(User.telegram_user_id)
                .where(User.telegram_user_id == int(user_id))
                .with_for_update()
            ).scalar_one_or_none()
            if existing_user is None:
                raise ValueError("Telegram user does not exist")
            existing = session.execute(
                select(BillingCreditLedger).where(
                    BillingCreditLedger.idempotency_key == idempotency_key
                )
            ).scalar_one_or_none()
            if existing is not None:
                if existing.telegram_user_id != int(user_id):
                    raise AIUsageStateError("Idempotency key belongs to another user")
                wallet = self._ensure_ai_wallet(session, user_id)
                return self._wallet_summary(wallet)
            wallet = self._ensure_ai_wallet(session, user_id)
            balance_after = wallet.balance_credits + int(delta)
            if balance_after < wallet.reserved_credits:
                raise ValueError("Credit balance cannot cover active reservations")
            wallet.balance_credits = balance_after
            wallet.updated_at = utcnow()
            session.add(
                BillingCreditLedger(
                    entry_id=str(uuid4()),
                    telegram_user_id=int(user_id),
                    delta=int(delta),
                    balance_after=balance_after,
                    entry_type="admin_adjustment",
                    idempotency_key=idempotency_key,
                    reference_type="admin",
                    reference_id=actor[:64],
                    reason=reason[:255],
                    actor=actor[:64],
                )
            )
            session.add(
                AdminAuditLog(
                    actor=actor[:64],
                    action="ai_wallet_adjusted",
                    target_type="telegram_user",
                    target_id=str(int(user_id)),
                    details_json=json.dumps(
                        {
                            "delta": int(delta),
                            "balance_after": balance_after,
                            "idempotency_key": idempotency_key,
                        },
                        sort_keys=True,
                        separators=(",", ":"),
                    ),
                )
            )
            return self._wallet_summary(wallet)

    def reserve_ai_usage(
        self,
        user_id: int,
        *,
        action: str,
        provider: str,
        model: str,
        credits: int,
        initial_credits: int,
        context_fingerprint: str,
        max_daily_requests: int | None = None,
        requested_service_tier: str = "default",
        economics_snapshot_id: str = "legacy",
        economics_snapshot_sha256: str = "0" * 64,
        projected_cost_micro_usd: int = 0,
        max_project_cost_micro_usd_per_day: int | None = None,
        max_project_cost_micro_usd_per_month: int | None = None,
        max_in_flight_cost_micro_usd: int | None = None,
        request_id: str | None = None,
    ) -> str:
        """Atomically reserve wallet credits and create a metered request."""
        if credits < 0 or initial_credits < 0:
            raise ValueError("AI credits and allowance must be non-negative")
        if max_daily_requests is not None and max_daily_requests <= 0:
            raise ValueError("AI daily request limit must be positive")
        projected_cost = int(projected_cost_micro_usd)
        if projected_cost < 0:
            raise ValueError("AI projected request cost cannot be negative")
        budget_limits = (
            max_project_cost_micro_usd_per_day,
            max_project_cost_micro_usd_per_month,
            max_in_flight_cost_micro_usd,
        )
        if projected_cost and any(value is None for value in budget_limits):
            raise ValueError("AI project and in-flight budgets are required")
        if any(value is not None and int(value) <= 0 for value in budget_limits):
            raise ValueError("AI project and in-flight budgets must be positive")
        self.ensure_user_id(user_id)
        usage_id = request_id or str(uuid4())
        with self.Session.begin() as session:
            if session.get(AIUsage, usage_id) is not None:
                raise AIUsageStateError("AI request id already exists")
            role = session.execute(
                select(User.role)
                .where(User.telegram_user_id == int(user_id))
                .with_for_update()
            ).scalar_one()
            if credits == 0 and role != "admin":
                raise ValueError("Zero-credit AI reservations require admin role")
            budget_state = self._ensure_ai_budget_state(session)
            if projected_cost:
                if budget_state.breaker_open:
                    raise AIQuotaExceeded("AI cost circuit breaker is open")
                now = utcnow()
                day_spend = self._ai_actual_spend(
                    session,
                    since=self._ai_period_start(now, month=False),
                )
                month_spend = self._ai_actual_spend(
                    session,
                    since=self._ai_period_start(now, month=True),
                )
                projected_total = budget_state.in_flight_micro_usd + projected_cost
                if projected_total > int(max_in_flight_cost_micro_usd or 0):
                    raise AIQuotaExceeded("AI in-flight project budget reached")
                if (
                    day_spend + projected_total
                    > int(max_project_cost_micro_usd_per_day or 0)
                ):
                    raise AIQuotaExceeded("AI daily project budget reached")
                if (
                    month_spend + projected_total
                    > int(max_project_cost_micro_usd_per_month or 0)
                ):
                    raise AIQuotaExceeded("AI monthly project budget reached")
            wallet = self._ensure_ai_wallet(
                session, user_id, initial_credits=initial_credits
            )
            if max_daily_requests is not None:
                attempts = session.execute(
                    select(func.count(AIUsage.request_id)).where(
                        AIUsage.telegram_user_id == int(user_id),
                        AIUsage.action == str(action),
                        AIUsage.created_at >= utcnow() - timedelta(hours=24),
                    )
                ).scalar_one()
                if int(attempts) >= int(max_daily_requests):
                    raise AIQuotaExceeded("AI daily request limit reached")
            if wallet.balance_credits - wallet.reserved_credits < credits:
                raise AICreditExhausted("AI credit allowance exhausted")
            wallet.reserved_credits += credits
            wallet.updated_at = utcnow()
            budget_state.in_flight_micro_usd += projected_cost
            budget_state.updated_at = utcnow()
            session.add(
                AIUsage(
                    request_id=usage_id,
                    telegram_user_id=int(user_id),
                    action=action,
                    provider=provider,
                    model=model,
                    requested_service_tier=str(requested_service_tier)[:32],
                    economics_snapshot_id=str(economics_snapshot_id)[:128],
                    economics_snapshot_sha256=str(economics_snapshot_sha256)[:64],
                    status="reserved",
                    context_fingerprint=context_fingerprint,
                    reserved_credits=credits,
                    projected_cost_micro_usd=projected_cost,
                )
            )
        return usage_id

    def mark_ai_provider_attempt_started(self, request_id: str) -> None:
        """Persist the single provider attempt before network I/O begins."""
        with self.Session.begin() as session:
            row = session.execute(
                select(AIUsage)
                .where(AIUsage.request_id == str(request_id))
                .with_for_update()
            ).scalar_one_or_none()
            if row is None or row.status != "reserved":
                raise AIUsageStateError("AI request is not reserved")
            if row.provider_attempts != 0:
                raise AIUsageStateError("AI request already has a provider attempt")
            row.provider_attempts = 1

    def record_ai_provider_response(
        self,
        request_id: str,
        *,
        provider_response_id: str | None,
        model: str,
        service_tier: str,
        provider_status: str,
        usage: Mapping[str, int],
        cost_micro_usd: int,
        latency_ms: int,
        expected_model: str,
        expected_service_tier: str,
        retrospective_breaker_micro_usd: int,
    ) -> dict[str, Any]:
        """Durably record billable response telemetry before output validation."""
        if retrospective_breaker_micro_usd <= 0:
            raise ValueError("AI retrospective breaker must be positive")
        now = utcnow()
        with self.Session.begin() as session:
            state = self._ensure_ai_budget_state(session)
            row = session.execute(
                select(AIUsage)
                .where(AIUsage.request_id == str(request_id))
                .with_for_update()
            ).scalar_one_or_none()
            if row is None or row.status != "reserved":
                raise AIUsageStateError("AI request is not reserved")
            if row.provider_attempts != 1:
                raise AIUsageStateError("AI provider attempt was not started")
            if row.provider_response_received:
                if row.provider_response_id != provider_response_id:
                    raise AIUsageStateError("AI provider response already differs")
                return {
                    "breaker_open": bool(state.breaker_open),
                    "breaker_reason": state.breaker_reason,
                }
            row.provider_response_received = True
            row.provider_response_id = provider_response_id
            row.model = str(model)[:128]
            row.returned_service_tier = str(service_tier)[:32]
            row.provider_status = str(provider_status)[:32]
            for field in (
                "input_tokens",
                "cached_input_tokens",
                "cache_write_tokens",
                "output_tokens",
                "reasoning_tokens",
                "total_tokens",
            ):
                setattr(row, field, max(0, int(usage.get(field, 0))))
            row.cost_micro_usd = max(0, int(cost_micro_usd))
            row.cost_is_estimate = False
            row.latency_ms = max(0, int(latency_ms))
            row.provider_completed_at = now

            breaker_reason = None
            if str(model) != str(expected_model):
                breaker_reason = "returned_model_mismatch"
            elif str(service_tier) != str(expected_service_tier):
                breaker_reason = "returned_service_tier_mismatch"
            elif row.cost_micro_usd > int(retrospective_breaker_micro_usd):
                breaker_reason = "provider_response_cost_outlier"
            if breaker_reason:
                self._open_ai_breaker_locked(
                    state,
                    reason=breaker_reason,
                    now=now,
                )
            return {
                "breaker_open": bool(state.breaker_open),
                "breaker_reason": state.breaker_reason,
            }

    def reconcile_ai_provider_response(
        self,
        record: Mapping[str, Any],
        *,
        actor: str,
    ) -> bool:
        """Import one privacy-safe fallback record without closing the breaker."""
        request_id = str(record.get("request_id") or "").strip()
        actor = str(actor).strip()
        if not request_id or not actor:
            raise ValueError("AI metering reconciliation requires request and actor")
        with self.Session.begin() as session:
            state = self._ensure_ai_budget_state(session)
            row = session.execute(
                select(AIUsage)
                .where(AIUsage.request_id == request_id)
                .with_for_update()
            ).scalar_one_or_none()
            if row is None or row.status not in {"reserved", "failed"}:
                raise AIUsageStateError(
                    "AI metering journal request cannot be reconciled"
                )
            response_id_value = record.get("provider_response_id")
            response_id = (
                str(response_id_value)[:128]
                if response_id_value is not None
                else None
            )
            model = str(record.get("model") or "")[:128]
            service_tier = str(record.get("service_tier") or "")[:32]
            provider_status = str(record.get("provider_status") or "")[:32]
            cost_micro_usd = max(0, int(record.get("cost_micro_usd") or 0))
            if not model or not service_tier or not provider_status:
                raise ValueError("AI metering journal response identity is incomplete")
            if row.provider_response_received:
                if (
                    row.provider_response_id != response_id
                    or row.model != model
                    or row.returned_service_tier != service_tier
                    or row.cost_micro_usd != cost_micro_usd
                ):
                    raise AIUsageStateError(
                        "AI metering journal conflicts with stored response"
                    )
                return False
            if row.provider_attempts != 1:
                raise AIUsageStateError(
                    "AI metering journal request has no provider attempt"
                )
            row.provider_response_received = True
            row.provider_response_id = response_id
            row.model = model
            row.returned_service_tier = service_tier
            row.provider_status = provider_status
            for field in (
                "input_tokens",
                "cached_input_tokens",
                "cache_write_tokens",
                "output_tokens",
                "reasoning_tokens",
                "total_tokens",
            ):
                setattr(row, field, max(0, int(record.get(field) or 0)))
            row.cost_micro_usd = cost_micro_usd
            row.cost_is_estimate = False
            row.latency_ms = max(0, int(record.get("latency_ms") or 0))
            row.provider_completed_at = utcnow()
            self._open_ai_breaker_locked(
                state,
                reason="provider_telemetry_reconciled",
            )
            session.add(
                AdminAuditLog(
                    actor=actor[:64],
                    action="ai_metering_reconciled",
                    target_type="ai_usage",
                    target_id=request_id,
                    details_json=json.dumps(
                        {
                            "cost_micro_usd": cost_micro_usd,
                            "model": model,
                            "provider_status": provider_status,
                            "service_tier": service_tier,
                        },
                        sort_keys=True,
                        separators=(",", ":"),
                    ),
                )
            )
            return True

    def complete_ai_usage(
        self,
        request_id: str,
        *,
        billed_credits: int,
        provider_response_id: str | None,
        model: str,
        usage: Mapping[str, int],
        cost_micro_usd: int,
        latency_ms: int,
        returned_service_tier: str | None = None,
        provider_status: str | None = None,
    ) -> dict[str, int]:
        """Settle a successful AI request and refund any unused reservation."""
        with self.Session.begin() as session:
            budget_state = self._ensure_ai_budget_state(session)
            row = session.execute(
                select(AIUsage)
                .where(AIUsage.request_id == request_id)
                .with_for_update()
            ).scalar_one_or_none()
            return self._settle_ai_usage_locked(
                session,
                row,
                request_id=request_id,
                billed_credits=billed_credits,
                provider_response_id=provider_response_id,
                model=model,
                usage=usage,
                cost_micro_usd=cost_micro_usd,
                latency_ms=latency_ms,
                returned_service_tier=returned_service_tier,
                provider_status=provider_status,
                budget_state=budget_state,
            )

    def _settle_ai_usage_locked(
        self,
        session: Any,
        row: AIUsage | None,
        *,
        request_id: str,
        billed_credits: int,
        provider_response_id: str | None,
        model: str,
        usage: Mapping[str, int],
        cost_micro_usd: int,
        latency_ms: int,
        budget_state: AIBudgetState,
        returned_service_tier: str | None = None,
        provider_status: str | None = None,
    ) -> dict[str, int]:
        if row is None or row.status != "reserved":
            raise AIUsageStateError("AI request is not reserved")
        if row.action == "block_tutor" and (
            row.provider_attempts != 1 or not row.provider_response_received
        ):
            raise AIUsageStateError(
                "AI tutor response telemetry must be recorded before settlement"
            )
        if row.action == "block_tutor":
            settled_usage = {
                field: max(0, int(usage.get(field, 0)))
                for field in (
                    "input_tokens",
                    "cached_input_tokens",
                    "cache_write_tokens",
                    "output_tokens",
                    "reasoning_tokens",
                    "total_tokens",
                )
            }
            recorded_usage = {
                field: int(getattr(row, field)) for field in settled_usage
            }
            telemetry_matches = (
                row.provider_response_id == provider_response_id
                and row.model == str(model)
                and recorded_usage == settled_usage
                and row.cost_micro_usd == max(0, int(cost_micro_usd))
                and row.latency_ms == max(0, int(latency_ms))
                and (
                    returned_service_tier is None
                    or row.returned_service_tier == str(returned_service_tier)
                )
                and (
                    provider_status is None
                    or row.provider_status == str(provider_status)
                )
            )
            if not telemetry_matches:
                raise AIUsageStateError(
                    "AI tutor settlement cannot alter provider telemetry"
                )
        if not 0 <= billed_credits <= row.reserved_credits:
            raise ValueError("Billed credits must fit the reservation")
        wallet = session.execute(
            select(AIWallet)
            .where(AIWallet.telegram_user_id == row.telegram_user_id)
            .with_for_update()
        ).scalar_one()
        if wallet.reserved_credits < row.reserved_credits:
            raise AIUsageStateError("AI wallet cannot settle reservation")
        self._release_ai_budget_locked(
            budget_state,
            projected_cost_micro_usd=row.projected_cost_micro_usd,
        )
        wallet.reserved_credits -= row.reserved_credits
        wallet.balance_credits -= billed_credits
        wallet.spent_credits += billed_credits
        wallet.updated_at = utcnow()
        if billed_credits:
            session.add(
                BillingCreditLedger(
                    entry_id=str(uuid4()),
                    telegram_user_id=row.telegram_user_id,
                    delta=-billed_credits,
                    balance_after=wallet.balance_credits,
                    entry_type="ai_usage",
                    idempotency_key=f"ai-usage:{request_id}",
                    reference_type="ai_usage",
                    reference_id=request_id,
                    reason=f"AI action: {row.action}"[:255],
                    actor="system",
                )
            )
        row.status = "completed"
        row.billed_credits = billed_credits
        row.provider_response_id = provider_response_id
        row.model = model
        if returned_service_tier is not None:
            row.returned_service_tier = str(returned_service_tier)[:32]
        if provider_status is not None:
            row.provider_status = str(provider_status)[:32]
        for field in (
            "input_tokens",
            "cached_input_tokens",
            "cache_write_tokens",
            "output_tokens",
            "reasoning_tokens",
            "total_tokens",
        ):
            setattr(row, field, max(0, int(usage.get(field, 0))))
        row.cost_micro_usd = max(0, int(cost_micro_usd))
        row.cost_is_estimate = False
        row.latency_ms = max(0, int(latency_ms))
        row.provider_response_received = True
        row.provider_completed_at = row.provider_completed_at or utcnow()
        row.completed_at = utcnow()
        return self._wallet_summary(wallet)

    def complete_voice_usage(
        self,
        *,
        request_id: str,
        session_id: str,
        user_id: int,
        turn_id: str,
        expected_vocabulary_id: str,
        matched_vocabulary_id: str | None,
        transcript: str,
        feedback_code: str,
        similarity_bps: int,
        transcript_expires_at: datetime,
        billed_credits: int,
        provider_response_id: str | None,
        model: str,
        usage: Mapping[str, int],
        cost_micro_usd: int,
        latency_ms: int,
    ) -> dict[str, Any]:
        """Atomically settle STT credits, persist a turn, and advance accepted speech."""
        if feedback_code not in {"exact", "close", "retry"}:
            raise ValueError("Unknown voice feedback code")
        transcript = str(transcript).strip()
        if not 1 <= len(transcript) <= 1000:
            raise ValueError("Voice transcript must contain 1-1000 characters")
        if not 0 <= int(similarity_bps) <= 10000:
            raise ValueError("Voice similarity is outside valid bounds")
        with self.Session.begin() as session:
            budget_state = self._ensure_ai_budget_state(session)
            usage_row = session.execute(
                select(AIUsage)
                .where(AIUsage.request_id == str(request_id))
                .with_for_update()
            ).scalar_one_or_none()
            if (
                usage_row is None
                or usage_row.telegram_user_id != int(user_id)
                or usage_row.action != "voice_transcription"
            ):
                raise AIUsageStateError("Voice AI reservation does not match the user")
            voice_session = session.execute(
                select(VoiceSession)
                .where(VoiceSession.session_id == str(session_id))
                .with_for_update()
            ).scalar_one_or_none()
            if (
                voice_session is None
                or voice_session.telegram_user_id != int(user_id)
                or voice_session.status != "active"
            ):
                raise AIUsageStateError("Voice session is not active")
            session_expiry = voice_session.expires_at
            if session_expiry.tzinfo is None:
                session_expiry = session_expiry.replace(tzinfo=timezone.utc)
            if session_expiry <= utcnow():
                raise AIUsageStateError("Voice session expired before completion")
            transcript_expiry = transcript_expires_at
            if transcript_expiry.tzinfo is None:
                transcript_expiry = transcript_expiry.replace(tzinfo=timezone.utc)
            if transcript_expiry <= utcnow():
                raise ValueError("Voice transcript expiry must be in the future")
            expected_ids = json.loads(voice_session.vocabulary_ids_json)
            if (
                not isinstance(expected_ids, list)
                or voice_session.next_position >= len(expected_ids)
                or expected_ids[voice_session.next_position]
                != str(expected_vocabulary_id)
            ):
                raise AIUsageStateError("Voice session position changed")
            allowance = self._settle_ai_usage_locked(
                session,
                usage_row,
                request_id=request_id,
                billed_credits=billed_credits,
                provider_response_id=provider_response_id,
                model=model,
                usage=usage,
                cost_micro_usd=cost_micro_usd,
                latency_ms=latency_ms,
                budget_state=budget_state,
            )
            session.add(
                VoiceTurn(
                    turn_id=str(turn_id),
                    session_id=voice_session.session_id,
                    telegram_user_id=int(user_id),
                    request_id=str(request_id),
                    expected_vocabulary_id=str(expected_vocabulary_id),
                    matched_vocabulary_id=(
                        str(matched_vocabulary_id)
                        if matched_vocabulary_id
                        else None
                    ),
                    transcript=transcript,
                    feedback_code=feedback_code,
                    similarity_bps=int(similarity_bps),
                    expires_at=transcript_expiry,
                )
            )
            voice_session.turn_count += 1
            if feedback_code != "retry":
                voice_session.next_position += 1
            voice_session.updated_at = utcnow()
            if voice_session.next_position >= len(expected_ids):
                voice_session.status = "completed"
                voice_session.ended_at = utcnow()
            return {
                **allowance,
                "session_status": voice_session.status,
                "next_position": voice_session.next_position,
            }

    def fail_ai_usage(
        self,
        request_id: str,
        *,
        error_code: str,
        open_breaker_reason: str | None = None,
    ) -> bool:
        """Release a reservation after provider, validation, or storage failure."""
        with self.Session.begin() as session:
            budget_state = self._ensure_ai_budget_state(session)
            row = session.execute(
                select(AIUsage)
                .where(AIUsage.request_id == request_id)
                .with_for_update()
            ).scalar_one_or_none()
            if row is None or row.status != "reserved":
                return False
            wallet = session.execute(
                select(AIWallet)
                .where(AIWallet.telegram_user_id == row.telegram_user_id)
                .with_for_update()
            ).scalar_one()
            if wallet.reserved_credits < row.reserved_credits:
                raise AIUsageStateError("AI wallet cannot release reservation")
            self._release_ai_budget_locked(
                budget_state,
                projected_cost_micro_usd=row.projected_cost_micro_usd,
            )
            wallet.reserved_credits -= row.reserved_credits
            wallet.updated_at = utcnow()
            row.status = "failed"
            row.error_code = error_code[:128]
            row.completed_at = utcnow()
            if row.provider_attempts and not row.provider_response_received:
                row.provider_status = "unknown_failure"
                row.cost_micro_usd = row.projected_cost_micro_usd
                row.cost_is_estimate = True
                row.provider_completed_at = utcnow()
            if open_breaker_reason:
                self._open_ai_breaker_locked(
                    budget_state,
                    reason=open_breaker_reason,
                )
            return True

    def recover_stale_ai_usage(
        self, *, timeout_seconds: int, user_id: int | None = None
    ) -> int:
        """Release reservations left behind by a terminated worker."""
        if timeout_seconds <= 0:
            raise ValueError("AI reservation timeout must be positive")
        cutoff = utcnow() - timedelta(seconds=int(timeout_seconds))
        with self.Session.begin() as session:
            budget_state = self._ensure_ai_budget_state(session)
            conditions = [
                AIUsage.status == "reserved",
                AIUsage.created_at <= cutoff,
            ]
            if user_id is not None:
                conditions.append(AIUsage.telegram_user_id == int(user_id))
            statement = (
                select(AIUsage)
                .where(*conditions)
                .order_by(AIUsage.created_at, AIUsage.request_id)
            )
            if self.engine.dialect.name == "postgresql":
                statement = statement.with_for_update(skip_locked=True)
            else:
                statement = statement.with_for_update()
            rows = session.execute(statement).scalars().all()
            recovered_at = utcnow()
            for row in rows:
                wallet = session.execute(
                    select(AIWallet)
                    .where(AIWallet.telegram_user_id == row.telegram_user_id)
                    .with_for_update()
                ).scalar_one_or_none()
                if (
                    wallet is None
                    or wallet.reserved_credits < row.reserved_credits
                ):
                    raise AIUsageStateError(
                        "AI wallet cannot release stale reservation"
                    )
                wallet.reserved_credits -= row.reserved_credits
                wallet.updated_at = recovered_at
                self._release_ai_budget_locked(
                    budget_state,
                    projected_cost_micro_usd=row.projected_cost_micro_usd,
                )
                row.status = "failed"
                row.error_code = "stale_reservation_timeout"
                row.completed_at = recovered_at
                if row.provider_attempts and not row.provider_response_received:
                    row.provider_status = "unknown_failure"
                    row.cost_micro_usd = row.projected_cost_micro_usd
                    row.cost_is_estimate = True
                    row.provider_completed_at = recovered_at
                    self._open_ai_breaker_locked(
                        budget_state,
                        reason="stale_provider_attempt_unknown",
                        now=recovered_at,
                    )
            return len(rows)

    def open_ai_breaker(self, *, reason: str) -> None:
        with self.Session.begin() as session:
            state = self._ensure_ai_budget_state(session)
            self._open_ai_breaker_locked(state, reason=reason)

    def ai_budget_status(self) -> dict[str, Any]:
        now = utcnow()
        with self.Session.begin() as session:
            state = self._ensure_ai_budget_state(session)
            reserved_attempts = session.execute(
                select(func.count(AIUsage.request_id)).where(
                    AIUsage.action.in_(METERED_PROVIDER_ACTIONS),
                    AIUsage.status == "reserved",
                )
            ).scalar_one()
            return {
                "in_flight_micro_usd": int(state.in_flight_micro_usd),
                "spent_today_micro_usd": self._ai_actual_spend(
                    session,
                    since=self._ai_period_start(now, month=False),
                ),
                "spent_month_micro_usd": self._ai_actual_spend(
                    session,
                    since=self._ai_period_start(now, month=True),
                ),
                "reserved_attempts": int(reserved_attempts or 0),
                "breaker_open": bool(state.breaker_open),
                "breaker_reason": state.breaker_reason,
                "breaker_opened_at": state.breaker_opened_at,
                "breaker_acknowledged_at": state.breaker_acknowledged_at,
                "breaker_acknowledged_by": state.breaker_acknowledged_by,
            }

    def reset_ai_breaker(self, *, actor: str, reason: str) -> bool:
        actor = str(actor).strip()
        reason = str(reason).strip()
        if not actor or not 3 <= len(reason) <= 255:
            raise ValueError("AI breaker reset requires actor and reason")
        with self.Session.begin() as session:
            state = self._ensure_ai_budget_state(session)
            if not state.breaker_open:
                return False
            reserved_attempts = session.execute(
                select(func.count(AIUsage.request_id)).where(
                    AIUsage.action.in_(METERED_PROVIDER_ACTIONS),
                    AIUsage.status == "reserved",
                )
            ).scalar_one()
            if int(reserved_attempts or 0):
                raise AIUsageStateError(
                    "AI breaker cannot reset while attempts are in flight"
                )
            previous_reason = state.breaker_reason
            now = utcnow()
            state.breaker_open = False
            state.breaker_reason = None
            state.breaker_acknowledged_at = now
            state.breaker_acknowledged_by = actor[:64]
            state.updated_at = now
            session.add(
                AdminAuditLog(
                    actor=actor[:64],
                    action="ai_breaker_reset",
                    target_type="ai_budget",
                    target_id="1",
                    details_json=json.dumps(
                        {
                            "previous_reason": previous_reason,
                            "reset_reason": reason,
                        },
                        sort_keys=True,
                        separators=(",", ":"),
                    ),
                )
            )
            return True

    def ai_usage_summary(
        self, user_id: int, *, initial_credits: int = 0
    ) -> dict[str, int]:
        """Return learner-visible allowance and aggregate technical usage."""
        with self.Session() as session:
            wallet = session.get(AIWallet, int(user_id))
            aggregate = session.execute(
                select(
                    func.count(AIUsage.request_id),
                    func.sum(case((AIUsage.status == "completed", 1), else_=0)),
                    func.sum(case((AIUsage.status == "failed", 1), else_=0)),
                    func.sum(AIUsage.total_tokens),
                    func.sum(AIUsage.cost_micro_usd),
                ).where(AIUsage.telegram_user_id == int(user_id))
            ).one()
            return {
                "available_credits": (
                    wallet.balance_credits - wallet.reserved_credits
                    if wallet
                    else initial_credits
                ),
                "reserved_credits": wallet.reserved_credits if wallet else 0,
                "spent_credits": wallet.spent_credits if wallet else 0,
                "balance_credits": wallet.balance_credits if wallet else initial_credits,
                "requests": int(aggregate[0] or 0),
                "completed_requests": int(aggregate[1] or 0),
                "failed_requests": int(aggregate[2] or 0),
                "total_tokens": int(aggregate[3] or 0),
                "cost_micro_usd": int(aggregate[4] or 0),
            }

    def get_ai_usage(self, request_id: str) -> dict[str, Any] | None:
        """Return one technical usage row without prompt or response content."""
        with self.Session() as session:
            row = session.get(AIUsage, request_id)
            if row is None:
                return None
            return {
                column.name: getattr(row, column.name)
                for column in AIUsage.__table__.columns
            }
