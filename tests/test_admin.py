import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from sqlalchemy import select

from mydictionary.admin import LoginLimiter, create_app
from mydictionary.admin_store import AdminStore
from mydictionary.storage import (
    AIAllowance,
    AICreditLedger,
    AdminAuditLog,
    DatabaseStore,
)


class AdminConsoleTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory(prefix="mydictionary-admin-")
        database_path = Path(self.temp_dir.name) / "admin.db"
        self.store = DatabaseStore(f"sqlite:///{database_path}")
        self.app = create_app(
            {
                "TESTING": True,
                "SECRET_KEY": "test-session-secret-with-at-least-32-chars",
                "ADMIN_USERNAME": "owner",
                "ADMIN_PASSWORD": "test-password-123",
            },
            database_store=self.store,
        )
        self.client = self.app.test_client()

    def tearDown(self):
        self.store.close()
        self.temp_dir.cleanup()

    def csrf(self):
        with self.client.session_transaction() as browser_session:
            return browser_session["csrf_token"]

    def login(self):
        self.client.get("/admin/login")
        response = self.client.post(
            "/admin/login",
            data={
                "csrf_token": self.csrf(),
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

    def test_all_post_routes_reject_missing_csrf(self):
        self.client.get("/admin/login")
        response = self.client.post(
            "/admin/login",
            data={"username": "owner", "password": "test-password-123"},
        )
        self.assertEqual(response.status_code, 400)

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
            "funnel",
            "learning",
            "ai",
            "content",
            "profile",
            "diagnostics",
            "audit",
        ):
            with self.subTest(tab=tab):
                response = self.client.get(f"/admin?tab={tab}")
                self.assertEqual(response.status_code, 200)
                self.assertIn("MY DICTIONARY", response.get_data(as_text=True))

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
        response = self.client.post(
            "/admin/credits",
            data={
                "csrf_token": self.csrf(),
                "user_id": "5501",
                "delta": "12",
                "reason": "closed beta grant",
            },
        )
        self.assertEqual(response.status_code, 302)
        with self.store.Session() as database_session:
            allowance = database_session.get(AIAllowance, 5501)
            ledger = database_session.execute(select(AICreditLedger)).scalar_one()
            self.assertEqual(allowance.available_credits, 12)
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
                database_session.get(AIAllowance, 5501).available_credits,
                12,
            )
            self.assertEqual(
                len(database_session.execute(select(AICreditLedger)).scalars().all()),
                1,
            )

    def test_credit_adjustment_rejects_unknown_user(self):
        with self.assertRaisesRegex(ValueError, "does not exist"):
            AdminStore(self.store).adjust_credits(
                999999,
                delta=3,
                reason="closed beta grant",
                actor="owner",
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

        users = admin_store.users(search="aki")
        self.assertEqual(len(users), 1)
        self.assertEqual(users[0]["active_lang"], "ja")
        self.assertEqual(users[0]["learned_words"], 1)
        self.assertEqual(users[0]["ai_requests"], 1)
        self.assertEqual(users[0]["accuracy"], 70)

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
        self.store.record_event(7001, "onboarding_started")
        self.store.record_event(
            7001,
            "onboarding_completed",
            properties={"pack_id": "ja-basics-100", "language": "ja"},
        )
        self.store.ensure_user(SimpleNamespace(id=7002), role="admin")
        self.store.record_event(7002, "start_received", source="direct")
        funnel = AdminStore(self.store).product_funnel(days=30)
        self.assertEqual(funnel["steps"][0]["users"], 1)
        self.assertEqual(funnel["steps"][0]["events"], 1)
        self.assertEqual(funnel["steps"][2]["conversion"], 100)

        self.login()
        response = self.client.get("/admin?tab=funnel")
        self.assertEqual(response.status_code, 200)
        self.assertIn("Продуктовая воронка", response.get_data(as_text=True))
        exported = self.client.get("/admin/export/analytics-events.csv")
        self.assertEqual(exported.status_code, 200)
        body = exported.get_data(as_text=True)
        self.assertIn("onboarding_completed", body)
        self.assertNotIn("prompt", body)

    def test_health_exposes_no_internal_configuration(self):
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json, {"status": "ok"})


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
