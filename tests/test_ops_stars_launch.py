import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import event

from mydictionary.admin_store import AdminStore
from mydictionary.stars_launch import StarsLaunchEnrollmentSettings
from mydictionary.storage import DatabaseStore
from ops import mydictionary_commercial_launch as commercial_launch
from ops import mydictionary_economics as economics
from ops import mydictionary_stars_launch as stars_launch_cli


VALID_TEST_TOKEN = "123456789:" + "T" * 35
TERMS_TEXT = "AI credits are delivered immediately after a successful Stars payment."


def profile_form() -> dict[str, str]:
    return {
        "seller_legal_name": "Example Learning SAS",
        "seller_address": "10 Example Street, 75001 Paris, France",
        "seller_email": "billing@example.test",
        "seller_phone": "+33102030405",
        "support_contact": "@example_support",
        "terms_text": TERMS_TEXT,
        "terms_version": "stars-prod-v1",
        "terms_approved": "on",
    }


def write_receipt(path: Path, *, completed_at: datetime) -> None:
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "environment": "telegram_test",
                "completed_at": completed_at.isoformat(),
                "scenarios": {
                    "purchase": "passed",
                    "duplicate_delivery": "passed",
                    "restart_recovery": "passed",
                    "reconciliation": "passed",
                    "refund": "passed",
                },
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    os.chmod(path, 0o600)


class StarsLaunchOperatorTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory(prefix="stars-launch-ops-")
        self.root = Path(self.temp_dir.name)
        os.chmod(self.root, 0o700)
        self.now = datetime(2026, 8, 15, 12, 0, tzinfo=timezone.utc)
        self.profile_path = self.root / "profile.json"
        self.credentials_path = self.root / "credentials.json"
        self.receipt_path = self.root / "receipt.json"
        enrollment = StarsLaunchEnrollmentSettings.from_mapping(
            {
                "STARS_LAUNCH_ENROLLMENT_ENABLED": "true",
                "STARS_LAUNCH_PROFILE_PATH": str(self.profile_path),
                "STARS_TEST_CREDENTIALS_PATH": str(self.credentials_path),
                "STARS_LAUNCH_ENROLLMENT_EXPIRES_AT": (
                    self.now + timedelta(minutes=30)
                ).isoformat(),
            },
            now=self.now,
            allowed_directory=self.root,
        )
        enrollment.enroll_profile(profile_form(), now=self.now)
        enrollment.enroll_test_credentials(
            {"bot_token": VALID_TEST_TOKEN, "test_user_id": "7001"},
            now=self.now,
        )
        write_receipt(self.receipt_path, completed_at=self.now)
        self.store = DatabaseStore(f"sqlite:///{self.root / 'launch.db'}")
        commercial_launch.seed_products(
            self.store,
            economics.load_snapshot(),
            actor="launch-test-seed",
        )
        self.values = {
            "BILLING_LAUNCH_PROFILE_FILE": str(self.profile_path),
            "TELEGRAM_TEST_CREDENTIALS_FILE": str(self.credentials_path),
            "STARS_TEST_RECEIPT_FILE": str(self.receipt_path),
            "TELEGRAM_STARS_ENABLED": "false",
            "BILLING_NET_MICRO_USD_PER_XTR": "10000",
            "BILLING_ECONOMICS_REVIEWED_ON": "2026-08-15",
            "BILLING_ECONOMICS_MAX_AGE_DAYS": "30",
        }

    def tearDown(self):
        self.store.close()
        self.temp_dir.cleanup()

    def statuses(self) -> dict[str, str]:
        return {
            row["product_id"]: row["status"]
            for row in AdminStore(self.store).billing_products()
        }

    def test_activation_is_explicit_one_time_only_and_idempotent(self):
        with self.assertRaisesRegex(RuntimeError, "--execute"):
            stars_launch_cli.activate_products(
                self.store,
                self.values,
                actor="launch-test",
                execute=False,
                now=self.now,
            )
        self.assertTrue(all(value == "draft" for value in self.statuses().values()))

        first = stars_launch_cli.activate_products(
            self.store,
            self.values,
            actor="launch-test",
            execute=True,
            now=self.now,
        )
        second = stars_launch_cli.activate_products(
            self.store,
            self.values,
            actor="launch-test",
            execute=True,
            now=self.now,
        )

        self.assertEqual(first, {"activated": 3, "unchanged": 0})
        self.assertEqual(second, {"activated": 0, "unchanged": 3})
        self.assertEqual(
            self.statuses(),
            {
                "ai-mini": "active",
                "ai-starter": "active",
                "ai-value": "active",
                "ai-monthly": "draft",
            },
        )
        self.assertEqual(self.values["TELEGRAM_STARS_ENABLED"], "false")

    def test_missing_gate_and_catalog_drift_block_every_write(self):
        self.receipt_path.unlink()
        blocked = stars_launch_cli.check_readiness(
            self.store, self.values, now=self.now
        )
        self.assertFalse(blocked["ready"])
        self.assertIn("test_receipt", blocked["blockers"])
        with self.assertRaisesRegex(RuntimeError, "not ready"):
            stars_launch_cli.activate_products(
                self.store,
                self.values,
                actor="launch-test",
                execute=True,
                now=self.now,
            )
        self.assertTrue(all(value == "draft" for value in self.statuses().values()))

        write_receipt(self.receipt_path, completed_at=self.now)
        admin = AdminStore(self.store)
        product = admin.billing_products(product_id="ai-mini")[0]
        admin.upsert_billing_product(
            **{
                key: product[key]
                for key in (
                    "product_id",
                    "title",
                    "description",
                    "credits",
                    "status",
                    "estimated_cost_micro_usd",
                    "target_margin_bps",
                    "display_order",
                    "billing_mode",
                    "subscription_period_seconds",
                )
            },
            price_xtr=70,
            actor="drift-test",
        )
        drift = stars_launch_cli.check_readiness(
            self.store, self.values, now=self.now
        )
        self.assertFalse(drift["ready"])
        self.assertIn("catalog", drift["blockers"])

    def test_cli_output_contract_is_safe_and_activation_defaults_to_dry_run(self):
        parsed = stars_launch_cli.parser().parse_args(["activate-products"])
        self.assertFalse(parsed.execute)
        report = stars_launch_cli.check_readiness(
            self.store, self.values, now=self.now
        )
        rendered = json.dumps(report, sort_keys=True)
        for forbidden in (
            VALID_TEST_TOKEN,
            "7001",
            "Example Learning",
            str(self.root),
            "sqlite",
        ):
            self.assertNotIn(forbidden, rendered)

    def test_activation_rolls_back_all_products_when_commit_fails(self):
        def fail_commit(_session):
            raise RuntimeError("simulated commit failure")

        event.listen(self.store.Session, "before_commit", fail_commit)
        try:
            with self.assertRaisesRegex(RuntimeError, "simulated commit failure"):
                stars_launch_cli.activate_products(
                    self.store,
                    self.values,
                    actor="launch-test",
                    execute=True,
                    now=self.now,
                )
        finally:
            event.remove(self.store.Session, "before_commit", fail_commit)

        self.assertTrue(all(value == "draft" for value in self.statuses().values()))


if __name__ == "__main__":
    unittest.main()
