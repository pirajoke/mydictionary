from __future__ import annotations

import os
from pathlib import Path
import re
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from sqlalchemy import delete, select

from mydictionary.admin import create_app
from mydictionary.admin_store import AdminStore
from mydictionary.storage import (
    BillingCreditLedger,
    DatabaseStore,
    ReferralAttribution,
    User,
)


INVITER_ID = 880_001
BOT_USERNAME = "mydictionary_admin_test_bot"
PUBLIC_URL = "https://admin-referral.example.test/miniapp"
TOKEN_FILE = "/protected/runtime/bot-token"


def telegram_user(user_id: int) -> SimpleNamespace:
    return SimpleNamespace(
        id=int(user_id),
        username=f"private_{user_id}",
        first_name="Private",
        last_name="Learner",
        language_code="ru",
    )


class AdminReferralOperationsV1Test(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="admin-referral-v1-")
        root = Path(self.temporary.name)
        self.store = DatabaseStore(f"sqlite:///{root / 'admin.sqlite3'}")
        self.store.ensure_user(telegram_user(INVITER_ID))
        with self.store.Session.begin() as session:
            inviter = session.get(User, INVITER_ID)
            inviter.access_status = "active"
            inviter.privacy_status = "active"
        self.app = create_app(
            {
                "TESTING": True,
                "SECRET_KEY": "r" * 40,
                "ADMIN_USERNAME": "owner",
                "ADMIN_PASSWORD": "strong-test-password",
                "DATA_DIR": str(root),
                "MINIAPP_ENABLED": True,
                "MINIAPP_PUBLIC_URL": PUBLIC_URL,
                "MINIAPP_BOT_USERNAME": BOT_USERNAME,
                "MINIAPP_AUTH_MAX_AGE_SECONDS": 300,
                "BOT_TOKEN_FILE": TOKEN_FILE,
                "AI_INITIAL_CREDITS": 40,
                "TELEGRAM_STARS_ENABLED": False,
            },
            database_store=self.store,
        )
        self.client = self.app.test_client()

    def tearDown(self) -> None:
        self.store.close()
        self.temporary.cleanup()

    def csrf(self) -> str:
        with self.client.session_transaction() as browser_session:
            return str(browser_session["csrf_token"])

    def login(self) -> None:
        self.client.get("/admin/login")
        response = self.client.post(
            "/admin/login",
            data={
                "csrf_token": self.csrf(),
                "username": "owner",
                "password": "strong-test-password",
            },
        )
        self.assertEqual(response.status_code, 302)

    def invite(self, invitee_id: int, *, activate: bool) -> str:
        code = self.store.issue_referral_code(INVITER_ID)
        captured = self.store.capture_referral_attribution(
            telegram_user(invitee_id), code
        )
        self.assertTrue(captured)
        if activate:
            self.store.update_product_profile(
                invitee_id,
                complete_onboarding=True,
                initial_credits=40,
            )
        return code

    def test_ac1_referrals_is_an_authenticated_users_tab(self):
        anonymous = self.client.get("/admin?tab=referrals")
        self.assertEqual(anonymous.status_code, 302)
        self.assertEqual(anonymous.headers["Location"], "/admin/login")

        self.login()
        page = self.client.get("/admin?tab=referrals")
        self.assertEqual(page.status_code, 200)
        body = page.get_data(as_text=True)
        self.assertIn("Рефералы", body)
        self.assertIn("Реферальная программа", body)
        self.assertIn("tab=referrals", body)

        fallback = self.client.get("/admin?tab=not-a-real-tab")
        self.assertIn("Обзор продукта", fallback.get_data(as_text=True))

    def test_ac2_ac4_ec1_empty_overview_is_numeric_and_uses_canonical_economics(self):
        overview = AdminStore(self.store).referral_overview(days=30)
        self.assertEqual(
            overview["all_time"],
            {
                "issued_codes": 0,
                "invited": 0,
                "pending": 0,
                "activated": 0,
                "rewarded": 0,
                "awarded_credits": 0,
                "conversion_percent": 0.0,
            },
        )
        self.assertEqual(overview["economics"], {"reward_credits": 5, "reward_cap": 10})
        self.assertEqual(overview["accounting"]["ledger_entries"], 0)
        self.assertEqual(overview["accounting"]["ledger_credits"], 0)
        self.assertTrue(overview["accounting"]["reconciled"])

    def test_ac2_ac4_ac5_ec2_cap_and_ledger_are_aggregated_without_graph_data(self):
        private_codes = {
            self.invite(881_000 + offset, activate=True)
            for offset in range(11)
        }
        self.assertEqual(len(private_codes), 1)

        overview = AdminStore(self.store).referral_overview(days=30)
        self.assertEqual(overview["all_time"]["issued_codes"], 1)
        self.assertEqual(overview["all_time"]["invited"], 11)
        self.assertEqual(overview["all_time"]["pending"], 0)
        self.assertEqual(overview["all_time"]["activated"], 11)
        self.assertEqual(overview["all_time"]["rewarded"], 10)
        self.assertEqual(overview["all_time"]["awarded_credits"], 50)
        self.assertEqual(overview["all_time"]["conversion_percent"], 100.0)
        self.assertEqual(overview["accounting"]["ledger_entries"], 10)
        self.assertEqual(overview["accounting"]["ledger_credits"], 50)
        self.assertTrue(overview["accounting"]["reconciled"])
        serialized = repr(overview)
        self.assertNotIn(str(INVITER_ID), serialized)
        for code in private_codes:
            self.assertNotIn(code, serialized)

    def test_ac3_err2_range_is_bounded_and_trend_includes_zero_days(self):
        self.invite(882_001, activate=True)
        self.invite(882_002, activate=False)
        admin_store = AdminStore(self.store)

        for days in (7, 30, 90):
            with self.subTest(days=days):
                overview = admin_store.referral_overview(days=days)
                self.assertEqual(overview["days"], days)
                self.assertEqual(len(overview["trend"]), days)
                self.assertEqual(
                    set(overview["trend"][0]),
                    {"date", "invited", "activated", "awarded_credits"},
                )
                self.assertEqual(sum(row["invited"] for row in overview["trend"]), 2)
                self.assertEqual(sum(row["activated"] for row in overview["trend"]), 1)
                self.assertTrue(any(row["invited"] == 0 for row in overview["trend"][:-1]))

        for invalid in (0, 8, 365):
            with self.subTest(invalid=invalid):
                with self.assertRaises(ValueError):
                    admin_store.referral_overview(days=invalid)

        self.login()
        for invalid_query in ("8", "all", ""):
            response = self.client.get(f"/admin?tab=referrals&days={invalid_query}")
            self.assertEqual(response.status_code, 200)
            self.assertIn("30 дней", response.get_data(as_text=True))

    def test_ac5_accounting_mismatch_is_visible(self):
        self.invite(883_001, activate=True)
        with self.store.Session.begin() as session:
            session.execute(
                delete(BillingCreditLedger).where(
                    BillingCreditLedger.entry_type == "referral_reward"
                )
            )

        accounting = AdminStore(self.store).referral_overview(days=30)["accounting"]
        self.assertEqual(accounting["attributed_credits"], 5)
        self.assertEqual(accounting["ledger_credits"], 0)
        self.assertFalse(accounting["reconciled"])

        self.login()
        body = self.client.get("/admin?tab=referrals").get_data(as_text=True)
        self.assertIn("Расхождение", body)
        self.assertNotIn(str(INVITER_ID), body)

    def test_ac6_readiness_is_useful_but_does_not_render_runtime_or_graph_secrets(self):
        code = self.invite(884_001, activate=False)
        self.login()
        body = self.client.get("/admin?tab=referrals").get_data(as_text=True)
        for label in ("Mini App", "Settings Hub", "/invite", "Имя бота"):
            self.assertIn(label, body)
        for private_value in (
            PUBLIC_URL,
            BOT_USERNAME,
            TOKEN_FILE,
            code,
            str(INVITER_ID),
            "private_884001",
        ):
            self.assertNotIn(private_value, body)
        self.assertNotIn("ref_", body)

    def test_ac7_diagnostics_uses_current_head_and_reports_recent_runtime_surfaces(self):
        self.login()
        with patch.dict(
            os.environ,
            {
                "MIRROR_MEMORY_ENABLED": "true",
                "MIRROR_DIALOGUE_RETENTION_DAYS": "7",
                "AI_CONSENT_VERSION": "ai-processing-2026-08-09",
                "AI_PROCESSING_NOTICE": (
                    "Dialogue history is retained for 7 days for contextual learning."
                ),
                "MIRROR_VOICE_OUTPUT_ENABLED": "false",
            },
            clear=False,
        ):
            response = self.client.get("/admin?tab=diagnostics")
        self.assertEqual(response.status_code, 200)
        body = re.sub(r"\s+", " ", response.get_data(as_text=True))
        self.assertRegex(
            body,
            r"Alembic revision</dt><dd>0019_referral_program_v1</dd>"
            r"<span class=\"readiness ok\">ready</span>",
        )
        for label in (
            "Mini App / Settings Hub",
            "Команда /invite",
            "Mirror memory",
            "Mirror retention",
            "Mirror voice output",
        ):
            self.assertIn(label, body)

    def test_err1_invalid_mirror_runtime_is_fail_closed_in_diagnostics(self):
        self.login()
        with patch.dict(
            os.environ,
            {
                "MIRROR_MEMORY_ENABLED": "sometimes",
                "MIRROR_DIALOGUE_RETENTION_DAYS": "0",
                "MIRROR_VOICE_OUTPUT_ENABLED": "sometimes",
            },
            clear=False,
        ):
            response = self.client.get("/admin?tab=diagnostics")
        self.assertEqual(response.status_code, 200)
        body = response.get_data(as_text=True)
        self.assertIn("Mirror memory", body)
        self.assertIn("invalid", body)
        self.assertNotIn("sometimes", body)

    def test_ac8_adaptation_map_is_explicit_and_referrals_stay_read_only(self):
        self.login()
        body = self.client.get("/admin?tab=referrals").get_data(as_text=True)
        for covered_surface in (
            "Stars и платежи",
            "Mirror",
            "Языки и контент",
            "Settings Hub",
            "навигация ученика",
        ):
            self.assertIn(covered_surface, body)
        self.assertNotIn("Ручное начисление", body)
        self.assertNotIn("Создать приглашение", body)
        self.assertNotIn("Отозвать код", body)


if __name__ == "__main__":
    unittest.main()
