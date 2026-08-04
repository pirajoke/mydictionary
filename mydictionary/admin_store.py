"""Database queries and transactional actions used by the admin console."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from typing import Any, Mapping
from uuid import uuid4

from sqlalchemy import String, cast, func, or_, select
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from mydictionary.bot_profile import BOT_PROFILE_DEFAULTS
from mydictionary.storage import (
    AIAllowance,
    AICreditLedger,
    AIUsage,
    AdminAuditLog,
    AdminCredential,
    AppSetting,
    DatabaseStore,
    User,
    UserProgress,
    WordProgress,
    utcnow,
)


def _json(value: Mapping[str, Any] | None) -> str:
    return json.dumps(value or {}, ensure_ascii=False, sort_keys=True)


def _name(user: User) -> str:
    full_name = " ".join(
        part for part in (user.first_name, user.last_name) if part
    ).strip()
    return full_name or (f"@{user.username}" if user.username else "Без имени")


class AdminStore:
    def __init__(self, store: DatabaseStore):
        self.store = store

    def get_settings(self) -> dict[str, str]:
        with self.store.Session() as session:
            rows = session.execute(select(AppSetting)).scalars().all()
        result = dict(BOT_PROFILE_DEFAULTS)
        result.update({row.key: row.value for row in rows})
        return result

    def update_settings(
        self, values: Mapping[str, str], *, actor: str
    ) -> dict[str, str]:
        allowed = set(BOT_PROFILE_DEFAULTS)
        unknown = set(values) - allowed
        if unknown:
            raise ValueError(f"Unknown settings: {', '.join(sorted(unknown))}")
        changed: list[str] = []
        with self.store.Session.begin() as session:
            for key, value in values.items():
                row = session.get(AppSetting, key)
                if row is None:
                    row = AppSetting(
                        key=key,
                        value=str(value),
                        updated_by=actor,
                    )
                    session.add(row)
                    changed.append(key)
                elif row.value != str(value):
                    row.value = str(value)
                    row.updated_by = actor
                    row.updated_at = utcnow()
                    changed.append(key)
            if changed:
                session.add(
                    AdminAuditLog(
                        actor=actor,
                        action="bot_profile_updated",
                        target_type="settings",
                        target_id="bot_profile",
                        details_json=_json({"fields": changed}),
                    )
                )
        return self.get_settings()

    def credential(self) -> AdminCredential | None:
        with self.store.Session() as session:
            return session.get(AdminCredential, 1)

    def bootstrap_credential(
        self, *, username: str, password_hash: str
    ) -> bool:
        with self.store.Session.begin() as session:
            if session.get(AdminCredential, 1) is not None:
                return False
            session.add(
                AdminCredential(
                    singleton_id=1,
                    username=username,
                    password_hash=password_hash,
                    session_version=1,
                )
            )
            session.add(
                AdminAuditLog(
                    actor="bootstrap",
                    action="admin_credential_created",
                    target_type="admin",
                    target_id=username,
                    details_json="{}",
                )
            )
            return True

    def update_credential(
        self, *, username: str, password_hash: str, actor: str
    ) -> int:
        with self.store.Session.begin() as session:
            row = session.get(AdminCredential, 1)
            if row is None:
                raise RuntimeError("Admin credential is not configured")
            previous_username = row.username
            row.username = username
            row.password_hash = password_hash
            row.session_version += 1
            row.updated_at = utcnow()
            session.add(
                AdminAuditLog(
                    actor=actor,
                    action="admin_credential_updated",
                    target_type="admin",
                    target_id=username,
                    details_json=_json(
                        {"previous_username": previous_username}
                    ),
                )
            )
            return row.session_version

    def record_audit(
        self,
        *,
        actor: str,
        action: str,
        target_type: str,
        target_id: str | None = None,
        details: Mapping[str, Any] | None = None,
    ) -> None:
        with self.store.Session.begin() as session:
            session.add(
                AdminAuditLog(
                    actor=actor[:64],
                    action=action[:64],
                    target_type=target_type[:64],
                    target_id=target_id[:128] if target_id else None,
                    details_json=_json(details),
                )
            )

    def adjust_credits(
        self,
        user_id: int,
        *,
        delta: int,
        reason: str,
        actor: str,
    ) -> int:
        if delta == 0:
            raise ValueError("Credit adjustment cannot be zero")
        reason = reason.strip()
        if len(reason) < 3 or len(reason) > 255:
            raise ValueError("Reason must contain 3 to 255 characters")
        with self.store.Session.begin() as session:
            existing_user = session.execute(
                select(User.telegram_user_id)
                .where(User.telegram_user_id == int(user_id))
                .with_for_update()
            ).scalar_one_or_none()
            if existing_user is None:
                raise ValueError("Telegram user does not exist")
            insert_for_dialect = (
                postgresql_insert
                if self.store.engine.dialect.name == "postgresql"
                else sqlite_insert
            )
            session.execute(
                insert_for_dialect(AIAllowance)
                .values(
                    telegram_user_id=int(user_id),
                    available_credits=0,
                    reserved_credits=0,
                    spent_credits=0,
                    updated_at=utcnow(),
                )
                .on_conflict_do_nothing(
                    index_elements=[AIAllowance.telegram_user_id]
                )
            )
            allowance = session.execute(
                select(AIAllowance)
                .where(AIAllowance.telegram_user_id == int(user_id))
                .with_for_update()
            ).scalar_one()
            balance_after = allowance.available_credits + int(delta)
            if balance_after < 0:
                raise ValueError("Credit balance cannot become negative")
            allowance.available_credits = balance_after
            allowance.updated_at = utcnow()
            entry_id = str(uuid4())
            session.add(
                AICreditLedger(
                    entry_id=entry_id,
                    telegram_user_id=int(user_id),
                    delta=int(delta),
                    balance_after=balance_after,
                    reason=reason,
                    actor=actor,
                )
            )
            session.add(
                AdminAuditLog(
                    actor=actor,
                    action="ai_credits_adjusted",
                    target_type="telegram_user",
                    target_id=str(user_id),
                    details_json=_json(
                        {
                            "delta": int(delta),
                            "balance_after": balance_after,
                            "reason": reason,
                            "ledger_entry_id": entry_id,
                        }
                    ),
                )
            )
            return balance_after

    def dashboard(self) -> dict[str, Any]:
        now = datetime.now(timezone.utc)
        since = now - timedelta(days=7)
        with self.store.Session() as session:
            users = session.scalar(select(func.count(User.telegram_user_id))) or 0
            new_users = session.scalar(
                select(func.count(User.telegram_user_id)).where(
                    User.created_at >= since
                )
            ) or 0
            active_users = session.scalar(
                select(func.count(User.telegram_user_id)).where(
                    User.updated_at >= since
                )
            ) or 0
            learning = session.execute(
                select(
                    func.sum(UserProgress.sessions),
                    func.sum(UserProgress.total_correct),
                    func.sum(UserProgress.total_wrong),
                    func.sum(UserProgress.xp),
                )
            ).one()
            tracked_words = session.scalar(
                select(func.count(WordProgress.vocabulary_id))
            ) or 0
            learned_words = session.scalar(
                select(func.count(WordProgress.vocabulary_id)).where(
                    WordProgress.correct_count >= 3
                )
            ) or 0
            ai = session.execute(
                select(
                    func.count(AIUsage.request_id),
                    func.sum(AIUsage.total_tokens),
                    func.sum(AIUsage.cost_micro_usd),
                    func.avg(AIUsage.latency_ms),
                )
            ).one()
            failed_ai = session.scalar(
                select(func.count(AIUsage.request_id)).where(
                    AIUsage.status == "failed"
                )
            ) or 0
            credits = session.execute(
                select(
                    func.sum(AIAllowance.available_credits),
                    func.sum(AIAllowance.reserved_credits),
                    func.sum(AIAllowance.spent_credits),
                )
            ).one()
            language_rows = session.execute(
                select(
                    UserProgress.active_lang,
                    func.count(UserProgress.telegram_user_id),
                )
                .group_by(UserProgress.active_lang)
                .order_by(func.count(UserProgress.telegram_user_id).desc())
            ).all()
        correct = int(learning[1] or 0)
        wrong = int(learning[2] or 0)
        attempts = correct + wrong
        return {
            "users": int(users),
            "new_users_7d": int(new_users),
            "active_users_7d": int(active_users),
            "sessions": int(learning[0] or 0),
            "correct": correct,
            "wrong": wrong,
            "accuracy": (correct / attempts * 100) if attempts else 0,
            "xp": int(learning[3] or 0),
            "tracked_words": int(tracked_words),
            "learned_words": int(learned_words),
            "ai_requests": int(ai[0] or 0),
            "ai_tokens": int(ai[1] or 0),
            "ai_cost_micro_usd": int(ai[2] or 0),
            "ai_avg_latency_ms": float(ai[3] or 0),
            "ai_failed": int(failed_ai),
            "credits_available": int(credits[0] or 0),
            "credits_reserved": int(credits[1] or 0),
            "credits_spent": int(credits[2] or 0),
            "languages": [
                {"code": row[0], "users": int(row[1])}
                for row in language_rows
            ],
        }

    def users(self, *, search: str = "", limit: int = 100) -> list[dict[str, Any]]:
        word_stats = (
            select(
                WordProgress.telegram_user_id.label("user_id"),
                func.count(WordProgress.vocabulary_id).label("tracked_words"),
                func.sum(WordProgress.correct_count).label("word_correct"),
                func.sum(WordProgress.wrong_count).label("word_wrong"),
            )
            .group_by(WordProgress.telegram_user_id)
            .subquery()
        )
        learned_stats = (
            select(
                WordProgress.telegram_user_id.label("user_id"),
                func.count(WordProgress.vocabulary_id).label("learned_words"),
            )
            .where(WordProgress.correct_count >= 3)
            .group_by(WordProgress.telegram_user_id)
            .subquery()
        )
        ai_stats = (
            select(
                AIUsage.telegram_user_id.label("user_id"),
                func.count(AIUsage.request_id).label("ai_requests"),
                func.sum(AIUsage.total_tokens).label("ai_tokens"),
                func.sum(AIUsage.cost_micro_usd).label("ai_cost"),
            )
            .group_by(AIUsage.telegram_user_id)
            .subquery()
        )
        statement = (
            select(
                User,
                UserProgress,
                AIAllowance,
                word_stats.c.tracked_words,
                learned_stats.c.learned_words,
                word_stats.c.word_correct,
                word_stats.c.word_wrong,
                ai_stats.c.ai_requests,
                ai_stats.c.ai_tokens,
                ai_stats.c.ai_cost,
            )
            .outerjoin(
                UserProgress,
                UserProgress.telegram_user_id == User.telegram_user_id,
            )
            .outerjoin(
                AIAllowance,
                AIAllowance.telegram_user_id == User.telegram_user_id,
            )
            .outerjoin(
                word_stats, word_stats.c.user_id == User.telegram_user_id
            )
            .outerjoin(
                learned_stats,
                learned_stats.c.user_id == User.telegram_user_id,
            )
            .outerjoin(ai_stats, ai_stats.c.user_id == User.telegram_user_id)
            .order_by(User.updated_at.desc())
            .limit(max(1, min(int(limit), 10000)))
        )
        search = search.strip()
        if search:
            like = f"%{search}%"
            statement = statement.where(
                or_(
                    cast(User.telegram_user_id, String).like(like),
                    User.username.ilike(like),
                    User.first_name.ilike(like),
                    User.last_name.ilike(like),
                )
            )
        with self.store.Session() as session:
            rows = session.execute(statement).all()
        result = []
        for row in rows:
            user, progress, allowance = row[0], row[1], row[2]
            correct = int((progress.total_correct if progress else 0) or 0)
            wrong = int((progress.total_wrong if progress else 0) or 0)
            attempts = correct + wrong
            result.append(
                {
                    "id": user.telegram_user_id,
                    "name": _name(user),
                    "username": user.username or "",
                    "language_code": user.language_code or "",
                    "active_lang": progress.active_lang if progress else "en",
                    "xp": progress.xp if progress else 0,
                    "level": progress.level if progress else 1,
                    "streak": progress.streak if progress else 0,
                    "sessions": progress.sessions if progress else 0,
                    "correct": correct,
                    "wrong": wrong,
                    "accuracy": (correct / attempts * 100) if attempts else 0,
                    "tracked_words": int(row[3] or 0),
                    "learned_words": int(row[4] or 0),
                    "word_correct": int(row[5] or 0),
                    "word_wrong": int(row[6] or 0),
                    "ai_requests": int(row[7] or 0),
                    "ai_tokens": int(row[8] or 0),
                    "ai_cost_micro_usd": int(row[9] or 0),
                    "credits_available": (
                        allowance.available_credits if allowance else 0
                    ),
                    "credits_reserved": (
                        allowance.reserved_credits if allowance else 0
                    ),
                    "credits_spent": allowance.spent_credits if allowance else 0,
                    "created_at": user.created_at,
                    "updated_at": user.updated_at,
                }
            )
        return result

    def learning_by_language(self) -> list[dict[str, Any]]:
        with self.store.Session() as session:
            rows = session.execute(
                select(
                    WordProgress.language,
                    func.count(func.distinct(WordProgress.telegram_user_id)),
                    func.count(WordProgress.vocabulary_id),
                    func.sum(WordProgress.correct_count),
                    func.sum(WordProgress.wrong_count),
                )
                .group_by(WordProgress.language)
                .order_by(WordProgress.language)
            ).all()
            learned = dict(
                session.execute(
                    select(
                        WordProgress.language,
                        func.count(WordProgress.vocabulary_id),
                    )
                    .where(WordProgress.correct_count >= 3)
                    .group_by(WordProgress.language)
                ).all()
            )
        result = []
        for language, users, tracked, correct, wrong in rows:
            attempts = int(correct or 0) + int(wrong or 0)
            result.append(
                {
                    "language": language,
                    "users": int(users or 0),
                    "tracked_words": int(tracked or 0),
                    "learned_words": int(learned.get(language, 0)),
                    "correct": int(correct or 0),
                    "wrong": int(wrong or 0),
                    "accuracy": (int(correct or 0) / attempts * 100)
                    if attempts
                    else 0,
                }
            )
        return result

    def ai_overview(self) -> dict[str, Any]:
        with self.store.Session() as session:
            status_rows = session.execute(
                select(AIUsage.status, func.count(AIUsage.request_id)).group_by(
                    AIUsage.status
                )
            ).all()
            model_rows = session.execute(
                select(
                    AIUsage.provider,
                    AIUsage.model,
                    func.count(AIUsage.request_id),
                    func.sum(AIUsage.total_tokens),
                    func.sum(AIUsage.cost_micro_usd),
                    func.avg(AIUsage.latency_ms),
                )
                .group_by(AIUsage.provider, AIUsage.model)
                .order_by(func.count(AIUsage.request_id).desc())
            ).all()
        return {
            "statuses": {row[0]: int(row[1]) for row in status_rows},
            "models": [
                {
                    "provider": row[0],
                    "model": row[1],
                    "requests": int(row[2] or 0),
                    "tokens": int(row[3] or 0),
                    "cost_micro_usd": int(row[4] or 0),
                    "avg_latency_ms": float(row[5] or 0),
                }
                for row in model_rows
            ],
        }

    def recent_ai_usage(self, limit: int = 100) -> list[dict[str, Any]]:
        with self.store.Session() as session:
            rows = session.execute(
                select(AIUsage)
                .order_by(AIUsage.created_at.desc())
                .limit(max(1, min(int(limit), 1000)))
            ).scalars().all()
        return [
            {column.name: getattr(row, column.name) for column in AIUsage.__table__.columns}
            for row in rows
        ]

    def ai_usage_export(self) -> list[dict[str, Any]]:
        with self.store.Session() as session:
            rows = session.execute(
                select(AIUsage).order_by(AIUsage.created_at.desc())
            ).scalars().all()
        return [
            {
                column.name: getattr(row, column.name)
                for column in AIUsage.__table__.columns
            }
            for row in rows
        ]

    def credit_ledger(self, limit: int = 100) -> list[dict[str, Any]]:
        with self.store.Session() as session:
            rows = session.execute(
                select(AICreditLedger)
                .order_by(AICreditLedger.created_at.desc())
                .limit(max(1, min(int(limit), 10000)))
            ).scalars().all()
        return [
            {
                column.name: getattr(row, column.name)
                for column in AICreditLedger.__table__.columns
            }
            for row in rows
        ]

    def audit_log(self, limit: int = 100) -> list[dict[str, Any]]:
        with self.store.Session() as session:
            rows = session.execute(
                select(AdminAuditLog)
                .order_by(AdminAuditLog.created_at.desc())
                .limit(max(1, min(int(limit), 1000)))
            ).scalars().all()
        return [
            {
                "id": row.id,
                "actor": row.actor,
                "action": row.action,
                "target_type": row.target_type,
                "target_id": row.target_id or "",
                "details": json.loads(row.details_json or "{}"),
                "created_at": row.created_at,
            }
            for row in rows
        ]

    def word_progress_export(self) -> list[dict[str, Any]]:
        with self.store.Session() as session:
            rows = session.execute(
                select(WordProgress).order_by(
                    WordProgress.telegram_user_id,
                    WordProgress.language,
                    WordProgress.word_index,
                )
            ).scalars().all()
        return [
            {
                column.name: getattr(row, column.name)
                for column in WordProgress.__table__.columns
            }
            for row in rows
        ]
