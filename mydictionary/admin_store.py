"""Database queries and transactional actions used by the admin console."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from typing import Any, Mapping
from uuid import uuid4

from sqlalchemy import String, cast, func, or_, select

from mydictionary.billing import (
    BillingService,
    BillingSettings,
    PRODUCT_ID_RE,
    PRODUCT_STATUSES,
)
from mydictionary.bot_profile import BOT_PROFILE_DEFAULTS
from mydictionary.storage import (
    ACCESS_STATUSES,
    AIWallet,
    AIUsage,
    AnalyticsEvent,
    AdminAuditLog,
    AdminCredential,
    AppSetting,
    BillingCreditLedger,
    BillingProduct,
    DatabaseStore,
    PaymentOrder,
    RefundRequest,
    StarsPayment,
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
    def __init__(
        self,
        store: DatabaseStore,
        billing_settings: BillingSettings | None = None,
    ):
        self.store = store
        self.billing_settings = billing_settings or BillingSettings.from_env()
        self.billing = BillingService(store, self.billing_settings)

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
        idempotency_key: str | None = None,
    ) -> int:
        if delta == 0:
            raise ValueError("Credit adjustment cannot be zero")
        reason = reason.strip()
        if len(reason) < 3 or len(reason) > 255:
            raise ValueError("Reason must contain 3 to 255 characters")
        result = self.store.adjust_ai_wallet(
            user_id,
            delta=int(delta),
            reason=reason,
            actor=actor,
            idempotency_key=(
                str(idempotency_key).strip()[:249]
                if idempotency_key
                else f"admin:{uuid4()}"
            ),
        )
        return result["available_credits"]

    def set_user_access_status(
        self,
        user_id: int,
        *,
        status: str,
        actor: str,
    ) -> str:
        status = str(status).strip().lower()
        if status not in ACCESS_STATUSES:
            raise ValueError("Unknown user access status")
        with self.store.Session.begin() as session:
            user = session.execute(
                select(User)
                .where(User.telegram_user_id == int(user_id))
                .with_for_update()
            ).scalar_one_or_none()
            if user is None:
                raise ValueError("Telegram user does not exist")
            if user.role == "admin" and status != "active":
                raise ValueError("Administrator access cannot be restricted")
            previous = user.access_status
            if previous == status:
                return status
            user.access_status = status
            user.access_status_updated_at = utcnow()
            user.updated_at = utcnow()
            session.add(
                AdminAuditLog(
                    actor=actor[:64],
                    action="user_access_updated",
                    target_type="user",
                    target_id=str(user.telegram_user_id),
                    details_json=_json(
                        {"previous": previous, "current": status}
                    ),
                )
            )
        return status

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
            onboarded_users = session.scalar(
                select(func.count(User.telegram_user_id)).where(
                    User.onboarding_completed_at.is_not(None)
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
                    func.sum(AIWallet.balance_credits - AIWallet.reserved_credits),
                    func.sum(AIWallet.reserved_credits),
                    func.sum(AIWallet.spent_credits),
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
            access_rows = session.execute(
                select(User.access_status, func.count(User.telegram_user_id))
                .group_by(User.access_status)
            ).all()
        correct = int(learning[1] or 0)
        wrong = int(learning[2] or 0)
        attempts = correct + wrong
        return {
            "users": int(users),
            "new_users_7d": int(new_users),
            "active_users_7d": int(active_users),
            "onboarded_users": int(onboarded_users),
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
            "access": {row[0]: int(row[1]) for row in access_rows},
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
                AIWallet,
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
                AIWallet,
                AIWallet.telegram_user_id == User.telegram_user_id,
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
            user, progress, wallet = row[0], row[1], row[2]
            correct = int((progress.total_correct if progress else 0) or 0)
            wrong = int((progress.total_wrong if progress else 0) or 0)
            attempts = correct + wrong
            result.append(
                {
                    "id": user.telegram_user_id,
                    "name": _name(user),
                    "username": user.username or "",
                    "language_code": user.language_code or "",
                    "role": user.role,
                    "access_status": user.access_status,
                    "access_status_updated_at": user.access_status_updated_at,
                    "native_language": user.native_language or "",
                    "learning_goal": user.learning_goal or "",
                    "daily_word_goal": user.daily_word_goal,
                    "onboarding_completed_at": user.onboarding_completed_at,
                    "active_lang": progress.active_lang if progress else "en",
                    "active_pack_id": (
                        progress.active_pack_id if progress else ""
                    ) or "",
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
                        wallet.balance_credits - wallet.reserved_credits
                        if wallet
                        else 0
                    ),
                    "credits_reserved": (
                        wallet.reserved_credits if wallet else 0
                    ),
                    "credits_spent": wallet.spent_credits if wallet else 0,
                    "created_at": user.created_at,
                    "updated_at": user.updated_at,
                }
            )
        return result

    def product_funnel(self, *, days: int = 30) -> dict[str, Any]:
        days = max(1, min(int(days), 365))
        since = datetime.now(timezone.utc) - timedelta(days=days)
        steps = [
            ("start_received", "Открыли /start"),
            ("pilot_waitlist_joined", "Встали в очередь пилота"),
            ("onboarding_started", "Начали настройку"),
            ("onboarding_completed", "Завершили настройку"),
            ("block_started", "Открыли учебный блок"),
            ("block_completed", "Завершили блок"),
        ]
        event_names = [name for name, _ in steps]
        with self.store.Session() as session:
            rows = session.execute(
                select(
                    AnalyticsEvent.event_name,
                    func.count(AnalyticsEvent.event_id),
                    func.count(func.distinct(AnalyticsEvent.telegram_user_id)),
                )
                .join(
                    User,
                    User.telegram_user_id == AnalyticsEvent.telegram_user_id,
                )
                .where(
                    AnalyticsEvent.occurred_at >= since,
                    AnalyticsEvent.event_name.in_(event_names),
                    User.role == "learner",
                )
                .group_by(AnalyticsEvent.event_name)
            ).all()
        aggregates = {
            row[0]: {"events": int(row[1]), "users": int(row[2])}
            for row in rows
        }
        starts = aggregates.get("start_received", {}).get("users", 0)
        return {
            "days": days,
            "steps": [
                {
                    "event_name": name,
                    "label": label,
                    "events": aggregates.get(name, {}).get("events", 0),
                    "users": aggregates.get(name, {}).get("users", 0),
                    "conversion": (
                        aggregates.get(name, {}).get("users", 0) / starts * 100
                        if starts
                        else 0
                    ),
                }
                for name, label in steps
            ],
        }

    def recent_product_events(self, limit: int = 100) -> list[dict[str, Any]]:
        with self.store.Session() as session:
            rows = session.execute(
                select(AnalyticsEvent)
                .order_by(AnalyticsEvent.occurred_at.desc())
                .limit(max(1, min(int(limit), 1000)))
            ).scalars().all()
        return [
            {
                "event_id": row.event_id,
                "telegram_user_id": row.telegram_user_id,
                "event_name": row.event_name,
                "session_id": row.session_id or "",
                "source": row.source or "",
                "properties": json.loads(row.properties_json or "{}"),
                "occurred_at": row.occurred_at,
            }
            for row in rows
        ]

    def product_events_export(self) -> list[dict[str, Any]]:
        return [
            dict(row, properties=json.dumps(row["properties"], ensure_ascii=False))
            for row in self.recent_product_events(limit=1000)
        ]

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

    def upsert_billing_product(
        self,
        *,
        product_id: str,
        title: str,
        description: str,
        credits: int,
        price_xtr: int,
        status: str,
        estimated_cost_micro_usd: int,
        target_margin_bps: int,
        display_order: int,
        actor: str,
    ) -> dict[str, Any]:
        product_id = str(product_id).strip().lower()
        title = str(title).strip()
        description = str(description).strip()
        status = str(status).strip().lower()
        if not PRODUCT_ID_RE.fullmatch(product_id):
            raise ValueError("Product ID must use lowercase letters, digits, and hyphens")
        if not 1 <= len(title) <= 32 or not 1 <= len(description) <= 255:
            raise ValueError("Product title or description is outside Telegram limits")
        if status not in PRODUCT_STATUSES:
            raise ValueError("Unknown billing product status")
        if not 1 <= int(credits) <= 1_000_000:
            raise ValueError("Product credits must be between 1 and 1000000")
        if not 1 <= int(price_xtr) <= 1_000_000:
            raise ValueError("Product price must be between 1 and 1000000 XTR")
        if int(estimated_cost_micro_usd) < 0:
            raise ValueError("Estimated product cost cannot be negative")
        if not 0 <= int(target_margin_bps) <= 10000:
            raise ValueError("Target margin must be between 0 and 10000 bps")
        candidate = {
            "price_xtr": int(price_xtr),
            "estimated_cost_micro_usd": int(estimated_cost_micro_usd),
        }
        estimated_margin = self.billing.product_margin_bps(candidate)
        if status == "active":
            if int(estimated_cost_micro_usd) <= 0 or int(target_margin_bps) <= 0:
                raise ValueError(
                    "Active products require measured cost and a positive margin floor"
                )
            if estimated_margin is None:
                raise ValueError(
                    "Configure BILLING_NET_MICRO_USD_PER_XTR before activation"
                )
            if estimated_margin < int(target_margin_bps):
                raise ValueError("Estimated margin is below the configured floor")
        with self.store.Session.begin() as session:
            row = session.get(BillingProduct, product_id)
            action = "billing_product_created"
            if row is None:
                row = BillingProduct(product_id=product_id)
                session.add(row)
            else:
                action = "billing_product_updated"
            row.title = title
            row.description = description
            row.credits = int(credits)
            row.price_xtr = int(price_xtr)
            row.status = status
            row.estimated_cost_micro_usd = int(estimated_cost_micro_usd)
            row.target_margin_bps = int(target_margin_bps)
            row.display_order = int(display_order)
            row.updated_at = utcnow()
            session.add(
                AdminAuditLog(
                    actor=actor[:64],
                    action=action,
                    target_type="billing_product",
                    target_id=product_id,
                    details_json=_json(
                        {
                            "credits": int(credits),
                            "price_xtr": int(price_xtr),
                            "status": status,
                            "estimated_cost_micro_usd": int(
                                estimated_cost_micro_usd
                            ),
                            "target_margin_bps": int(target_margin_bps),
                            "estimated_margin_bps": estimated_margin,
                        }
                    ),
                )
            )
        return self.billing_products(product_id=product_id)[0]

    def billing_products(
        self, *, product_id: str | None = None
    ) -> list[dict[str, Any]]:
        statement = select(BillingProduct).order_by(
            BillingProduct.display_order, BillingProduct.price_xtr
        )
        if product_id is not None:
            statement = statement.where(BillingProduct.product_id == product_id)
        with self.store.Session() as session:
            rows = session.execute(statement).scalars().all()
        result = []
        for row in rows:
            product = {
                column.name: getattr(row, column.name)
                for column in BillingProduct.__table__.columns
            }
            product["estimated_margin_bps"] = self.billing.product_margin_bps(row)
            product["estimated_net_revenue_micro_usd"] = (
                row.price_xtr * self.billing_settings.net_micro_usd_per_xtr
            )
            result.append(product)
        return result

    def billing_overview(self) -> dict[str, Any]:
        with self.store.Session() as session:
            order_rows = session.execute(
                select(PaymentOrder.status, func.count(PaymentOrder.order_id)).group_by(
                    PaymentOrder.status
                )
            ).all()
            payment_rows = session.execute(
                select(
                    StarsPayment.status,
                    func.count(StarsPayment.payment_id),
                    func.sum(StarsPayment.total_amount),
                ).group_by(StarsPayment.status)
            ).all()
            credits_sold = session.scalar(
                select(func.sum(PaymentOrder.credits_snapshot)).where(
                    PaymentOrder.status.in_({"paid", "refund_pending"})
                )
            ) or 0
            credits_refunded = session.scalar(
                select(func.sum(RefundRequest.credits)).where(
                    RefundRequest.status == "completed"
                )
            ) or 0
            pending_refunds = session.scalar(
                select(func.count(RefundRequest.refund_id)).where(
                    RefundRequest.status.in_({"requested", "processing", "failed"})
                )
            ) or 0
        payment_statuses = {
            status: {"count": int(count or 0), "xtr": int(amount or 0)}
            for status, count, amount in payment_rows
        }
        return {
            "enabled": self.billing_settings.enabled,
            "unit_economics_configured": (
                self.billing_settings.net_micro_usd_per_xtr > 0
            ),
            "orders": {status: int(count) for status, count in order_rows},
            "payments": payment_statuses,
            "xtr_collected": sum(
                value["xtr"]
                for status, value in payment_statuses.items()
                if status in {"paid", "refund_pending"}
            ),
            "xtr_refunded": payment_statuses.get("refunded", {}).get("xtr", 0),
            "credits_sold": int(credits_sold),
            "credits_refunded": int(credits_refunded),
            "pending_refunds": int(pending_refunds),
        }

    def recent_payment_orders(self, limit: int = 100) -> list[dict[str, Any]]:
        with self.store.Session() as session:
            rows = session.execute(
                select(PaymentOrder)
                .order_by(PaymentOrder.created_at.desc())
                .limit(max(1, min(int(limit), 1000)))
            ).scalars().all()
        return [
            {
                column.name: getattr(row, column.name)
                for column in PaymentOrder.__table__.columns
                if column.name != "invoice_payload"
            }
            for row in rows
        ]

    def stars_payments(self, limit: int = 100) -> list[dict[str, Any]]:
        with self.store.Session() as session:
            rows = session.execute(
                select(StarsPayment, PaymentOrder)
                .join(PaymentOrder, PaymentOrder.order_id == StarsPayment.order_id)
                .order_by(StarsPayment.received_at.desc())
                .limit(max(1, min(int(limit), 1000)))
            ).all()
        return [
            {
                "payment_id": payment.payment_id,
                "order_id": payment.order_id,
                "telegram_user_id": payment.telegram_user_id,
                "product_id": order.product_id,
                "product_title": order.product_title,
                "credits": order.credits_snapshot,
                "currency": payment.currency,
                "total_amount": payment.total_amount,
                "telegram_payment_charge_id": payment.telegram_payment_charge_id,
                "status": payment.status,
                "received_at": payment.received_at,
                "refunded_at": payment.refunded_at,
            }
            for payment, order in rows
        ]

    def refund_requests(self, limit: int = 100) -> list[dict[str, Any]]:
        with self.store.Session() as session:
            rows = session.execute(
                select(RefundRequest)
                .order_by(RefundRequest.created_at.desc())
                .limit(max(1, min(int(limit), 1000)))
            ).scalars().all()
        return [
            {
                column.name: getattr(row, column.name)
                for column in RefundRequest.__table__.columns
            }
            for row in rows
        ]

    def request_stars_refund(
        self, *, payment_id: str, reason: str, actor: str
    ) -> str:
        return self.billing.request_refund(
            payment_id=payment_id, reason=reason, actor=actor
        )

    def billing_reconciliation(self) -> list[dict[str, str]]:
        issues: list[dict[str, str]] = []
        with self.store.Session() as session:
            orders = session.execute(
                select(PaymentOrder).where(
                    PaymentOrder.status.in_(
                        {"paid", "refund_pending", "refunded"}
                    )
                )
            ).scalars().all()
            for order in orders:
                payment = session.execute(
                    select(StarsPayment).where(
                        StarsPayment.order_id == order.order_id
                    )
                ).scalar_one_or_none()
                if payment is None:
                    issues.append(
                        {
                            "code": "paid_order_missing_payment",
                            "reference": order.order_id,
                            "details": "Order state requires a Stars payment row",
                        }
                    )
                    continue
                ledger = session.execute(
                    select(BillingCreditLedger).where(
                        BillingCreditLedger.idempotency_key
                        == f"stars-payment:{payment.telegram_payment_charge_id}"
                    )
                ).scalar_one_or_none()
                if ledger is None:
                    issues.append(
                        {
                            "code": "payment_missing_credit_ledger",
                            "reference": payment.payment_id,
                            "details": "Payment has no idempotent credit grant",
                        }
                    )
            refunds = session.execute(
                select(RefundRequest).where(RefundRequest.status == "completed")
            ).scalars().all()
            for refund in refunds:
                ledger = session.execute(
                    select(BillingCreditLedger).where(
                        BillingCreditLedger.reference_type == "refund",
                        BillingCreditLedger.reference_id == refund.refund_id,
                    )
                ).scalar_one_or_none()
                if ledger is None:
                    issues.append(
                        {
                            "code": "refund_missing_credit_reversal",
                            "reference": refund.refund_id,
                            "details": "Completed refund has no ledger reversal",
                        }
                    )
        return issues

    def credit_ledger(self, limit: int = 100) -> list[dict[str, Any]]:
        with self.store.Session() as session:
            rows = session.execute(
                select(BillingCreditLedger)
                .order_by(BillingCreditLedger.created_at.desc())
                .limit(max(1, min(int(limit), 10000)))
            ).scalars().all()
        return [
            {
                column.name: getattr(row, column.name)
                for column in BillingCreditLedger.__table__.columns
            }
            for row in rows
        ]

    def payment_orders_export(self) -> list[dict[str, Any]]:
        return self.recent_payment_orders(limit=10000)

    def stars_payments_export(self) -> list[dict[str, Any]]:
        return self.stars_payments(limit=10000)

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
