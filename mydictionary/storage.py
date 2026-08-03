"""Transactional multi-user persistence for learner progress."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from alembic import command
from alembic.config import Config
from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    create_engine,
)
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
    word_index: Mapped[int] = mapped_column(Integer, primary_key=True)
    term: Mapped[str] = mapped_column(String(512))
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
    ) -> dict[int, dict[str, Any]]:
        with self.Session() as session:
            rows = (
                session.query(WordProgress)
                .filter_by(telegram_user_id=int(user_id), language=language)
                .all()
            )
            return {
                row.word_index: {
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
        key = (int(user_id), language, int(word_index))
        row = session.get(WordProgress, key)
        if row is None:
            row = WordProgress(
                telegram_user_id=int(user_id),
                language=language,
                word_index=int(word_index),
                term=str(word.get("en", "")),
            )
            session.add(row)
        row.term = str(word.get("en", row.term))
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
