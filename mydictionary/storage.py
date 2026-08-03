"""Transactional multi-user persistence for learner progress."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
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


class AIQuotaExceeded(RuntimeError):
    """Raised when a learner has no pilot AI credits available."""


class AIUsageStateError(RuntimeError):
    """Raised when an AI usage transition is invalid or duplicated."""


def run_migrations(database_url: str) -> None:
    """Upgrade a database using the repository's versioned Alembic migrations."""
    root = Path(__file__).resolve().parents[1]
    config = Config(str(root / "alembic.ini"))
    config.set_main_option("script_location", str(root / "migrations"))
    config.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))
    command.upgrade(config, "head")


def _profile_values(progress: Mapping[str, Any]) -> dict[str, Any]:
    return {field: progress.get(field) for field in PROFILE_FIELDS}


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

    def ensure_user(self, telegram_user: Any) -> None:
        user_id = int(telegram_user.id)
        with self.Session.begin() as session:
            user = session.get(User, user_id)
            if user is None:
                user = User(telegram_user_id=user_id)
                session.add(user)
            for field in ("username", "first_name", "last_name", "language_code"):
                value = getattr(telegram_user, field, None)
                if value is not None:
                    setattr(user, field, str(value))
            user.updated_at = utcnow()
            if session.get(UserProgress, user_id) is None:
                session.add(UserProgress(telegram_user_id=user_id))

    def ensure_user_id(self, user_id: int) -> None:
        telegram_user = type("TelegramUser", (), {"id": int(user_id)})()
        self.ensure_user(telegram_user)

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
