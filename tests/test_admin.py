import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from sqlalchemy import select

from mydictionary.admin import LoginLimiter, create_app
from mydictionary.admin_store import AdminStore
from mydictionary.ai_metering import AIMeteringJournal
from mydictionary.billing import BillingService, BillingSettings
from mydictionary.readiness import BotHeartbeat
from mydictionary.storage import (
    AIWallet,
    AIUsage,
    BillingCreditLedger,
    AdminAuditLog,
    AnalyticsEvent,
    DatabaseStore,
    TelegramNotification,
    User,
    UserProgress,
)


class AdminConsoleTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory(prefix="mydictionary-admin-")
        database_path = Path(self.temp_dir.name) / "admin.db"
        self.heartbeat_path = Path(self.temp_dir.name) / "bot-heartbeat.json"
        BotHeartbeat(
            self.heartbeat_path,
            release_sha="test-release",
            access_mode="pilot",
        ).mark_ready()
        self.store = DatabaseStore(f"sqlite:///{database_path}")
        self.local_config_dir = Path(self.temp_dir.name) / "local-config"
        self.local_config_dir.mkdir()
        os.chmod(self.local_config_dir, 0o700)
        self.ai_key_path = self.local_config_dir / "openai-gate2.key"
        self.groq_key_path = self.local_config_dir / "groq-voice.key"
        self.app = create_app(
            {
                "TESTING": True,
                "SECRET_KEY": "test-session-secret-with-at-least-32-chars",
                "ADMIN_USERNAME": "owner",
                "ADMIN_PASSWORD": "test-password-123",
                "DATA_DIR": self.temp_dir.name,
                "BOT_HEARTBEAT_PATH": str(self.heartbeat_path),
                "BOT_HEARTBEAT_MAX_AGE_SECONDS": 45,
                "AI_KEY_ENROLLMENT_ENABLED": "true",
                "AI_KEY_ENROLLMENT_PATH": str(self.ai_key_path),
                "AI_KEY_ENROLLMENT_EXPIRES_AT": (
                    datetime.now(timezone.utc) + timedelta(minutes=30)
                ).isoformat(),
                "GROQ_KEY_ENROLLMENT_ENABLED": "true",
                "GROQ_KEY_ENROLLMENT_PATH": str(self.groq_key_path),
                "GROQ_KEY_ENROLLMENT_EXPIRES_AT": (
                    datetime.now(timezone.utc) + timedelta(minutes=30)
                ).isoformat(),
            },
            database_store=self.store,
        )
        self.client = self.app.test_client()

    def tearDown(self):
        self.store.close()
        self.temp_dir.cleanup()

    def csrf(self, client=None):
        browser = client or self.client
        with browser.session_transaction() as browser_session:
            return browser_session["csrf_token"]

    def login(self, client=None):
        browser = client or self.client
        browser.get("/admin/login")
        response = browser.post(
            "/admin/login",
            data={
                "csrf_token": self.csrf(browser),
                "username": "owner",
                "password": "test-password-123",
            },
        )
        self.assertEqual(response.status_code, 302)
        return response

    def test_admin_requires_auth_and_sets_security_headers(self):
        anonymous = self.client.get("/admin")
        self.assertEqual(anonymous.status_code, 302)
        self.assertEqual(anonymous.headers["Location"], "/admin/login")

        login_page = self.client.get("/admin/login")
        self.assertEqual(login_page.status_code, 200)
        self.assertIn("frame-ancestors 'none'", login_page.headers["Content-Security-Policy"])
        self.assertEqual(login_page.headers["X-Frame-Options"], "DENY")

        self.login()
        dashboard = self.client.get("/admin")
        self.assertEqual(dashboard.status_code, 200)
        self.assertIn("Обзор продукта", dashboard.get_data(as_text=True))

    def test_login_recovers_from_missing_csrf(self):
        self.client.get("/admin/login")
        response = self.client.post(
            "/admin/login",
            data={"username": "owner", "password": "test-password-123"},
        )
        self.assertEqual(response.status_code, 303)
        self.assertEqual(response.headers["Location"], "/admin")

        login_redirect = self.client.get(response.headers["Location"])
        self.assertEqual(login_redirect.status_code, 302)
        self.assertEqual(login_redirect.headers["Location"], "/admin/login")
        fresh_login = self.client.get(login_redirect.headers["Location"])
        self.assertEqual(fresh_login.status_code, 200)
        self.assertTrue(self.csrf())

    def test_remote_ai_key_enrollment_is_authenticated_one_time_and_private(self):
        secret = "sk-proj-" + "A" * 48
        anonymous = self.client.get("/admin/ai-key")
        self.assertEqual(anonymous.status_code, 302)
        self.assertEqual(anonymous.headers["Location"], "/admin/login")

        self.login()
        page = self.client.get("/admin/ai-key")
        self.assertEqual(page.status_code, 200)
        self.assertIn('type="password"', page.get_data(as_text=True))
        self.assertEqual(page.headers["Cache-Control"], "no-store")

        missing_csrf = self.client.post(
            "/admin/ai-key", data={"api_key": secret}
        )
        self.assertEqual(missing_csrf.status_code, 400)
        self.assertFalse(self.ai_key_path.exists())

        invalid = self.client.post(
            "/admin/ai-key",
            data={"csrf_token": self.csrf(), "api_key": "not-a-key"},
        )
        self.assertEqual(invalid.status_code, 400)
        self.assertNotIn("not-a-key", invalid.get_data(as_text=True))
        self.assertFalse(self.ai_key_path.exists())

        accepted = self.client.post(
            "/admin/ai-key",
            data={"csrf_token": self.csrf(), "api_key": secret},
        )
        self.assertEqual(accepted.status_code, 303)
        self.assertNotIn(secret, accepted.get_data(as_text=True))
        self.assertEqual(self.ai_key_path.read_text(encoding="ascii"), secret)
        self.assertEqual(self.ai_key_path.stat().st_mode & 0o777, 0o600)

        consumed = self.client.get("/admin/ai-key")
        self.assertEqual(consumed.status_code, 200)
        self.assertIn("Одноразовое окно закрыто", consumed.get_data(as_text=True))
        self.assertNotIn(secret, consumed.get_data(as_text=True))

        replay = self.client.post(
            "/admin/ai-key",
            data={"csrf_token": self.csrf(), "api_key": "sk-proj-" + "B" * 48},
        )
        self.assertEqual(replay.status_code, 409)
        self.assertEqual(self.ai_key_path.read_text(encoding="ascii"), secret)

        with self.store.Session() as database_session:
            audit_rows = database_session.execute(
                select(AdminAuditLog).where(
                    AdminAuditLog.action.in_(
                        {"ai_key_enrolled", "ai_key_enrollment_rejected"}
                    )
                )
            ).scalars().all()
        self.assertEqual(len(audit_rows), 3)
        serialized_audit = "\n".join(row.details_json for row in audit_rows)
        self.assertNotIn(secret, serialized_audit)
        self.assertIn("fingerprint_sha256_12", serialized_audit)

    def test_remote_ai_key_enrollment_disabled_and_expired_fail_closed(self):
        disabled_app = create_app(
            {
                "TESTING": True,
                "SECRET_KEY": "another-test-session-secret-at-least-32",
                "AI_KEY_ENROLLMENT_ENABLED": "false",
            },
            database_store=self.store,
        )
        disabled_client = disabled_app.test_client()
        self.login(disabled_client)
        self.assertEqual(disabled_client.get("/admin/ai-key").status_code, 404)

        expired_path = self.local_config_dir / "expired-gate2.key"
        expired_app = create_app(
            {
                "TESTING": True,
                "SECRET_KEY": "expired-test-session-secret-at-least-32",
                "DATA_DIR": self.temp_dir.name,
                "AI_KEY_ENROLLMENT_ENABLED": "true",
                "AI_KEY_ENROLLMENT_PATH": str(expired_path),
                "AI_KEY_ENROLLMENT_EXPIRES_AT": (
                    datetime.now(timezone.utc) - timedelta(seconds=1)
                ).isoformat(),
            },
            database_store=self.store,
        )
        expired_client = expired_app.test_client()
        self.login(expired_client)
        expired = expired_client.get("/admin/ai-key")
        self.assertEqual(expired.status_code, 410)
        rejected = expired_client.post(
            "/admin/ai-key",
            data={
                "csrf_token": self.csrf(expired_client),
                "api_key": "sk-proj-" + "C" * 48,
            },
        )
        self.assertEqual(rejected.status_code, 410)
        self.assertFalse(expired_path.exists())

        with self.assertRaisesRegex(
            RuntimeError, "must stay in local-config"
        ):
            create_app(
                {
                    "TESTING": True,
                    "SECRET_KEY": "outside-test-session-secret-at-least-32",
                    "DATA_DIR": self.temp_dir.name,
                    "AI_KEY_ENROLLMENT_ENABLED": "true",
                    "AI_KEY_ENROLLMENT_PATH": str(
                        Path(self.temp_dir.name) / "outside.key"
                    ),
                    "AI_KEY_ENROLLMENT_EXPIRES_AT": (
                        datetime.now(timezone.utc) + timedelta(minutes=30)
                    ).isoformat(),
                },
                database_store=self.store,
            )

    def test_remote_groq_key_enrollment_is_separate_private_and_audited(self):
        secret = "gsk_" + "G" * 48
        self.login()

        page = self.client.get("/admin/groq-key")
        self.assertEqual(page.status_code, 200)
        self.assertIn("Groq project key", page.get_data(as_text=True))
        self.assertNotIn(secret, page.get_data(as_text=True))
        self.assertEqual(page.headers["Cache-Control"], "no-store")

        invalid = self.client.post(
            "/admin/groq-key",
            data={"csrf_token": self.csrf(), "api_key": "sk-not-groq"},
        )
        self.assertEqual(invalid.status_code, 400)
        self.assertFalse(self.groq_key_path.exists())

        accepted = self.client.post(
            "/admin/groq-key",
            data={"csrf_token": self.csrf(), "api_key": secret},
        )
        self.assertEqual(accepted.status_code, 303)
        self.assertEqual(self.groq_key_path.read_text(encoding="ascii"), secret)
        self.assertEqual(self.groq_key_path.stat().st_mode & 0o777, 0o600)
        self.assertFalse(self.ai_key_path.exists())

        replay = self.client.post(
            "/admin/groq-key",
            data={"csrf_token": self.csrf(), "api_key": "gsk_" + "R" * 48},
        )
        self.assertEqual(replay.status_code, 409)
        with self.store.Session() as database_session:
            rows = database_session.execute(
                select(AdminAuditLog).where(
                    AdminAuditLog.action.in_(
                        {"groq_key_enrolled", "groq_key_enrollment_rejected"}
                    )
                )
            ).scalars().all()
        serialized = "\n".join(row.details_json for row in rows)
        self.assertEqual(len(rows), 3)
        self.assertNotIn(secret, serialized)
        self.assertIn("fingerprint_sha256_12", serialized)

    def test_duplicate_login_post_keeps_authenticated_session(self):
        self.client.get("/admin/login")
        stale_csrf = self.csrf()
        credentials = {
            "csrf_token": stale_csrf,
            "username": "owner",
            "password": "test-password-123",
        }
        first_response = self.client.post("/admin/login", data=credentials)
        self.assertEqual(first_response.status_code, 302)

        duplicate_response = self.client.post("/admin/login", data=credentials)
        self.assertEqual(duplicate_response.status_code, 303)
        self.assertEqual(duplicate_response.headers["Location"], "/admin")
        dashboard = self.client.get(duplicate_response.headers["Location"])
        self.assertEqual(dashboard.status_code, 200)
        self.assertIn("Обзор продукта", dashboard.get_data(as_text=True))

    def test_state_changing_post_routes_reject_missing_csrf(self):

        user_id = 5400
        self.store.ensure_user_id(user_id)
        self.login()
        response = self.client.post(
            f"/admin/users/{user_id}/access",
            data={"status": "active"},
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            self.store.product_profile(user_id)["access_status"], "pending"
        )

    def test_short_session_secret_is_rejected(self):
        with self.assertRaisesRegex(RuntimeError, "at least 32"):
            create_app(
                {"TESTING": True, "SECRET_KEY": "too-short"},
                database_store=self.store,
            )

    def test_every_admin_tab_renders_on_empty_database(self):
        self.login()
        for tab in (
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
        ):
            with self.subTest(tab=tab):
                response = self.client.get(f"/admin?tab={tab}")
                self.assertEqual(response.status_code, 200)
                self.assertIn("MY DICTIONARY", response.get_data(as_text=True))

    def test_compact_navigation_has_six_primary_groups_and_context_tabs(self):
        self.login()
        page = self.client.get("/admin?tab=diagnostics").get_data(as_text=True)
        self.assertEqual(page.count('class="primary-nav-link'), 6)
        for label in (
            "Обзор",
            "Пользователи",
            "Продукт",
            "AI и голос",
            "Платежи",
            "Настройки",
        ):
            self.assertIn(label, page)
        for tab in ("profile", "safety", "diagnostics", "audit"):
            self.assertIn(f"/admin?tab={tab}", page)
        self.assertIn("nav-disclosure", page)
        self.assertIn('class="nav-disclosure" open', page)
        self.assertIn("/static/admin/admin.js", page)

        ai_page = self.client.get("/admin?tab=voice").get_data(as_text=True)
        self.assertIn("/admin?tab=ai", ai_page)
        self.assertIn("/admin?tab=voice", ai_page)

    def test_profile_settings_are_persisted_and_audited(self):
        self.login()
        profile = AdminStore(self.store).get_settings()
        profile["bot_start_text"] = "Привет, {name}! Новый старт."
        response = self.client.post(
            "/admin/settings/profile",
            data={"csrf_token": self.csrf(), **profile},
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            AdminStore(self.store).get_settings()["bot_start_text"],
            "Привет, {name}! Новый старт.",
        )
        with self.store.Session() as database_session:
            actions = database_session.execute(
                select(AdminAuditLog.action)
            ).scalars().all()
        self.assertIn("bot_profile_updated", actions)

    def test_credit_adjustment_is_transactional_and_has_ledger(self):
        self.login()
        self.store.ensure_user_id(5501)
        adjustment = {
            "csrf_token": self.csrf(),
            "action_id": "same-admin-action",
            "user_id": "5501",
            "delta": "12",
            "reason": "closed beta grant",
        }
        response = self.client.post(
            "/admin/credits",
            data=adjustment,
        )
        self.assertEqual(response.status_code, 302)
        replay = self.client.post(
            "/admin/credits",
            data={**adjustment, "csrf_token": self.csrf()},
        )
        self.assertEqual(replay.status_code, 302)
        with self.store.Session() as database_session:
            wallet = database_session.get(AIWallet, 5501)
            ledger = database_session.execute(select(BillingCreditLedger)).scalar_one()
            self.assertEqual(wallet.balance_credits, 12)
            self.assertEqual(ledger.delta, 12)
            self.assertEqual(ledger.balance_after, 12)

        rejected = self.client.post(
            "/admin/credits",
            data={
                "csrf_token": self.csrf(),
                "user_id": "5501",
                "delta": "-13",
                "reason": "invalid debit",
            },
        )
        self.assertEqual(rejected.status_code, 302)
        with self.store.Session() as database_session:
            self.assertEqual(
                database_session.get(AIWallet, 5501).balance_credits,
                12,
            )
            self.assertEqual(
                len(
                    database_session.execute(
                        select(BillingCreditLedger)
                    ).scalars().all()
                ),
                1,
            )

    def test_billing_product_draft_is_managed_with_csrf_and_audit(self):
        self.login()
        response = self.client.post(
            "/admin/billing/products",
            data={
                "csrf_token": self.csrf(),
                "product_id": "ai-starter",
                "title": "AI Starter",
                "description": "50 AI credits",
                "credits": "50",
                "price_xtr": "100",
                "estimated_cost_micro_usd": "0",
                "target_margin_bps": "0",
                "display_order": "10",
                "status": "draft",
            },
        )
        self.assertEqual(response.status_code, 302)
        page = self.client.get("/admin?tab=billing").get_data(as_text=True)
        self.assertIn("ai-starter", page)
        self.assertIn("draft", page)
        with self.store.Session() as session:
            actions = session.execute(select(AdminAuditLog.action)).scalars().all()
        self.assertIn("billing_product_created", actions)

    def test_billing_tab_shows_commercial_launch_contract_and_blockers(self):
        self.login()
        page = self.client.get("/admin?tab=billing").get_data(as_text=True)

        self.assertIn("Commercial Launch v3", page)
        self.assertIn("mydictionary-commercial-v3-2026-08-14", page)
        self.assertIn("Измеренный AI-вызов", page)
        self.assertIn("2 353 microUSD", page)
        self.assertIn("Реквизиты продавца", page)
        self.assertIn("Каталог БД", page)
        self.assertNotIn("must-not-appear", page)

    def test_credit_adjustment_rejects_unknown_user(self):
        with self.assertRaisesRegex(ValueError, "does not exist"):
            AdminStore(self.store).adjust_credits(
                999999,
                delta=3,
                reason="closed beta grant",
                actor="owner",
            )

    def test_pilot_access_changes_are_transactional_and_audited(self):
        user_id = 5502
        self.store.ensure_user_id(user_id)
        self.assertEqual(
            self.store.product_profile(user_id)["access_status"], "pending"
        )
        self.login()
        users_page = self.client.get("/admin?tab=users").get_data(as_text=True)
        self.assertIn(f"/admin/users/{user_id}/access", users_page)
        self.assertIn("Допустить", users_page)
        self.assertIn("Блокировать", users_page)
        approved = self.client.post(
            f"/admin/users/{user_id}/access",
            data={"csrf_token": self.csrf(), "status": "active"},
        )
        self.assertEqual(approved.status_code, 302)
        self.assertEqual(
            self.store.product_profile(user_id)["access_status"], "active"
        )
        with self.store.Session() as database_session:
            audit = database_session.execute(
                select(AdminAuditLog).where(
                    AdminAuditLog.action == "user_access_updated"
                )
            ).scalar_one()
            access_event = database_session.execute(
                select(AnalyticsEvent).where(
                    AnalyticsEvent.telegram_user_id == user_id,
                    AnalyticsEvent.event_name == "pilot_access_approved",
                )
            ).scalar_one()
            notification = database_session.execute(
                select(TelegramNotification).where(
                    TelegramNotification.telegram_user_id == user_id
                )
            ).scalar_one()
        self.assertEqual(audit.target_id, str(user_id))
        self.assertEqual(access_event.source, "admin")
        self.assertEqual(notification.status, "pending")
        self.assertEqual(
            json.loads(audit.details_json),
            {"previous": "pending", "current": "active"},
        )

        blocked = self.client.post(
            f"/admin/users/{user_id}/access",
            data={"csrf_token": self.csrf(), "status": "blocked"},
        )
        self.assertEqual(blocked.status_code, 302)
        self.assertEqual(
            self.store.product_profile(user_id)["access_status"], "blocked"
        )

        rejected = self.client.post(
            f"/admin/users/{user_id}/access",
            data={"csrf_token": self.csrf(), "status": "unknown"},
        )
        self.assertEqual(rejected.status_code, 302)
        self.assertEqual(
            self.store.product_profile(user_id)["access_status"], "blocked"
        )
        with self.store.Session() as database_session:
            audits = database_session.execute(
                select(AdminAuditLog).where(
                    AdminAuditLog.action == "user_access_updated"
                )
            ).scalars().all()
            events = database_session.execute(
                select(AnalyticsEvent.event_name).where(
                    AnalyticsEvent.telegram_user_id == user_id
                )
            ).scalars().all()
            notification = database_session.execute(
                select(TelegramNotification).where(
                    TelegramNotification.telegram_user_id == user_id
                )
            ).scalar_one()
        self.assertEqual(len(audits), 2)
        self.assertEqual(
            events,
            ["pilot_access_approved", "pilot_access_blocked"],
        )
        self.assertEqual(notification.status, "cancelled")

    def test_pilot_dashboard_tracks_funnel_retention_and_stage_filters(self):
        user_id = 5510
        now = datetime.now(timezone.utc)
        joined_at = now - timedelta(days=8, hours=2)
        self.store.ensure_user(
            SimpleNamespace(
                id=user_id,
                username="pilot_student",
                first_name="Pilot",
                last_name=None,
                language_code="ru",
            )
        )
        waitlist_id = self.store.record_event(
            user_id,
            "pilot_waitlist_joined",
            source="referral",
        )
        AdminStore(self.store).set_user_access_status(
            user_id,
            status="active",
            actor="owner",
        )
        onboarding_id = self.store.record_event(
            user_id, "onboarding_completed"
        )
        block_started_id = self.store.record_event(user_id, "block_started")
        block_completed_id = self.store.record_event(
            user_id, "block_completed"
        )
        d7_activity_id = self.store.record_event(
            user_id, "language_switched"
        )
        with self.store.Session.begin() as session:
            session.get(AnalyticsEvent, waitlist_id).occurred_at = joined_at
            session.get(AnalyticsEvent, onboarding_id).occurred_at = (
                joined_at + timedelta(hours=1)
            )
            session.get(AnalyticsEvent, block_started_id).occurred_at = (
                joined_at + timedelta(days=1, hours=1)
            )
            session.get(AnalyticsEvent, block_completed_id).occurred_at = (
                joined_at + timedelta(days=1, hours=2)
            )
            session.get(AnalyticsEvent, d7_activity_id).occurred_at = (
                joined_at + timedelta(days=7, hours=1)
            )
            user = session.get(User, user_id)
            user.acquisition_source = "referral"
            user.onboarding_completed_at = joined_at + timedelta(hours=1)
            progress = session.get(UserProgress, user_id)
            progress.active_lang = "fr"
            progress.sessions = 1

        admin_store = AdminStore(self.store)
        pilot = admin_store.pilot_overview(days=30)
        stages = {stage["event_name"]: stage for stage in pilot["stages"]}
        self.assertEqual(pilot["cohort"], 1)
        self.assertTrue(all(stage["users"] == 1 for stage in stages.values()))
        self.assertEqual(pilot["retention"]["d1"]["rate"], 100)
        self.assertEqual(pilot["retention"]["d7"]["rate"], 100)
        self.assertEqual(pilot["sources"], [{"source": "referral", "users": 1}])
        self.assertEqual(pilot["languages"], [{"language": "fr", "users": 1}])
        self.assertEqual(
            [user["id"] for user in admin_store.pilot_users(stage="engaged")],
            [user_id],
        )
        self.assertEqual(admin_store.pilot_users(stage="pending"), [])

        legacy_user_id = 5511
        self.store.ensure_user_id(legacy_user_id)
        self.store.record_event(legacy_user_id, "pilot_waitlist_joined")
        admin_store.set_user_access_status(
            legacy_user_id,
            status="active",
            actor="owner",
        )
        with self.store.Session.begin() as session:
            legacy_user = session.get(User, legacy_user_id)
            legacy_user.onboarding_completed_at = joined_at
            legacy_progress = session.get(UserProgress, legacy_user_id)
            legacy_progress.sessions = 9
        self.assertEqual(
            [
                user["id"]
                for user in admin_store.pilot_users(stage="first_block")
            ],
            [legacy_user_id],
        )

        self.login()
        page = self.client.get(
            "/admin?tab=pilot&pilot_stage=engaged"
        ).get_data(as_text=True)
        self.assertIn("Воронка когорты", page)
        self.assertIn("pilot_student", page)

    def test_administrator_access_cannot_be_restricted(self):
        user_id = 5503
        self.store.ensure_user(SimpleNamespace(id=user_id), role="admin")
        with self.assertRaisesRegex(ValueError, "Administrator"):
            AdminStore(self.store).set_user_access_status(
                user_id,
                status="blocked",
                actor="owner",
            )
        self.assertEqual(
            self.store.product_profile(user_id)["access_status"], "active"
        )

    def test_dashboard_and_user_table_aggregate_real_activity(self):
        self.store.ensure_user(
            SimpleNamespace(
                id=6001,
                username="aki",
                first_name="Аки",
                last_name=None,
                language_code="ru",
            )
        )
        progress = {
            "total_correct": 7,
            "total_wrong": 3,
            "sessions": 2,
            "xp": 90,
            "level": 2,
            "streak": 2,
            "streak_best": 4,
            "last_activity_date": "2026-08-04",
            "today_xp": 20,
            "today_date": "2026-08-04",
            "active_lang": "ja",
        }
        word = {
            "en": "猫",
            "ru": "кошка",
            "correct_count": 3,
            "wrong_count": 1,
            "last_seen": "2026-08-04T12:00:00+00:00",
            "interval": 4,
            "next_review": "2026-08-08T12:00:00+00:00",
        }
        self.store.save_learning_state(6001, progress, "ja", 0, word)
        request_id = self.store.reserve_ai_usage(
            6001,
            action="explain",
            provider="disabled-test-provider",
            model="test-model",
            credits=2,
            initial_credits=5,
            context_fingerprint="0" * 64,
        )
        self.store.complete_ai_usage(
            request_id,
            billed_credits=1,
            provider_response_id=None,
            model="test-model",
            usage={"input_tokens": 80, "output_tokens": 40, "total_tokens": 120},
            cost_micro_usd=240,
            latency_ms=180,
        )

        admin_store = AdminStore(self.store)
        dashboard = admin_store.dashboard()
        self.assertEqual(dashboard["users"], 1)
        self.assertEqual(dashboard["sessions"], 2)
        self.assertEqual(dashboard["learned_words"], 1)
        self.assertEqual(dashboard["ai_requests"], 1)
        self.assertEqual(dashboard["ai_tokens"], 120)
        self.assertEqual(dashboard["credits_spent"], 1)
        self.assertEqual(dashboard["access"]["pending"], 1)

        users = admin_store.users(search="aki")
        self.assertEqual(len(users), 1)
        self.assertEqual(users[0]["active_lang"], "ja")
        self.assertEqual(users[0]["learned_words"], 1)
        self.assertEqual(users[0]["ai_requests"], 1)
        self.assertEqual(users[0]["accuracy"], 70)
        self.assertEqual(users[0]["access_status"], "pending")

        usage_columns = set(admin_store.ai_usage_export()[0])
        self.assertNotIn("prompt", usage_columns)
        self.assertNotIn("response", usage_columns)

    def test_csv_exports_require_auth_and_record_audit(self):
        anonymous = self.client.get("/admin/export/users.csv")
        self.assertEqual(anonymous.status_code, 302)
        self.login()
        exported = self.client.get("/admin/export/users.csv")
        self.assertEqual(exported.status_code, 200)
        self.assertEqual(exported.mimetype, "text/csv")
        with self.store.Session() as database_session:
            actions = database_session.execute(
                select(AdminAuditLog.action)
            ).scalars().all()
        self.assertIn("csv_export_downloaded", actions)

    def test_product_funnel_renders_and_exports_privacy_safe_events(self):
        self.store.record_event(7001, "start_received", source="direct")
        self.store.record_event(
            7001,
            "onboarding_completed",
            properties={"pack_id": "ja-basics-100", "language": "ja"},
        )
        self.store.record_event(7001, "buy_opened", source="command")
        self.store.ensure_user(SimpleNamespace(id=7002), role="admin")
        self.store.record_event(7002, "start_received", source="direct")
        funnel = AdminStore(self.store).product_funnel(days=30)
        steps = {step["event_name"]: step for step in funnel["steps"]}
        self.assertEqual(steps["start_received"]["users"], 1)
        self.assertEqual(steps["start_received"]["events"], 1)
        self.assertEqual(steps["buy_opened"]["users"], 1)
        self.assertEqual(steps["onboarding_completed"]["conversion"], 100)
        self.assertEqual(steps["invoice_created"]["source"], "ledger")
        self.assertEqual(funnel["commercial"]["net_xtr"], 0)

        self.login()
        response = self.client.get("/admin?tab=funnel")
        self.assertEqual(response.status_code, 200)
        self.assertIn("Продуктовая воронка", response.get_data(as_text=True))
        exported = self.client.get("/admin/export/analytics-events.csv")
        self.assertEqual(exported.status_code, 200)
        body = exported.get_data(as_text=True)
        self.assertIn("onboarding_completed", body)
        self.assertNotIn("prompt", body)

    def test_commercial_funnel_uses_durable_orders_payments_and_ai_usage(self):
        user_id = 7010
        self.store.ensure_user_id(user_id)
        self.store.grant_consent(
            user_id,
            consent_type="billing_terms",
            document_version="funnel-1",
            source="test",
        )
        settings = BillingSettings(
            enabled=True,
            payload_secret="s" * 40,
            support_contact="@support",
            terms_text="Funnel terms",
            terms_version="funnel-1",
            net_micro_usd_per_xtr=1000,
            terms_approved=True,
            economics_reviewed_on=datetime.now(timezone.utc).date().isoformat(),
        )
        admin = AdminStore(self.store, settings)
        admin.upsert_billing_product(
            product_id="funnel-pack",
            title="Funnel pack",
            description="Test credits",
            credits=5,
            price_xtr=10,
            status="active",
            estimated_cost_micro_usd=100,
            target_margin_bps=100,
            display_order=1,
            actor="test",
        )
        billing = BillingService(self.store, settings)
        for index in range(2):
            order = billing.create_order(
                user_id=user_id, product_id="funnel-pack"
            )
            billing.fulfill_successful_payment(
                user_id=user_id,
                payload=order.payload,
                currency="XTR",
                total_amount=10,
                telegram_payment_charge_id=f"funnel-charge-{index}",
            )
        for event_name in (
            "ai_paywall_shown",
            "billing_package_selected",
            "billing_invoice_created",
            "stars_payment_completed",
        ):
            self.store.record_event(user_id, event_name, source="telegram")
        with self.store.Session.begin() as session:
            session.add(
                AIUsage(
                    request_id="funnel-ai-request",
                    telegram_user_id=user_id,
                    action="block_tutor",
                    provider="test",
                    model="test",
                    status="completed",
                    context_fingerprint="f" * 64,
                    reserved_credits=1,
                    billed_credits=1,
                    cost_micro_usd=1000,
                )
            )

        funnel = admin.product_funnel(days=30)
        steps = {step["event_name"]: step for step in funnel["steps"]}
        self.assertEqual(steps["invoice_created"]["events"], 2)
        self.assertEqual(steps["ai_paywall_shown"]["events"], 1)
        self.assertEqual(steps["billing_package_selected"]["events"], 1)
        self.assertEqual(steps["billing_invoice_created"]["events"], 1)
        self.assertEqual(steps["stars_payment_completed"]["users"], 1)
        self.assertEqual(steps["ai_request_completed"]["users"], 1)
        self.assertEqual(steps["repeat_purchase"]["users"], 1)
        self.assertEqual(funnel["commercial"]["gross_xtr"], 20)
        self.assertEqual(funnel["commercial"]["net_xtr"], 20)
        self.assertEqual(funnel["commercial"]["ai_provider_cost_micro_usd"], 1000)
        self.assertEqual(
            funnel["commercial"]["estimated_contribution_micro_usd"], 19000
        )
        self.assertEqual(
            funnel["commercial"]["estimated_contribution_margin_bps"], 9500
        )

    def test_health_exposes_no_internal_configuration(self):
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json, {"status": "ok"})

        stale_at = datetime.now(timezone.utc) - timedelta(minutes=2)
        BotHeartbeat(
            self.heartbeat_path,
            release_sha="test-release",
            access_mode="pilot",
            now=lambda: stale_at,
        ).mark_ready()
        unavailable = self.client.get("/health")
        self.assertEqual(unavailable.status_code, 503)
        self.assertEqual(unavailable.json, {"status": "unavailable"})

    def test_ai_breaker_diagnostics_reset_and_journal_guard(self):
        journal_path = Path(self.temp_dir.name) / "ai-metering.jsonl"
        self.store.open_ai_breaker(reason="returned_model_mismatch")
        self.login()
        with patch.dict(
            os.environ,
            {"AI_METERING_JOURNAL_PATH": str(journal_path)},
        ):
            diagnostics = self.client.get("/admin?tab=diagnostics")
            body = diagnostics.get_data(as_text=True)
            self.assertEqual(diagnostics.status_code, 200)
            self.assertIn("returned_model_mismatch", body)
            self.assertIn("Сброс AI breaker", body)

            rejected = self.client.post(
                "/admin/ai/breaker/reset",
                data={"reason": "missing csrf"},
            )
            self.assertEqual(rejected.status_code, 400)
            self.assertTrue(self.store.ai_budget_status()["breaker_open"])

            reset = self.client.post(
                "/admin/ai/breaker/reset",
                data={
                    "csrf_token": self.csrf(),
                    "reason": "verified provider telemetry",
                },
                follow_redirects=True,
            )
            self.assertEqual(reset.status_code, 200)
            self.assertIn("AI breaker сброшен", reset.get_data(as_text=True))
            self.assertFalse(self.store.ai_budget_status()["breaker_open"])

            self.store.open_ai_breaker(reason="storage_failure")
            AIMeteringJournal(journal_path).append(
                {"request_id": "pending-test", "error_code": "storage_failure"}
            )
            blocked = self.client.post(
                "/admin/ai/breaker/reset",
                data={
                    "csrf_token": self.csrf(),
                    "reason": "must not reset",
                },
                follow_redirects=True,
            )
            self.assertIn(
                "metering journal не reconciled",
                blocked.get_data(as_text=True),
            )
            self.assertTrue(self.store.ai_budget_status()["breaker_open"])

        with self.store.Session() as database_session:
            resets = database_session.execute(
                select(AdminAuditLog).where(
                    AdminAuditLog.action == "ai_breaker_reset"
                )
            ).scalars().all()
        self.assertEqual(len(resets), 1)


class LoginLimiterTest(unittest.TestCase):
    def test_failures_block_source_until_success_resets_it(self):
        limiter = LoginLimiter(attempts=2, window_seconds=300)
        self.assertTrue(limiter.allowed("127.0.0.1"))
        limiter.failure("127.0.0.1")
        self.assertTrue(limiter.allowed("127.0.0.1"))
        limiter.failure("127.0.0.1")
        self.assertFalse(limiter.allowed("127.0.0.1"))
        limiter.success("127.0.0.1")
        self.assertTrue(limiter.allowed("127.0.0.1"))


if __name__ == "__main__":
    unittest.main()
