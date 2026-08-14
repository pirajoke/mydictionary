"""Database queries and transactional actions used by the admin console."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import json
from typing import Any, Mapping
from uuid import uuid4

from sqlalchemy import String, case, cast, func, or_, select

from mydictionary.billing import (
    BILLING_MODES,
    BillingService,
    BillingSettings,
    PRODUCT_ID_RE,
    PRODUCT_STATUSES,
    SUBSCRIPTION_PERIOD_SECONDS,
)
from mydictionary.bot_profile import BOT_PROFILE_DEFAULTS
from mydictionary.mirror_assistant import (
    MIRROR_ADMIN_DEFAULTS,
    MIRROR_CONTROL_PLANE_DEFAULTS,
    validate_mirror_admin_settings,
    validate_mirror_control_plane,
)
from mydictionary.storage import (
    ACCESS_STATUSES,
    AIWallet,
    AIUsage,
    AbuseEvent,
    AnalyticsEvent,
    AdminAuditLog,
    AdminCredential,
    AppSetting,
    BillingCreditLedger,
    BillingProduct,
    DatabaseStore,
    MirrorPolicySnapshot,
    MirrorResponseFeedback,
    MirrorResponseQuality,
    PaymentOrder,
    RefundRequest,
    RateLimitBucket,
    StarsPayment,
    StarsSubscription,
    TelegramNotification,
    User,
    UserProgress,
    VoiceSession,
    VoiceTurn,
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


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


PILOT_STAGE_LABELS = (
    ("pilot_waitlist_joined", "Оставили заявку"),
    ("pilot_access_approved", "Допущены"),
    ("onboarding_completed", "Завершили настройку"),
    ("block_started", "Открыли первый блок"),
    ("block_completed", "Завершили первый блок"),
)
PILOT_ACTIVITY_EVENTS = {
    "start_received",
    "onboarding_started",
    "onboarding_completed",
    "language_switched",
    "block_started",
    "block_mode_started",
    "word_audio_played",
    "block_completed",
}
PILOT_USER_STAGES = {
    "all",
    "pending",
    "onboarding",
    "first_block",
    "engaged",
    "blocked",
}


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
        result = {**BOT_PROFILE_DEFAULTS, **MIRROR_ADMIN_DEFAULTS}
        result.update({row.key: row.value for row in rows})
        result["mirror_safety_envelope_checksum"] = MIRROR_ADMIN_DEFAULTS[
            "mirror_safety_envelope_checksum"
        ]
        return result

    def update_mirror_settings(
        self, values: Mapping[str, str], *, actor: str
    ) -> dict[str, str]:
        validated = validate_mirror_admin_settings(values)
        changed: list[str] = []
        with self.store.Session.begin() as session:
            for key, value in validated.items():
                row = session.get(AppSetting, key)
                if row is None:
                    row = AppSetting(key=key, value=value, updated_by=actor)
                    session.add(row)
                    changed.append(key)
                elif row.value != value:
                    row.value = value
                    row.updated_by = actor
                    row.updated_at = utcnow()
                    changed.append(key)
            if changed:
                session.add(
                    AdminAuditLog(
                        actor=actor[:64],
                        action="mirror_settings_updated",
                        target_type="settings",
                        target_id=validated["mirror_capabilities_version"],
                        details_json=_json(
                            {
                                "fields": changed,
                                "capabilities_sha256": hashlib.sha256(
                                    validated["mirror_capabilities_text"].encode("utf-8")
                                ).hexdigest(),
                                "persona_sha256": hashlib.sha256(
                                    validated["mirror_persona_guidance"].encode("utf-8")
                                ).hexdigest(),
                            }
                        ),
                    )
                )
        return self.get_settings()

    @staticmethod
    def _mirror_policy_from_row(row: MirrorPolicySnapshot) -> dict[str, Any]:
        return {
            "snapshot_id": row.snapshot_id,
            "policy_version": row.policy_version,
            "enabled_modes": json.loads(row.enabled_modes_json),
            "default_mode": row.default_mode,
            "answer_depth": row.answer_depth,
            "learner_level": row.learner_level,
            "mode_guidance": json.loads(row.mode_guidance_json),
            "config_sha256": row.config_sha256,
            "created_at": row.created_at,
        }

    def get_mirror_control_plane(self) -> dict[str, Any]:
        with self.store.Session() as session:
            row = session.execute(
                select(MirrorPolicySnapshot).order_by(
                    MirrorPolicySnapshot.created_at.desc(),
                    MirrorPolicySnapshot.snapshot_id.desc(),
                )
            ).scalars().first()
        if row is None:
            return {**MIRROR_CONTROL_PLANE_DEFAULTS, "snapshot_id": None}
        return self._mirror_policy_from_row(row)

    @staticmethod
    def _mirror_policy_hashes(policy: Mapping[str, Any]) -> dict[str, str]:
        return {
            field: hashlib.sha256(
                json.dumps(
                    policy[field], ensure_ascii=False, sort_keys=True
                ).encode("utf-8")
            ).hexdigest()
            for field in (
                "policy_version",
                "enabled_modes",
                "default_mode",
                "answer_depth",
                "learner_level",
                "mode_guidance",
            )
        }

    def _save_mirror_control_plane(
        self,
        policy: Mapping[str, Any],
        *,
        actor: str,
        action: str,
        source_snapshot_id: str | None = None,
    ) -> dict[str, Any]:
        previous = self.get_mirror_control_plane()
        changed = [
            field
            for field in (
                "policy_version",
                "enabled_modes",
                "default_mode",
                "answer_depth",
                "learner_level",
                "mode_guidance",
            )
            if previous.get(field) != policy.get(field)
        ]
        serialized = json.dumps(
            dict(policy), ensure_ascii=False, sort_keys=True, separators=(",", ":")
        )
        snapshot_id = str(uuid4())
        row = MirrorPolicySnapshot(
            snapshot_id=snapshot_id,
            policy_version=str(policy["policy_version"]),
            enabled_modes_json=json.dumps(
                policy["enabled_modes"], ensure_ascii=False, separators=(",", ":")
            ),
            default_mode=str(policy["default_mode"]),
            answer_depth=str(policy["answer_depth"]),
            learner_level=str(policy["learner_level"]),
            mode_guidance_json=json.dumps(
                policy["mode_guidance"],
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ),
            config_sha256=hashlib.sha256(serialized.encode("utf-8")).hexdigest(),
            actor=str(actor)[:64],
            created_at=utcnow(),
        )
        details = {
            "changed_fields": changed,
            "field_hashes": self._mirror_policy_hashes(policy),
        }
        if source_snapshot_id:
            details["source_snapshot_id"] = source_snapshot_id
        with self.store.Session.begin() as session:
            session.add(row)
            session.add(
                AdminAuditLog(
                    actor=str(actor)[:64],
                    action=action,
                    target_type="mirror_control_plane",
                    target_id=snapshot_id,
                    details_json=_json(details),
                )
            )
        return self.get_mirror_control_plane()

    def update_mirror_control_plane(
        self, values: Mapping[str, Any], *, actor: str
    ) -> dict[str, Any]:
        validated = validate_mirror_control_plane(values)
        return self._save_mirror_control_plane(
            validated,
            actor=actor,
            action="mirror_control_plane_updated",
        )

    def mirror_control_plane_snapshots(self, *, limit: int = 20) -> list[dict[str, Any]]:
        bounded = int(limit)
        if not 1 <= bounded <= 100:
            raise ValueError("Mirror snapshot limit must be 1-100")
        with self.store.Session() as session:
            rows = session.execute(
                select(MirrorPolicySnapshot)
                .order_by(
                    MirrorPolicySnapshot.created_at.desc(),
                    MirrorPolicySnapshot.snapshot_id.desc(),
                )
                .limit(bounded)
            ).scalars().all()
        return [self._mirror_policy_from_row(row) for row in rows]

    def restore_mirror_control_plane(
        self, snapshot_id: str, *, actor: str
    ) -> dict[str, Any]:
        with self.store.Session() as session:
            row = session.get(MirrorPolicySnapshot, str(snapshot_id))
            if row is None:
                raise ValueError("Mirror control plane snapshot was not found")
            policy = self._mirror_policy_from_row(row)
        validated = validate_mirror_control_plane(
            {
                key: policy[key]
                for key in (
                    "policy_version",
                    "enabled_modes",
                    "default_mode",
                    "answer_depth",
                    "learner_level",
                    "mode_guidance",
                )
            }
        )
        return self._save_mirror_control_plane(
            validated,
            actor=actor,
            action="mirror_control_plane_restored",
            source_snapshot_id=str(snapshot_id),
        )

    def mirror_quality_analytics(self, *, days: int = 30) -> dict[str, Any]:
        if int(days) not in {7, 30, 90}:
            raise ValueError("Mirror analytics range must be 7, 30, or 90 days")
        range_days = int(days)
        since = utcnow() - timedelta(days=range_days)
        with self.store.Session() as session:
            quality = session.execute(
                select(MirrorResponseQuality).where(
                    MirrorResponseQuality.created_at >= since
                )
            ).scalars().all()
            feedback = session.execute(
                select(MirrorResponseFeedback).where(
                    MirrorResponseFeedback.created_at >= since
                )
            ).scalars().all()
            learning_sessions = int(
                session.scalar(
                    select(func.count(AnalyticsEvent.event_id)).where(
                        AnalyticsEvent.event_name == "block_completed",
                        AnalyticsEvent.occurred_at >= since,
                    )
                )
                or 0
            )
            voice_requests = int(
                session.scalar(
                    select(func.count(AIUsage.request_id)).where(
                        AIUsage.action.in_(
                            {"voice_transcription", "voice_translation"}
                        ),
                        AIUsage.created_at >= since,
                    )
                )
                or 0
            )

        def breakdown(field: str) -> dict[str, Any]:
            counts: dict[str, int] = {}
            for row in quality:
                key = str(getattr(row, field))
                counts[key] = counts.get(key, 0) + 1
            return (
                {"status": "ok", "items": counts}
                if counts
                else {"status": "no_data", "items": {}}
            )

        has_data = bool(quality or learning_sessions or voice_requests)
        helpful = sum(1 for row in feedback if row.helpful)
        mirror = {
            "status": "ok" if quality else "no_data",
            "responses": len(quality),
            "average_score_bps": (
                round(sum(row.deterministic_score_bps for row in quality) / len(quality))
                if quality
                else 0
            ),
            "feedback": len(feedback),
            "helpful": helpful,
        }
        return {
            "range_days": range_days,
            "has_data": has_data,
            "status": "ok" if has_data else "no_data",
            "learning": {
                "status": "ok" if learning_sessions else "no_data",
                "completed_blocks": learning_sessions,
            },
            "mirror": mirror,
            "voice": {
                "status": "ok" if voice_requests else "no_data",
                "requests": voice_requests,
            },
            "breakdowns": {
                "mode": breakdown("mode"),
                "task": breakdown("task"),
                "level": breakdown("level"),
            },
        }

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
            observed_at = utcnow()
            user.access_status = status
            user.access_status_updated_at = observed_at
            if status == "active" and user.privacy_status == "erased":
                user.privacy_status = "active"
                user.privacy_deleted_at = None
            user.updated_at = observed_at
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
            event_name = {
                "active": "pilot_access_approved",
                "pending": "pilot_access_pending",
                "blocked": "pilot_access_blocked",
            }[status]
            session.add(
                AnalyticsEvent(
                    event_id=str(uuid4()),
                    telegram_user_id=user.telegram_user_id,
                    event_name=event_name,
                    source="admin",
                    properties_json="{}",
                    occurred_at=observed_at,
                )
            )
            if status == "active":
                session.add(
                    TelegramNotification(
                        notification_id=str(uuid4()),
                        telegram_user_id=user.telegram_user_id,
                        kind="pilot_access_approved",
                        status="pending",
                        idempotency_key=(
                            f"pilot-access:{user.telegram_user_id}:"
                            f"{observed_at.isoformat()}"
                        ),
                        available_at=observed_at,
                        created_at=observed_at,
                        updated_at=observed_at,
                    )
                )
            else:
                queued = session.execute(
                    select(TelegramNotification).where(
                        TelegramNotification.telegram_user_id
                        == user.telegram_user_id,
                        TelegramNotification.kind == "pilot_access_approved",
                        TelegramNotification.status.in_({"pending", "processing"}),
                    )
                ).scalars().all()
                for notification in queued:
                    notification.status = "cancelled"
                    notification.lease_until = None
                    notification.updated_at = observed_at
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
                    "privacy_status": user.privacy_status,
                    "privacy_deleted_at": user.privacy_deleted_at,
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

    def pilot_overview(self, *, days: int = 30) -> dict[str, Any]:
        days = max(1, min(int(days), 365))
        now = datetime.now(timezone.utc)
        since = now - timedelta(days=days)
        with self.store.Session() as session:
            waitlist_rows = session.execute(
                select(
                    AnalyticsEvent.telegram_user_id,
                    func.min(AnalyticsEvent.occurred_at),
                )
                .join(User, User.telegram_user_id == AnalyticsEvent.telegram_user_id)
                .where(
                    User.role == "learner",
                    AnalyticsEvent.event_name == "pilot_waitlist_joined",
                    AnalyticsEvent.occurred_at >= since,
                )
                .group_by(AnalyticsEvent.telegram_user_id)
            ).all()
            joined_at = {
                int(user_id): _as_utc(observed_at)
                for user_id, observed_at in waitlist_rows
            }
            cohort_ids = set(joined_at)
            if cohort_ids:
                tracked_names = {
                    name for name, _ in PILOT_STAGE_LABELS
                } | PILOT_ACTIVITY_EVENTS
                event_rows = session.execute(
                    select(
                        AnalyticsEvent.telegram_user_id,
                        AnalyticsEvent.event_name,
                        AnalyticsEvent.occurred_at,
                    ).where(
                        AnalyticsEvent.telegram_user_id.in_(cohort_ids),
                        AnalyticsEvent.event_name.in_(tracked_names),
                        AnalyticsEvent.occurred_at >= since,
                    )
                ).all()
                user_rows = session.execute(
                    select(User, UserProgress)
                    .outerjoin(
                        UserProgress,
                        UserProgress.telegram_user_id == User.telegram_user_id,
                    )
                    .where(User.telegram_user_id.in_(cohort_ids))
                ).all()
                notification_rows = session.execute(
                    select(
                        TelegramNotification.status,
                        func.count(TelegramNotification.notification_id),
                    )
                    .where(TelegramNotification.telegram_user_id.in_(cohort_ids))
                    .group_by(TelegramNotification.status)
                ).all()
            else:
                event_rows = []
                user_rows = []
                notification_rows = []

        first_events: dict[str, dict[int, datetime]] = {
            name: {} for name, _ in PILOT_STAGE_LABELS
        }
        activity_by_user: dict[int, list[datetime]] = {
            user_id: [] for user_id in cohort_ids
        }
        for user_id, event_name, occurred_at in event_rows:
            user_id = int(user_id)
            observed_at = _as_utc(occurred_at)
            if event_name in first_events:
                previous = first_events[event_name].get(user_id)
                if previous is None or observed_at < previous:
                    first_events[event_name][user_id] = observed_at
            if event_name in PILOT_ACTIVITY_EVENTS:
                activity_by_user[user_id].append(observed_at)
        first_events["pilot_waitlist_joined"] = dict(joined_at)
        cohort_size = len(cohort_ids)
        stages = []
        for event_name, label in PILOT_STAGE_LABELS:
            users = len(first_events[event_name])
            stages.append(
                {
                    "event_name": event_name,
                    "label": label,
                    "users": users,
                    "conversion": users / cohort_size * 100 if cohort_size else 0,
                }
            )

        def retention(day: int) -> dict[str, float | int]:
            eligible = {
                user_id
                for user_id, joined in joined_at.items()
                if joined <= now - timedelta(days=day)
            }
            retained = {
                user_id
                for user_id in eligible
                if any(
                    joined_at[user_id] + timedelta(days=day) <= observed
                    < joined_at[user_id] + timedelta(days=day + 1)
                    for observed in activity_by_user[user_id]
                )
            }
            return {
                "eligible": len(eligible),
                "users": len(retained),
                "rate": len(retained) / len(eligible) * 100 if eligible else 0,
            }

        access: dict[str, int] = {}
        sources: dict[str, int] = {}
        languages: dict[str, int] = {}
        for user, progress in user_rows:
            access[user.access_status] = access.get(user.access_status, 0) + 1
            source = user.acquisition_source or "direct"
            sources[source] = sources.get(source, 0) + 1
            language = progress.active_lang if progress else "en"
            languages[language] = languages.get(language, 0) + 1
        return {
            "days": days,
            "cohort": cohort_size,
            "stages": stages,
            "retention": {"d1": retention(1), "d7": retention(7)},
            "access": access,
            "notifications": {
                status: int(count) for status, count in notification_rows
            },
            "sources": [
                {"source": key, "users": value}
                for key, value in sorted(
                    sources.items(), key=lambda item: (-item[1], item[0])
                )
            ],
            "languages": [
                {"language": key, "users": value}
                for key, value in sorted(
                    languages.items(), key=lambda item: (-item[1], item[0])
                )
            ],
        }

    def pilot_users(
        self, *, stage: str = "all", limit: int = 250
    ) -> list[dict[str, Any]]:
        stage = str(stage).strip().lower()
        if stage not in PILOT_USER_STAGES:
            stage = "all"
        with self.store.Session() as session:
            waitlist_rows = session.execute(
                select(
                    AnalyticsEvent.telegram_user_id,
                    func.min(AnalyticsEvent.occurred_at),
                )
                .join(
                    User,
                    User.telegram_user_id == AnalyticsEvent.telegram_user_id,
                )
                .where(
                    User.role == "learner",
                    AnalyticsEvent.event_name == "pilot_waitlist_joined",
                )
                .group_by(AnalyticsEvent.telegram_user_id)
            ).all()
            joined_at = {
                int(user_id): _as_utc(observed_at)
                for user_id, observed_at in waitlist_rows
            }
            cohort_ids = set(joined_at)
            block_rows = (
                session.execute(
                    select(
                        AnalyticsEvent.telegram_user_id,
                        AnalyticsEvent.occurred_at,
                    ).where(
                        AnalyticsEvent.telegram_user_id.in_(cohort_ids),
                        AnalyticsEvent.event_name == "block_started",
                    )
                ).all()
                if cohort_ids
                else []
            )
        activated_ids = {
            int(user_id)
            for user_id, observed_at in block_rows
            if _as_utc(observed_at) >= joined_at[int(user_id)]
        }
        result = []
        for user in self.users(limit=10000):
            if user["id"] not in cohort_ids:
                continue
            if user["access_status"] == "blocked":
                pilot_stage = "blocked"
            elif user["access_status"] == "pending":
                pilot_stage = "pending"
            elif not user["onboarding_completed_at"]:
                pilot_stage = "onboarding"
            elif user["id"] not in activated_ids:
                pilot_stage = "first_block"
            else:
                pilot_stage = "engaged"
            if stage != "all" and pilot_stage != stage:
                continue
            result.append(dict(user, pilot_stage=pilot_stage))
            if len(result) >= max(1, min(int(limit), 1000)):
                break
        return result

    def product_funnel(self, *, days: int = 30) -> dict[str, Any]:
        days = max(1, min(int(days), 365))
        since = datetime.now(timezone.utc) - timedelta(days=days)
        event_steps = [
            ("start_received", "Открыли /start"),
            ("onboarding_completed", "Завершили настройку"),
            ("block_started", "Открыли учебный блок"),
            ("ai_paywall_shown", "Увидели предложение"),
            ("buy_opened", "Открыли покупку"),
            ("billing_terms_accepted", "Приняли условия"),
            ("billing_package_selected", "Выбрали пакет"),
            ("billing_invoice_created", "Получили счёт"),
        ]
        event_names = [name for name, _ in event_steps]
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
            order_events, order_users = session.execute(
                select(
                    func.count(PaymentOrder.order_id),
                    func.count(func.distinct(PaymentOrder.telegram_user_id)),
                ).where(PaymentOrder.created_at >= since)
            ).one()
            payment_events, payment_users, gross_xtr, refunded_xtr = session.execute(
                select(
                    func.count(StarsPayment.payment_id),
                    func.count(func.distinct(StarsPayment.telegram_user_id)),
                    func.coalesce(func.sum(StarsPayment.total_amount), 0),
                    func.coalesce(
                        func.sum(
                            case(
                                (StarsPayment.status == "refunded", StarsPayment.total_amount),
                                else_=0,
                            )
                        ),
                        0,
                    ),
                ).where(StarsPayment.received_at >= since)
            ).one()
            ai_events, ai_users = session.execute(
                select(
                    func.count(AIUsage.request_id),
                    func.count(func.distinct(AIUsage.telegram_user_id)),
                ).where(
                    AIUsage.created_at >= since,
                    AIUsage.status == "completed",
                )
            ).one()
            ai_provider_cost = session.execute(
                select(func.coalesce(func.sum(AIUsage.cost_micro_usd), 0)).where(
                    AIUsage.created_at >= since
                )
            ).scalar_one()
            payment_counts = (
                select(
                    StarsPayment.telegram_user_id.label("telegram_user_id"),
                    func.count(StarsPayment.payment_id).label("payment_count"),
                )
                .where(StarsPayment.received_at >= since)
                .group_by(StarsPayment.telegram_user_id)
                .subquery()
            )
            repeat_users, repeat_events = session.execute(
                select(
                    func.count(payment_counts.c.telegram_user_id),
                    func.coalesce(func.sum(payment_counts.c.payment_count), 0),
                ).where(payment_counts.c.payment_count >= 2)
            ).one()
        aggregates = {
            row[0]: {"events": int(row[1]), "users": int(row[2])}
            for row in rows
        }
        durable_steps = {
            "invoice_created": {
                "label": "Создали счёт",
                "events": int(order_events or 0),
                "users": int(order_users or 0),
            },
            "stars_payment_completed": {
                "label": "Успешно оплатили",
                "events": int(payment_events or 0),
                "users": int(payment_users or 0),
            },
            "ai_request_completed": {
                "label": "Использовали AI",
                "events": int(ai_events or 0),
                "users": int(ai_users or 0),
            },
            "repeat_purchase": {
                "label": "Купили повторно",
                "events": int(repeat_events or 0),
                "users": int(repeat_users or 0),
            },
        }
        starts = aggregates.get("start_received", {}).get("users", 0)
        steps = [
            {
                "event_name": name,
                "label": label,
                "events": aggregates.get(name, {}).get("events", 0),
                "users": aggregates.get(name, {}).get("users", 0),
                "source": "analytics",
            }
            for name, label in event_steps
        ]
        steps.extend(
            dict(event_name=name, source="ledger", **values)
            for name, values in durable_steps.items()
        )
        for step in steps:
            step["conversion"] = step["users"] / starts * 100 if starts else 0
        net_xtr = int(gross_xtr or 0) - int(refunded_xtr or 0)
        estimated_revenue = max(
            0,
            net_xtr * int(self.billing_settings.net_micro_usd_per_xtr or 0),
        )
        provider_cost = int(ai_provider_cost or 0)
        estimated_contribution = estimated_revenue - provider_cost
        return {
            "days": days,
            "steps": steps,
            "commercial": {
                "orders": int(order_events or 0),
                "payments": int(payment_events or 0),
                "payers": int(payment_users or 0),
                "gross_xtr": int(gross_xtr or 0),
                "refunded_xtr": int(refunded_xtr or 0),
                "net_xtr": net_xtr,
                "ai_provider_cost_micro_usd": provider_cost,
                "estimated_contribution_micro_usd": estimated_contribution,
                "estimated_contribution_margin_bps": (
                    estimated_contribution * 10000 // estimated_revenue
                    if estimated_revenue
                    else None
                ),
            },
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
        billing_mode: str = "one_time",
        subscription_period_seconds: int | None = None,
    ) -> dict[str, Any]:
        product_id = str(product_id).strip().lower()
        title = str(title).strip()
        description = str(description).strip()
        status = str(status).strip().lower()
        billing_mode = str(billing_mode).strip().lower()
        if not PRODUCT_ID_RE.fullmatch(product_id):
            raise ValueError("Product ID must use lowercase letters, digits, and hyphens")
        if not 1 <= len(title) <= 32 or not 1 <= len(description) <= 255:
            raise ValueError("Product title or description is outside Telegram limits")
        if status not in PRODUCT_STATUSES:
            raise ValueError("Unknown billing product status")
        if billing_mode not in BILLING_MODES:
            raise ValueError("Unknown billing product mode")
        if billing_mode == "subscription":
            if int(subscription_period_seconds or 0) != SUBSCRIPTION_PERIOD_SECONDS:
                raise ValueError("Stars subscriptions must use a 30-day period")
            subscription_period_seconds = SUBSCRIPTION_PERIOD_SECONDS
        elif subscription_period_seconds not in {None, 0}:
            raise ValueError("One-time products cannot have a subscription period")
        else:
            subscription_period_seconds = None
        if not 1 <= int(credits) <= 1_000_000:
            raise ValueError("Product credits must be between 1 and 1000000")
        if not 1 <= int(price_xtr) <= 1_000_000:
            raise ValueError("Product price must be between 1 and 1000000 XTR")
        if billing_mode == "subscription" and int(price_xtr) > 10_000:
            raise ValueError("Stars subscription price cannot exceed 10000 XTR")
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
            row.billing_mode = billing_mode
            row.subscription_period_seconds = subscription_period_seconds
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
                            "billing_mode": billing_mode,
                            "subscription_period_seconds": (
                                subscription_period_seconds
                            ),
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
                select(func.sum(PaymentOrder.credits_snapshot))
                .join(StarsPayment, StarsPayment.order_id == PaymentOrder.order_id)
                .where(StarsPayment.status.in_({"paid", "refund_pending"}))
            ) or 0
            active_subscriptions = session.scalar(
                select(func.count(StarsSubscription.subscription_id)).where(
                    StarsSubscription.status == "active"
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
            "active_subscriptions": int(active_subscriptions),
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
                "subscription_id": payment.subscription_id,
                "is_recurring": payment.is_recurring,
                "is_first_recurring": payment.is_first_recurring,
                "subscription_expiration_date": (
                    payment.subscription_expiration_date
                ),
                "status": payment.status,
                "received_at": payment.received_at,
                "refunded_at": payment.refunded_at,
            }
            for payment, order in rows
        ]

    def stars_subscriptions(self, limit: int = 100) -> list[dict[str, Any]]:
        with self.store.Session() as session:
            rows = session.execute(
                select(StarsSubscription, PaymentOrder)
                .join(PaymentOrder, PaymentOrder.order_id == StarsSubscription.order_id)
                .order_by(StarsSubscription.created_at.desc())
                .limit(max(1, min(int(limit), 1000)))
            ).all()
        return [
            {
                "subscription_id": subscription.subscription_id,
                "order_id": subscription.order_id,
                "telegram_user_id": subscription.telegram_user_id,
                "product_id": subscription.product_id,
                "product_title": order.product_title,
                "credits": order.credits_snapshot,
                "amount_xtr": order.amount_xtr,
                "status": subscription.status,
                "period_seconds": subscription.period_seconds,
                "current_period_end": subscription.current_period_end,
                "cancelled_at": subscription.cancelled_at,
                "created_at": subscription.created_at,
            }
            for subscription, order in rows
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
            payments = session.execute(select(StarsPayment)).scalars().all()
            for payment in payments:
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

    def safety_overview(self) -> dict[str, int]:
        now = utcnow()
        since = now - timedelta(hours=24)
        with self.store.Session() as session:
            events = session.scalar(
                select(func.count()).select_from(AbuseEvent).where(
                    AbuseEvent.occurred_at >= since
                )
            ) or 0
            affected_users = session.scalar(
                select(func.count(func.distinct(AbuseEvent.telegram_user_id))).where(
                    AbuseEvent.occurred_at >= since
                )
            ) or 0
            active_blocks = session.scalar(
                select(func.count()).select_from(RateLimitBucket).where(
                    RateLimitBucket.blocked_until > now
                )
            ) or 0
            erased_users = session.scalar(
                select(func.count()).select_from(User).where(
                    User.privacy_status == "erased"
                )
            ) or 0
        return {
            "events_24h": int(events),
            "affected_users_24h": int(affected_users),
            "active_blocks": int(active_blocks),
            "erased_users": int(erased_users),
        }

    def recent_abuse_events(self, limit: int = 100) -> list[dict[str, Any]]:
        with self.store.Session() as session:
            rows = session.execute(
                select(AbuseEvent)
                .order_by(AbuseEvent.occurred_at.desc())
                .limit(max(1, min(int(limit), 1000)))
            ).scalars().all()
        return [
            {
                column.name: getattr(row, column.name)
                for column in AbuseEvent.__table__.columns
            }
            for row in rows
        ]

    def voice_overview(self) -> dict[str, Any]:
        with self.store.Session() as session:
            sessions = session.scalar(
                select(func.count()).select_from(VoiceSession)
            ) or 0
            active = session.scalar(
                select(func.count()).select_from(VoiceSession).where(
                    VoiceSession.status == "active"
                )
            ) or 0
            turns = session.scalar(
                select(func.count()).select_from(VoiceTurn)
            ) or 0
            average = session.scalar(select(func.avg(VoiceTurn.similarity_bps))) or 0
            feedback_rows = session.execute(
                select(VoiceTurn.feedback_code, func.count(VoiceTurn.turn_id)).group_by(
                    VoiceTurn.feedback_code
                )
            ).all()
        return {
            "sessions": int(sessions),
            "active_sessions": int(active),
            "turns": int(turns),
            "average_similarity_percent": float(average) / 100,
            "feedback": {row[0]: int(row[1]) for row in feedback_rows},
        }

    def recent_voice_turns(self, limit: int = 100) -> list[dict[str, Any]]:
        with self.store.Session() as session:
            rows = session.execute(
                select(
                    VoiceTurn,
                    VoiceSession.pack_id,
                    VoiceSession.language,
                    VoiceSession.mode,
                )
                .join(VoiceSession, VoiceSession.session_id == VoiceTurn.session_id)
                .order_by(VoiceTurn.created_at.desc())
                .limit(max(1, min(int(limit), 1000)))
            ).all()
        return [
            {
                "turn_id": turn.turn_id,
                "telegram_user_id": turn.telegram_user_id,
                "pack_id": pack_id,
                "language": language,
                "mode": mode,
                "expected_vocabulary_id": turn.expected_vocabulary_id,
                "matched_vocabulary_id": turn.matched_vocabulary_id or "",
                "feedback_code": turn.feedback_code,
                "similarity_percent": turn.similarity_bps / 100,
                "created_at": turn.created_at,
                "expires_at": turn.expires_at,
            }
            for turn, pack_id, language, mode in rows
        ]

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
