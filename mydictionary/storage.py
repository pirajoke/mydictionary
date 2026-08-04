"""Transactional multi-user persistence for learner progress."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Mapping
from uuid import uuid4

from alembic import command
from alembic.config import Config
from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    case,
    create_engine,
    func,
    select,
)
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

from mydictionary.catalog import PACK_ID_RE


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


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def vocabulary_id_for(word: Mapping[str, Any]) -> str:
    """Return position-independent identity for one bilingual entry."""
    term = str(word.get("en", "")).strip()
    meaning = str(word.get("ru", "")).strip()
    if not term or not meaning:
        raise ValueError("Vocabulary entries require target and Russian text")
    identity = json.dumps(
        [term, meaning], ensure_ascii=False, separators=(",", ":")
    )
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

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
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    context_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    reserved_credits: Mapped[int] = mapped_column(Integer, default=0)
    billed_credits: Mapped[int] = mapped_column(Integer, default=0)
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


class AIQuotaExceeded(RuntimeError):
    """Raised when a learner has no pilot AI credits available."""


class AIUsageStateError(RuntimeError):
    """Raised when an AI usage transition is invalid or duplicated."""


USER_ROLES = {"learner", "admin"}
ACCESS_STATUSES = {"pending", "active", "blocked"}
EVENT_NAME_RE = re.compile(r"^[a-z][a-z0-9_]{1,63}$")
EVENT_PROPERTY_KEYS = {
    "correct_count",
    "daily_word_goal",
    "goal",
    "language",
    "mode",
    "pack_id",
    "retry",
    "topic",
    "word_count",
    "word_index",
    "wrong_count",
}
EVENT_DIMENSION_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}$")


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

    def product_profile(self, user_id: int) -> dict[str, Any]:
        self.ensure_user_id(user_id)
        with self.Session() as session:
            user = session.get(User, int(user_id))
            progress = session.get(UserProgress, int(user_id))
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
            }

    def access_profile(self, user_id: int) -> dict[str, Any] | None:
        """Return access state without creating a record for denied traffic."""
        with self.Session() as session:
            user = session.get(User, int(user_id))
            if user is None:
                return None
            return {
                "role": user.role,
                "access_status": user.access_status,
                "access_status_updated_at": user.access_status_updated_at,
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
        term = str(word.get("en", "")).strip()
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
        request_id: str | None = None,
    ) -> str:
        """Atomically reserve pilot credits and create a metered request."""
        if credits <= 0 or initial_credits < 0:
            raise ValueError("AI credits must be positive and allowance non-negative")
        self.ensure_user_id(user_id)
        usage_id = request_id or str(uuid4())
        with self.Session.begin() as session:
            if session.get(AIUsage, usage_id) is not None:
                raise AIUsageStateError("AI request id already exists")
            allowance_values = {
                "telegram_user_id": int(user_id),
                "available_credits": int(initial_credits),
                "reserved_credits": 0,
                "spent_credits": 0,
                "updated_at": utcnow(),
            }
            insert_for_dialect = (
                postgresql_insert
                if self.engine.dialect.name == "postgresql"
                else sqlite_insert
            )
            session.execute(
                insert_for_dialect(AIAllowance)
                .values(**allowance_values)
                .on_conflict_do_nothing(
                    index_elements=[AIAllowance.telegram_user_id]
                )
            )
            allowance = session.execute(
                select(AIAllowance)
                .where(AIAllowance.telegram_user_id == int(user_id))
                .with_for_update()
            ).scalar_one()
            if allowance.available_credits < credits:
                raise AIQuotaExceeded("AI credit allowance exhausted")
            allowance.available_credits -= credits
            allowance.reserved_credits += credits
            allowance.updated_at = utcnow()
            session.add(
                AIUsage(
                    request_id=usage_id,
                    telegram_user_id=int(user_id),
                    action=action,
                    provider=provider,
                    model=model,
                    status="reserved",
                    context_fingerprint=context_fingerprint,
                    reserved_credits=credits,
                )
            )
        return usage_id

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
    ) -> dict[str, int]:
        """Settle a successful AI request and refund any unused reservation."""
        with self.Session.begin() as session:
            row = session.execute(
                select(AIUsage)
                .where(AIUsage.request_id == request_id)
                .with_for_update()
            ).scalar_one_or_none()
            if row is None or row.status != "reserved":
                raise AIUsageStateError("AI request is not reserved")
            if not 0 <= billed_credits <= row.reserved_credits:
                raise ValueError("Billed credits must fit the reservation")
            allowance = session.execute(
                select(AIAllowance)
                .where(AIAllowance.telegram_user_id == row.telegram_user_id)
                .with_for_update()
            ).scalar_one()
            allowance.reserved_credits -= row.reserved_credits
            allowance.available_credits += row.reserved_credits - billed_credits
            allowance.spent_credits += billed_credits
            allowance.updated_at = utcnow()

            row.status = "completed"
            row.billed_credits = billed_credits
            row.provider_response_id = provider_response_id
            row.model = model
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
            row.latency_ms = max(0, int(latency_ms))
            row.completed_at = utcnow()
            result = {
                "available_credits": allowance.available_credits,
                "reserved_credits": allowance.reserved_credits,
                "spent_credits": allowance.spent_credits,
            }
        return result

    def fail_ai_usage(self, request_id: str, *, error_code: str) -> bool:
        """Release a reservation after provider, validation, or storage failure."""
        with self.Session.begin() as session:
            row = session.execute(
                select(AIUsage)
                .where(AIUsage.request_id == request_id)
                .with_for_update()
            ).scalar_one_or_none()
            if row is None or row.status != "reserved":
                return False
            allowance = session.execute(
                select(AIAllowance)
                .where(AIAllowance.telegram_user_id == row.telegram_user_id)
                .with_for_update()
            ).scalar_one()
            allowance.reserved_credits -= row.reserved_credits
            allowance.available_credits += row.reserved_credits
            allowance.updated_at = utcnow()
            row.status = "failed"
            row.error_code = error_code[:128]
            row.completed_at = utcnow()
            return True

    def recover_stale_ai_usage(
        self, *, timeout_seconds: int, user_id: int | None = None
    ) -> int:
        """Release reservations left behind by a terminated worker."""
        if timeout_seconds <= 0:
            raise ValueError("AI reservation timeout must be positive")
        cutoff = utcnow() - timedelta(seconds=int(timeout_seconds))
        with self.Session.begin() as session:
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
                allowance = session.execute(
                    select(AIAllowance)
                    .where(
                        AIAllowance.telegram_user_id == row.telegram_user_id
                    )
                    .with_for_update()
                ).scalar_one_or_none()
                if (
                    allowance is None
                    or allowance.reserved_credits < row.reserved_credits
                ):
                    raise AIUsageStateError(
                        "AI allowance cannot release stale reservation"
                    )
                allowance.reserved_credits -= row.reserved_credits
                allowance.available_credits += row.reserved_credits
                allowance.updated_at = recovered_at
                row.status = "failed"
                row.error_code = "stale_reservation_timeout"
                row.completed_at = recovered_at
            return len(rows)

    def ai_usage_summary(
        self, user_id: int, *, initial_credits: int = 0
    ) -> dict[str, int]:
        """Return learner-visible allowance and aggregate technical usage."""
        with self.Session() as session:
            allowance = session.get(AIAllowance, int(user_id))
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
                    allowance.available_credits if allowance else initial_credits
                ),
                "reserved_credits": allowance.reserved_credits if allowance else 0,
                "spent_credits": allowance.spent_credits if allowance else 0,
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
