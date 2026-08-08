"""Loopback-first administration console for MY DICTIONARY."""

from __future__ import annotations

from collections import defaultdict, deque
import csv
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from functools import wraps
import getpass
import hmac
import io
import json
import os
from pathlib import Path
import secrets
import sys
from threading import Lock
import time
from typing import Any, Callable

from flask import (
    Flask,
    Response,
    abort,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from sqlalchemy import text
from werkzeug.security import check_password_hash, generate_password_hash

from mydictionary.admin_store import AdminStore
from mydictionary.ai_metering import AIMeteringJournal
from mydictionary.bot_profile import BOT_PROFILE_DEFAULTS, validate_bot_profile
from mydictionary.catalog import load_catalog
from mydictionary.content import example_target_text
from mydictionary.commercial_launch import (
    CommercialLaunchError,
    commercial_launch_overview,
)
from mydictionary.economics import (
    EconomicsSnapshotError,
    load_ai_economics_contract,
    require_current_review,
    review_is_current,
)
from mydictionary.readiness import (
    configured_max_age_seconds,
    heartbeat_path,
    inspect_bot_heartbeat,
)
from mydictionary.privacy import RetentionPolicy
from mydictionary.secret_enrollment import (
    SecretEnrollmentError,
    SecretEnrollmentSettings,
)
from mydictionary.storage import DatabaseStore
from vocabulary_topics import topic_counts, transcription_for


BASE_DIR = Path(__file__).resolve().parents[1]
CATALOG = load_catalog(BASE_DIR)
LANG_LABELS = {
    pack.target_language: pack.label for pack in CATALOG.packs
}
ADMIN_TABS = {
    "dashboard",
    "users",
    "pilot",
    "funnel",
    "learning",
    "ai",
    "billing",
    "voice",
    "safety",
    "content",
    "profile",
    "diagnostics",
    "audit",
}


def _positive_decimal_setting(name: str) -> bool:
    try:
        value = Decimal(os.environ.get(name, "0"))
    except (InvalidOperation, ValueError):
        return False
    return value.is_finite() and value > 0


def _review_setting_current(date_name: str, age_name: str) -> bool:
    try:
        max_age_days = int(os.environ.get(age_name, "30"))
    except ValueError:
        return False
    return review_is_current(
        os.environ.get(date_name, ""), max_age_days=max_age_days
    )


def _ai_metering_journal() -> AIMeteringJournal:
    configured = os.environ.get("AI_METERING_JOURNAL_PATH", "").strip()
    data_dir = Path(os.environ.get("DATA_DIR", str(BASE_DIR))).expanduser()
    return AIMeteringJournal(
        Path(configured).expanduser()
        if configured
        else data_dir / "ai-metering-fallback.jsonl"
    )


def _ai_snapshot_diagnostics() -> dict[str, Any]:
    path = os.environ.get("AI_ECONOMICS_SNAPSHOT_PATH", "").strip()
    snapshot_id = os.environ.get("AI_ECONOMICS_SNAPSHOT_ID", "").strip()
    digest = os.environ.get("AI_ECONOMICS_SNAPSHOT_SHA256", "").strip()
    result = {
        "valid": False,
        "approved": False,
        "current": False,
        "status": "missing",
    }
    if not path or not snapshot_id or not digest:
        return result
    try:
        contract = load_ai_economics_contract(
            path,
            expected_snapshot_id=snapshot_id,
            expected_snapshot_sha256=digest,
        )
        require_current_review(
            contract.reviewed_on,
            max_age_days=contract.max_age_days,
            setting_name="AI economics snapshot",
        )
    except (EconomicsSnapshotError, OSError, TypeError, ValueError):
        return result
    return {
        "valid": True,
        "approved": contract.status == "approved",
        "current": True,
        "status": contract.status,
    }


def _commercial_launch_diagnostics(
    products: list[dict[str, Any]], admin_store: AdminStore
) -> dict[str, Any]:
    fallback = {
        "status": "invalid",
        "snapshot_id": "missing",
        "snapshot_sha256": "missing",
        "contract_ready": False,
        "catalog_status": "missing",
        "seller_complete": False,
        "terms_approved": False,
        "checkout_enabled": False,
        "measurement": {},
        "packages": [],
    }
    path = BASE_DIR / "config" / "launch-economics.json"
    try:
        snapshot = json.loads(path.read_text(encoding="utf-8"))
        return commercial_launch_overview(
            snapshot,
            products=products,
            seller_complete=admin_store.billing_settings.seller_identity_complete,
            terms_approved=admin_store.billing_settings.terms_approved,
            checkout_enabled=admin_store.billing_settings.enabled,
            root=BASE_DIR,
        )
    except (CommercialLaunchError, OSError, TypeError, ValueError, json.JSONDecodeError):
        return fallback


def database_url_from_env() -> str:
    configured = os.environ.get("DATABASE_URL", "").strip()
    if configured.startswith("postgres://"):
        return configured.replace("postgres://", "postgresql+psycopg://", 1)
    if configured.startswith("postgresql://"):
        return configured.replace(
            "postgresql://", "postgresql+psycopg://", 1
        )
    if configured:
        return configured
    if os.environ.get("ALLOW_SQLITE_DEV", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }:
        return f"sqlite:///{(BASE_DIR / 'mydictionary.db').resolve()}"
    raise RuntimeError("DATABASE_URL is required for the admin console")


class LoginLimiter:
    def __init__(self, *, attempts: int = 5, window_seconds: int = 300):
        self.attempts = attempts
        self.window_seconds = window_seconds
        self._events: dict[str, deque[float]] = defaultdict(deque)
        self._lock = Lock()

    def allowed(self, key: str) -> bool:
        with self._lock:
            now = time.monotonic()
            events = self._events[key]
            while events and now - events[0] > self.window_seconds:
                events.popleft()
            return len(events) < self.attempts

    def failure(self, key: str) -> None:
        with self._lock:
            self._events[key].append(time.monotonic())

    def success(self, key: str) -> None:
        with self._lock:
            self._events.pop(key, None)


def _content_overview() -> list[dict[str, Any]]:
    result = []
    for pack in CATALOG.packs:
        words = CATALOG.words(pack)
        transcribed = sum(
            1
            for word in words
            if transcription_for(word, pack.target_language)
        )
        examples = sum(1 for word in words if example_target_text(word))
        topics = topic_counts(
            words,
            pack.target_language,
            topic_labels=CATALOG.topic_labels,
        )
        result.append(
            {
                "pack_id": pack.pack_id,
                "language": pack.target_language,
                "label": pack.label,
                "title": pack.title,
                "filename": pack.filename,
                "visibility": pack.visibility,
                "is_free": pack.is_free,
                "status": pack.status,
                "version": pack.content_version,
                "words": len(words),
                "transcribed": transcribed,
                "examples": examples,
                "topic_count": len(topics),
                "topics": [
                    {
                        "id": topic,
                        "label": CATALOG.topic_labels.get(topic, topic),
                        "words": count,
                    }
                    for topic, count in topics.items()
                ],
            }
        )
    return result


def _csv_response(filename: str, rows: list[dict[str, Any]]) -> Response:
    output = io.StringIO(newline="")
    if rows:
        headers = list(rows[0])
        writer = csv.DictWriter(output, fieldnames=headers, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    key: value.isoformat() if isinstance(value, datetime) else value
                    for key, value in row.items()
                }
            )
    response = Response(output.getvalue(), mimetype="text/csv")
    response.headers["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


def create_app(
    test_config: dict[str, Any] | None = None,
    *,
    database_store: DatabaseStore | None = None,
) -> Flask:
    app = Flask(__name__)
    data_dir = Path(os.environ.get("DATA_DIR", str(BASE_DIR)))
    app.config.from_mapping(
        SECRET_KEY=os.environ.get("ADMIN_SESSION_SECRET", ""),
        ADMIN_USERNAME=os.environ.get("ADMIN_USERNAME", "").strip(),
        ADMIN_PASSWORD=os.environ.get("ADMIN_PASSWORD", ""),
        ADMIN_PASSWORD_HASH=os.environ.get("ADMIN_PASSWORD_HASH", ""),
        ADMIN_HOST=os.environ.get("ADMIN_HOST", "127.0.0.1").strip(),
        ADMIN_PORT=int(os.environ.get("ADMIN_PORT", "8787")),
        DATA_DIR=str(data_dir),
        BOT_HEARTBEAT_PATH=str(heartbeat_path(data_dir)),
        BOT_HEARTBEAT_MAX_AGE_SECONDS=configured_max_age_seconds(),
        SESSION_COOKIE_NAME="mydictionary_admin_session",
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Strict",
        SESSION_COOKIE_SECURE=(
            os.environ.get("ADMIN_COOKIE_SECURE", "false").strip().lower()
            in {"1", "true", "yes", "on"}
        ),
        AI_KEY_ENROLLMENT_ENABLED=os.environ.get(
            "AI_KEY_ENROLLMENT_ENABLED", "false"
        ),
        AI_KEY_ENROLLMENT_PATH=os.environ.get("AI_KEY_ENROLLMENT_PATH", ""),
        AI_KEY_ENROLLMENT_EXPIRES_AT=os.environ.get(
            "AI_KEY_ENROLLMENT_EXPIRES_AT", ""
        ),
        MAX_CONTENT_LENGTH=64 * 1024,
    )
    if test_config:
        app.config.update(test_config)
    session_secret = app.config.get("SECRET_KEY")
    if not session_secret:
        raise RuntimeError("ADMIN_SESSION_SECRET is required")
    if len(session_secret) < 32:
        raise RuntimeError(
            "ADMIN_SESSION_SECRET must contain at least 32 characters"
        )

    store = database_store or DatabaseStore(database_url_from_env())
    admin_store = AdminStore(store)
    key_enrollment = SecretEnrollmentSettings.from_mapping(
        app.config,
        allowed_directory=Path(app.config["DATA_DIR"]) / "local-config",
    )
    app.extensions["database_store"] = store
    app.extensions["admin_store"] = admin_store
    app.extensions["ai_key_enrollment"] = key_enrollment
    limiter = LoginLimiter()

    username = str(app.config.get("ADMIN_USERNAME") or "").strip()
    password = str(app.config.get("ADMIN_PASSWORD") or "")
    configured_hash = str(app.config.get("ADMIN_PASSWORD_HASH") or "").strip()
    bootstrap_hash = configured_hash or (
        generate_password_hash(password) if len(password) >= 12 else ""
    )
    if admin_store.credential() is None and username and bootstrap_hash:
        admin_store.bootstrap_credential(
            username=username,
            password_hash=bootstrap_hash,
        )

    def current_credential():
        return admin_store.credential()

    def admin_configured() -> bool:
        return current_credential() is not None

    def current_actor() -> str:
        return str(session.get("admin_username") or "unknown")

    def csrf_token() -> str:
        token = session.get("csrf_token")
        if not token:
            token = secrets.token_urlsafe(32)
            session["csrf_token"] = token
        return str(token)

    def login_required(handler: Callable):
        @wraps(handler)
        def wrapped(*args, **kwargs):
            credential = current_credential()
            if credential is None:
                return render_template("admin/login.html", unavailable=True), 503
            valid = (
                session.get("admin_username") == credential.username
                and session.get("session_version") == credential.session_version
            )
            if not valid:
                session.clear()
                return redirect(url_for("admin_login"))
            return handler(*args, **kwargs)

        return wrapped

    @app.context_processor
    def template_context():
        return {
            "csrf_token": csrf_token,
            "current_actor": current_actor(),
            "language_labels": LANG_LABELS,
        }

    @app.template_filter("datetime")
    def format_datetime(value):
        if not value:
            return "—"
        if isinstance(value, str):
            try:
                value = datetime.fromisoformat(value)
            except ValueError:
                return value
        return value.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    @app.template_filter("usd")
    def format_usd(micro_usd):
        return f"${int(micro_usd or 0) / 1_000_000:.6f}"

    @app.template_filter("number")
    def format_number(value):
        return f"{int(value or 0):,}".replace(",", " ")

    @app.before_request
    def verify_csrf():
        if request.method != "POST":
            return None
        supplied = str(request.form.get("csrf_token") or "")
        expected = str(session.get("csrf_token") or "")
        if not supplied or not expected or not hmac.compare_digest(supplied, expected):
            if request.endpoint == "admin_login":
                return redirect(url_for("admin_index"), code=303)
            abort(400, description="Invalid CSRF token")
        return None

    @app.after_request
    def security_headers(response):
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; img-src 'self' data:; style-src 'self'; "
            "script-src 'self'; form-action 'self'; frame-ancestors 'none'; "
            "base-uri 'none'"
        )
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.get("/health")
    def health():
        try:
            with store.engine.connect() as connection:
                connection.execute(text("select 1"))
            bot_readiness = inspect_bot_heartbeat(
                Path(app.config["BOT_HEARTBEAT_PATH"]),
                max_age_seconds=int(
                    app.config["BOT_HEARTBEAT_MAX_AGE_SECONDS"]
                ),
            )
            if bot_readiness.ready:
                return {"status": "ok"}
            return {"status": "unavailable"}, 503
        except Exception:
            return {"status": "unavailable"}, 503

    @app.get("/")
    def root():
        return redirect(url_for("admin_index"))

    @app.route("/admin/login", methods=["GET", "POST"])
    def admin_login():
        if not admin_configured():
            return render_template("admin/login.html", unavailable=True), 503
        if request.method == "GET":
            return render_template("admin/login.html", unavailable=False)
        key = request.remote_addr or "unknown"
        if not limiter.allowed(key):
            return render_template(
                "admin/login.html",
                unavailable=False,
                error="Слишком много попыток. Повторите через несколько минут.",
            ), 429
        credential = current_credential()
        submitted_username = str(request.form.get("username") or "").strip()
        submitted_password = str(request.form.get("password") or "")
        valid = bool(
            credential
            and hmac.compare_digest(submitted_username, credential.username)
            and check_password_hash(credential.password_hash, submitted_password)
        )
        if not valid:
            limiter.failure(key)
            admin_store.record_audit(
                actor=(submitted_username or "unknown")[:64],
                action="admin_login_failed",
                target_type="admin",
            )
            return render_template(
                "admin/login.html",
                unavailable=False,
                error="Неверный логин или пароль.",
            ), 401
        limiter.success(key)
        session.clear()
        session["admin_username"] = credential.username
        session["session_version"] = credential.session_version
        session["csrf_token"] = secrets.token_urlsafe(32)
        admin_store.record_audit(
            actor=credential.username,
            action="admin_login_succeeded",
            target_type="admin",
        )
        return redirect(url_for("admin_index"))

    @app.post("/admin/logout")
    @login_required
    def admin_logout():
        actor = current_actor()
        admin_store.record_audit(
            actor=actor, action="admin_logout", target_type="admin"
        )
        session.clear()
        return redirect(url_for("admin_login"))

    @app.get("/admin")
    @login_required
    def admin_index():
        tab = str(request.args.get("tab") or "dashboard")
        if tab not in ADMIN_TABS:
            tab = "dashboard"
        search = str(request.args.get("q") or "").strip()
        context: dict[str, Any] = {
            "tab": tab,
            "search": search,
            "profile": admin_store.get_settings(),
            "dashboard": admin_store.dashboard(),
            "admin_action_id": secrets.token_urlsafe(18),
        }
        if tab == "dashboard":
            context["users"] = admin_store.users(limit=8)
            context["audit"] = admin_store.audit_log(limit=8)
        elif tab == "users":
            context["users"] = admin_store.users(search=search, limit=250)
        elif tab == "pilot":
            pilot_stage = str(request.args.get("pilot_stage") or "all")
            context["pilot_stage"] = pilot_stage
            context["pilot"] = admin_store.pilot_overview(days=30)
            context["users"] = admin_store.pilot_users(
                stage=pilot_stage,
                limit=250,
            )
        elif tab == "funnel":
            context["funnel"] = admin_store.product_funnel(days=30)
            context["events"] = admin_store.recent_product_events(limit=100)
        elif tab == "learning":
            context["learning"] = admin_store.learning_by_language()
            context["content"] = _content_overview()
        elif tab == "ai":
            context["ai"] = admin_store.ai_overview()
            context["usage"] = admin_store.recent_ai_usage(limit=100)
            context["ledger"] = admin_store.credit_ledger(limit=100)
        elif tab == "billing":
            context["billing"] = admin_store.billing_overview()
            context["products"] = admin_store.billing_products()
            context["commercial_launch"] = _commercial_launch_diagnostics(
                context["products"], admin_store
            )
            context["orders"] = admin_store.recent_payment_orders(limit=100)
            context["payments"] = admin_store.stars_payments(limit=100)
            context["subscriptions"] = admin_store.stars_subscriptions(limit=100)
            context["refunds"] = admin_store.refund_requests(limit=100)
            context["reconciliation"] = admin_store.billing_reconciliation()
        elif tab == "safety":
            context["safety"] = admin_store.safety_overview()
            context["abuse_events"] = admin_store.recent_abuse_events(limit=100)
            retention = RetentionPolicy.from_env()
            context["retention"] = {
                "analytics_days": retention.analytics_days,
                "ai_usage_days": retention.ai_usage_days,
                "abuse_days": retention.abuse_days,
                "rate_limit_days": retention.rate_limit_days,
                "voice_transcript_days": retention.voice_transcript_days,
            }
        elif tab == "voice":
            context["voice"] = admin_store.voice_overview()
            context["voice_turns"] = admin_store.recent_voice_turns(limit=100)
        elif tab == "content":
            context["content"] = _content_overview()
        elif tab == "diagnostics":
            with store.engine.connect() as connection:
                revision = connection.execute(
                    text("select version_num from alembic_version")
                ).scalar_one()
            bot_readiness = inspect_bot_heartbeat(
                Path(app.config["BOT_HEARTBEAT_PATH"]),
                max_age_seconds=int(
                    app.config["BOT_HEARTBEAT_MAX_AGE_SECONDS"]
                ),
            )
            ai_budget = store.ai_budget_status()
            metering_journal_pending = _ai_metering_journal().pending_count()
            ai_snapshot = _ai_snapshot_diagnostics()
            context["diagnostics"] = {
                "database": store.engine.dialect.name,
                "migration": revision,
                "ai_enabled": os.environ.get("AI_TUTOR_ENABLED", "false"),
                "ai_provider_configured": (
                    os.environ.get("AI_PROVIDER_CONFIGURED", "false").lower()
                    in {"1", "true", "yes", "on"}
                    or bool(os.environ.get("OPENAI_API_KEY"))
                ),
                "ai_pricing_configured": all(
                    _positive_decimal_setting(name)
                    for name in (
                        "AI_INPUT_USD_PER_MILLION",
                        "AI_CACHED_INPUT_USD_PER_MILLION",
                        "AI_CACHE_WRITE_USD_PER_MILLION",
                        "AI_OUTPUT_USD_PER_MILLION",
                    )
                ),
                "ai_pricing_reviewed_on": os.environ.get(
                    "AI_PRICING_REVIEWED_ON", "missing"
                ),
                "ai_pricing_review_current": _review_setting_current(
                    "AI_PRICING_REVIEWED_ON", "AI_PRICING_MAX_AGE_DAYS"
                ),
                "ai_daily_request_limit": os.environ.get(
                    "AI_MAX_DAILY_REQUESTS_PER_USER", "5"
                ),
                "ai_service_tier": os.environ.get("AI_SERVICE_TIER", "default"),
                "ai_snapshot_id": os.environ.get(
                    "AI_ECONOMICS_SNAPSHOT_ID", "missing"
                ),
                "ai_snapshot_sha256": os.environ.get(
                    "AI_ECONOMICS_SNAPSHOT_SHA256", "missing"
                ),
                "ai_snapshot": ai_snapshot,
                "ai_preflight_budget_micro_usd": os.environ.get(
                    "AI_MAX_PREFLIGHT_COST_MICRO_USD_PER_REQUEST", "5000"
                ),
                "ai_retrospective_breaker_micro_usd": os.environ.get(
                    "AI_RETROSPECTIVE_BREAKER_MICRO_USD_PER_RESPONSE", "5000"
                ),
                "ai_project_daily_budget_micro_usd": os.environ.get(
                    "AI_MAX_PROJECT_COST_MICRO_USD_PER_DAY", "25000"
                ),
                "ai_project_monthly_budget_micro_usd": os.environ.get(
                    "AI_MAX_PROJECT_COST_MICRO_USD_PER_MONTH", "100000"
                ),
                "ai_in_flight_budget_micro_usd": os.environ.get(
                    "AI_MAX_IN_FLIGHT_COST_MICRO_USD", "5000"
                ),
                "ai_budget": ai_budget,
                "ai_metering_journal_pending": metering_journal_pending,
                "ai_key_enrollment_status": key_enrollment.status(),
                "ai_key_enrollment_expires_at": (
                    key_enrollment.expires_at.isoformat()
                    if key_enrollment.expires_at
                    else "not configured"
                ),
                "stars_enabled": admin_store.billing_settings.enabled,
                "stars_unit_economics": (
                    admin_store.billing_settings.net_micro_usd_per_xtr > 0
                ),
                "voice_enabled": os.environ.get("VOICE_TUTOR_ENABLED", "false"),
                "voice_model": os.environ.get(
                    "VOICE_TRANSCRIPTION_MODEL", "gpt-4o-transcribe"
                ),
                "billing_terms_version": admin_store.billing_settings.terms_version,
                "billing_terms_approved": (
                    admin_store.billing_settings.terms_approved
                ),
                "billing_economics_reviewed_on": (
                    admin_store.billing_settings.economics_reviewed_on or "missing"
                ),
                "billing_economics_review_current": review_is_current(
                    admin_store.billing_settings.economics_reviewed_on or "",
                    max_age_days=(
                        admin_store.billing_settings.economics_max_age_days
                    ),
                ),
                "billing_private_chat_topics": (
                    admin_store.billing_settings.private_chat_topics_enabled
                ),
                "voice_consent_version": os.environ.get(
                    "VOICE_CONSENT_VERSION", "unversioned"
                ),
                "admin_host": app.config["ADMIN_HOST"],
                "admin_port": app.config["ADMIN_PORT"],
                "release_sha": os.environ.get("RELEASE_SHA", "not set"),
                "welcome_banner": (BASE_DIR / "assets/mydictionary-welcome.jpg").exists(),
                "bot_ready": bot_readiness.ready,
                "bot_state": bot_readiness.state,
                "bot_reason": bot_readiness.reason,
                "bot_heartbeat_age_seconds": bot_readiness.age_seconds,
                "bot_release_sha": bot_readiness.release_sha,
                "bot_access_mode": bot_readiness.access_mode,
            }

        elif tab == "audit":
            context["audit"] = admin_store.audit_log(limit=250)
        return render_template("admin/index.html", **context)

    @app.get("/admin/ai-key")
    @login_required
    def ai_key_enrollment():
        state = key_enrollment.status()
        if state == "disabled":
            abort(404)
        return (
            render_template(
                "admin/ai_key.html",
                state=state,
                expires_at=key_enrollment.expires_at,
            ),
            410 if state == "expired" else 200,
        )

    @app.post("/admin/ai-key")
    @login_required
    def enroll_ai_key():
        try:
            fingerprint = key_enrollment.enroll(
                str(request.form.get("api_key") or "")
            )
        except SecretEnrollmentError:
            state = key_enrollment.status()
            reason = "invalid_key" if state == "ready" else state
            admin_store.record_audit(
                actor=current_actor(),
                action="ai_key_enrollment_rejected",
                target_type="provider_credential",
                target_id="openai",
                details={"reason": reason},
            )
            messages = {
                "ready": "Ключ не принят. Проверьте формат project API key.",
                "consumed": "Одноразовое окно уже использовано.",
                "expired": "Срок действия одноразового окна истёк.",
                "disabled": "Одноразовое окно выключено.",
            }
            return (
                render_template(
                    "admin/ai_key.html",
                    state=state,
                    expires_at=key_enrollment.expires_at,
                    error=messages.get(state, "Ключ не принят."),
                ),
                {"ready": 400, "consumed": 409, "expired": 410}.get(
                    state, 404
                ),
            )
        admin_store.record_audit(
            actor=current_actor(),
            action="ai_key_enrolled",
            target_type="provider_credential",
            target_id="openai",
            details={"fingerprint_sha256_12": fingerprint},
        )
        session["csrf_token"] = secrets.token_urlsafe(32)
        return redirect(url_for("ai_key_enrollment"), code=303)

    @app.post("/admin/ai/breaker/reset")
    @login_required
    def reset_ai_breaker():
        try:
            if _ai_metering_journal().pending_count():
                raise RuntimeError(
                    "Нельзя сбросить breaker: metering journal не reconciled."
                )
            changed = store.reset_ai_breaker(
                actor=current_actor(),
                reason=str(request.form.get("reason") or ""),
            )
            flash(
                "AI breaker сброшен." if changed else "AI breaker уже закрыт.",
                "success",
            )
        except (TypeError, ValueError, RuntimeError) as exc:
            flash(str(exc), "error")
        return redirect(url_for("admin_index", tab="diagnostics"))

    @app.post("/admin/settings/profile")
    @login_required
    def update_profile():
        values = {
            key: str(request.form.get(key) or "")
            for key in BOT_PROFILE_DEFAULTS
        }
        try:
            validated = validate_bot_profile(values)
            admin_store.update_settings(validated, actor=current_actor())
            flash("Профиль и приветствие бота сохранены.", "success")
        except ValueError as exc:
            flash(str(exc), "error")
        return redirect(url_for("admin_index", tab="profile"))

    @app.post("/admin/credits")
    @login_required
    def adjust_credits():
        try:
            user_id = int(str(request.form.get("user_id") or ""))
            delta = int(str(request.form.get("delta") or ""))
            balance = admin_store.adjust_credits(
                user_id,
                delta=delta,
                reason=str(request.form.get("reason") or ""),
                actor=current_actor(),
                idempotency_key=(
                    "admin:" + str(request.form.get("action_id") or "").strip()
                    if request.form.get("action_id")
                    else None
                ),
            )
            flash(f"Новый доступный баланс пользователя {user_id}: {balance}.", "success")
        except (TypeError, ValueError, RuntimeError) as exc:
            flash(str(exc), "error")
        return redirect(url_for("admin_index", tab="ai"))

    @app.post("/admin/billing/products")
    @login_required
    def update_billing_product():
        try:
            product = admin_store.upsert_billing_product(
                product_id=str(request.form.get("product_id") or ""),
                title=str(request.form.get("title") or ""),
                description=str(request.form.get("description") or ""),
                credits=int(str(request.form.get("credits") or "")),
                price_xtr=int(str(request.form.get("price_xtr") or "")),
                status=str(request.form.get("status") or "draft"),
                estimated_cost_micro_usd=int(
                    str(request.form.get("estimated_cost_micro_usd") or "0")
                ),
                target_margin_bps=int(
                    str(request.form.get("target_margin_bps") or "0")
                ),
                display_order=int(str(request.form.get("display_order") or "0")),
                actor=current_actor(),
                billing_mode=str(
                    request.form.get("billing_mode") or "one_time"
                ),
                subscription_period_seconds=(
                    int(str(request.form.get("subscription_period_seconds") or "0"))
                    or None
                ),
            )
            flash(f"Продукт {product['product_id']} сохранён.", "success")
        except (TypeError, ValueError) as exc:
            flash(str(exc), "error")
        return redirect(url_for("admin_index", tab="billing"))

    @app.post("/admin/billing/refunds")
    @login_required
    def request_billing_refund():
        try:
            refund_id = admin_store.request_stars_refund(
                payment_id=str(request.form.get("payment_id") or ""),
                reason=str(request.form.get("reason") or ""),
                actor=current_actor(),
            )
            flash(f"Refund-заявка {refund_id} создана.", "success")
        except (TypeError, ValueError, RuntimeError) as exc:
            flash(str(exc), "error")
        return redirect(url_for("admin_index", tab="billing"))

    @app.post("/admin/users/<int:user_id>/access")
    @login_required
    def update_user_access(user_id: int):
        try:
            status = admin_store.set_user_access_status(
                user_id,
                status=str(request.form.get("status") or ""),
                actor=current_actor(),
            )
            labels = {
                "pending": "ожидает решения",
                "active": "допущен к пилоту",
                "blocked": "заблокирован",
            }
            flash(f"Пользователь {user_id}: {labels[status]}.", "success")
        except (TypeError, ValueError) as exc:
            flash(str(exc), "error")
        return_tab = str(request.form.get("return_tab") or "users")
        if return_tab == "pilot":
            return redirect(
                url_for(
                    "admin_index",
                    tab="pilot",
                    pilot_stage=str(request.form.get("pilot_stage") or "all"),
                )
            )
        return redirect(url_for("admin_index", tab="users"))

    @app.post("/admin/security")
    @login_required
    def update_security():
        credential = current_credential()
        actor = current_actor()
        current_password = str(request.form.get("current_password") or "")
        new_username = str(request.form.get("username") or "").strip()
        new_password = str(request.form.get("password") or "")
        if not credential or not check_password_hash(
            credential.password_hash, current_password
        ):
            flash("Текущий пароль неверен.", "error")
        elif not 3 <= len(new_username) <= 64 or len(new_password) < 12:
            flash(
                "Логин: от 3 до 64 символов; пароль: минимум 12.",
                "error",
            )
        else:
            version = admin_store.update_credential(
                username=new_username,
                password_hash=generate_password_hash(new_password),
                actor=actor,
            )
            session["admin_username"] = new_username
            session["session_version"] = version
            session["csrf_token"] = secrets.token_urlsafe(32)
            flash("Учётные данные администратора обновлены.", "success")
        return redirect(url_for("admin_index", tab="profile"))

    @app.get("/admin/export/<kind>.csv")
    @login_required
    def export_csv(kind: str):
        exporters = {
            "users": lambda: admin_store.users(limit=10000),
            "learning": admin_store.word_progress_export,
            "ai-usage": admin_store.ai_usage_export,
            "credit-ledger": lambda: admin_store.credit_ledger(limit=10000),
            "payment-orders": admin_store.payment_orders_export,
            "stars-payments": admin_store.stars_payments_export,
            "analytics-events": admin_store.product_events_export,
        }
        if kind not in exporters:
            abort(404)
        rows = exporters[kind]()
        admin_store.record_audit(
            actor=current_actor(),
            action="csv_export_downloaded",
            target_type="export",
            target_id=kind,
            details={"rows": len(rows)},
        )
        return _csv_response(f"mydictionary-{kind}.csv", rows)

    return app


def main() -> None:
    if len(sys.argv) > 1 and sys.argv[1] == "hash-password":
        password = getpass.getpass("Admin password: ")
        if len(password) < 12:
            raise SystemExit("Password must contain at least 12 characters")
        print(generate_password_hash(password))
        return
    app = create_app()
    app.run(
        host=str(app.config["ADMIN_HOST"]),
        port=int(app.config["ADMIN_PORT"]),
        debug=False,
    )


if __name__ == "__main__":
    main()
