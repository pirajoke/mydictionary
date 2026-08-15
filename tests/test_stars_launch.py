import hashlib
import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from mydictionary.billing import BillingConfigurationError, BillingSettings
from mydictionary.stars_launch import (
    StarsLaunchEnrollmentSettings,
    StarsLaunchError,
    load_billing_launch_profile,
    stars_launch_enrollment_overview,
    stars_launch_readiness,
    validate_stars_test_receipt,
)
from ops import mydictionary_commercial_launch as commercial_launch
from ops import mydictionary_economics as economics


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


class StarsLaunchContractTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory(prefix="stars-launch-")
        self.root = Path(self.temp_dir.name)
        os.chmod(self.root, 0o700)
        self.profile_path = self.root / "billing-launch-profile.json"
        self.credentials_path = self.root / "telegram-test-credentials.json"
        self.receipt_path = self.root / "telegram-test-receipt.json"
        self.now = datetime(2026, 8, 15, 12, 0, tzinfo=timezone.utc)
        self.settings = StarsLaunchEnrollmentSettings.from_mapping(
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

    def tearDown(self):
        self.temp_dir.cleanup()

    def enroll_all(self) -> None:
        self.settings.enroll_profile(profile_form(), now=self.now)
        self.settings.enroll_test_credentials(
            {"bot_token": VALID_TEST_TOKEN, "test_user_id": "7001"},
            now=self.now,
        )

    def runtime_values(self) -> dict[str, str]:
        return {
            "BILLING_LAUNCH_PROFILE_FILE": str(self.profile_path),
            "TELEGRAM_TEST_CREDENTIALS_FILE": str(self.credentials_path),
            "STARS_TEST_RECEIPT_FILE": str(self.receipt_path),
            "TELEGRAM_STARS_ENABLED": "false",
            "BILLING_NET_MICRO_USD_PER_XTR": "10000",
            "BILLING_ECONOMICS_REVIEWED_ON": "2026-08-15",
            "BILLING_ECONOMICS_MAX_AGE_DAYS": "30",
        }

    def test_one_time_enrollment_writes_separate_owner_only_files(self):
        profile_fingerprint = self.settings.enroll_profile(
            profile_form(), now=self.now
        )
        credential_fingerprint = self.settings.enroll_test_credentials(
            {"bot_token": VALID_TEST_TOKEN, "test_user_id": "7001"},
            now=self.now,
        )

        self.assertRegex(profile_fingerprint, r"^[a-f0-9]{12}$")
        self.assertRegex(credential_fingerprint, r"^[a-f0-9]{12}$")
        self.assertEqual(self.profile_path.stat().st_mode & 0o777, 0o600)
        self.assertEqual(self.credentials_path.stat().st_mode & 0o777, 0o600)
        profile = json.loads(self.profile_path.read_text(encoding="utf-8"))
        credentials = json.loads(
            self.credentials_path.read_text(encoding="utf-8")
        )
        self.assertEqual(profile["schema_version"], 1)
        self.assertEqual(profile["terms"]["text"], TERMS_TEXT)
        self.assertEqual(
            profile["terms"]["sha256"],
            hashlib.sha256(TERMS_TEXT.encode("utf-8")).hexdigest(),
        )
        self.assertTrue(profile["terms"]["approved"])
        self.assertGreaterEqual(len(profile["payload_secret"]), 43)
        self.assertNotIn(profile["payload_secret"], profile_form().values())
        self.assertEqual(
            credentials,
            {"bot_token": VALID_TEST_TOKEN, "test_user_id": 7001},
        )
        self.assertEqual(
            self.settings.statuses(now=self.now),
            {"profile": "consumed", "test_credentials": "consumed"},
        )
        with self.assertRaisesRegex(StarsLaunchError, "consumed"):
            self.settings.enroll_profile(profile_form(), now=self.now)

    def test_enrollment_rejects_invalid_data_expiry_and_unsafe_destinations(self):
        invalid = profile_form()
        invalid["terms_approved"] = ""
        with self.assertRaisesRegex(StarsLaunchError, "approval"):
            self.settings.enroll_profile(invalid, now=self.now)
        self.assertFalse(self.profile_path.exists())

        with self.assertRaisesRegex(StarsLaunchError, "one hour"):
            StarsLaunchEnrollmentSettings.from_mapping(
                {
                    "STARS_LAUNCH_ENROLLMENT_ENABLED": "true",
                    "STARS_LAUNCH_PROFILE_PATH": str(self.profile_path),
                    "STARS_TEST_CREDENTIALS_PATH": str(self.credentials_path),
                    "STARS_LAUNCH_ENROLLMENT_EXPIRES_AT": (
                        self.now + timedelta(hours=2)
                    ).isoformat(),
                },
                now=self.now,
                allowed_directory=self.root,
            )

        unsafe_root = self.root / "unsafe"
        unsafe_root.mkdir()
        os.chmod(unsafe_root, 0o777)
        unsafe = StarsLaunchEnrollmentSettings.from_mapping(
            {
                "STARS_LAUNCH_ENROLLMENT_ENABLED": "true",
                "STARS_LAUNCH_PROFILE_PATH": str(unsafe_root / "profile.json"),
                "STARS_TEST_CREDENTIALS_PATH": str(unsafe_root / "creds.json"),
                "STARS_LAUNCH_ENROLLMENT_EXPIRES_AT": (
                    self.now + timedelta(minutes=10)
                ).isoformat(),
            },
            now=self.now,
            allowed_directory=unsafe_root,
        )
        with self.assertRaisesRegex(StarsLaunchError, "permissions"):
            unsafe.enroll_test_credentials(
                {"bot_token": VALID_TEST_TOKEN, "test_user_id": "7001"},
                now=self.now,
            )

    def test_billing_settings_load_private_profile_and_reject_inline_conflicts(self):
        self.settings.enroll_profile(profile_form(), now=self.now)
        values = self.runtime_values()
        loaded = load_billing_launch_profile(values)
        settings = BillingSettings.from_env(values)

        self.assertNotIn("BILLING_LAUNCH_PROFILE_FILE", loaded)
        self.assertEqual(settings.seller_legal_name, "Example Learning SAS")
        self.assertEqual(settings.support_contact, "@example_support")
        self.assertEqual(settings.terms_version, "stars-prod-v1")
        self.assertTrue(settings.terms_approved)
        self.assertGreaterEqual(len(settings.payload_secret or ""), 43)

        with self.assertRaisesRegex(BillingConfigurationError, "cannot be mixed"):
            BillingSettings.from_env(
                {**values, "BILLING_SUPPORT_CONTACT": "@inline"}
            )
        os.chmod(self.profile_path, 0o640)
        with self.assertRaisesRegex(BillingConfigurationError, "permissions"):
            BillingSettings.from_env(values)
        os.chmod(self.profile_path, 0o400)
        with self.assertRaisesRegex(BillingConfigurationError, "permissions"):
            BillingSettings.from_env(values)

    def test_receipt_and_readiness_are_strict_and_privacy_safe(self):
        self.enroll_all()
        write_receipt(self.receipt_path, completed_at=self.now)
        receipt = validate_stars_test_receipt(
            self.receipt_path, now=self.now
        )
        products = commercial_launch._candidate_products(
            economics.load_snapshot()
        )
        result = stars_launch_readiness(
            self.runtime_values(), products, now=self.now
        )

        self.assertEqual(receipt["status"], "passed")
        self.assertTrue(result["ready"])
        self.assertEqual(result["blockers"], [])
        self.assertTrue(all(result["gates"].values()))
        rendered = json.dumps(result, sort_keys=True)
        for forbidden in (
            "Example Learning",
            "@example_support",
            VALID_TEST_TOKEN,
            "7001",
            str(self.root),
        ):
            self.assertNotIn(forbidden, rendered)

        unsafe = json.loads(self.receipt_path.read_text(encoding="utf-8"))
        unsafe["bot_token"] = VALID_TEST_TOKEN
        self.receipt_path.write_text(json.dumps(unsafe), encoding="utf-8")
        os.chmod(self.receipt_path, 0o600)
        with self.assertRaisesRegex(StarsLaunchError, "schema"):
            validate_stars_test_receipt(self.receipt_path, now=self.now)

    def test_readiness_returns_stable_blockers_without_raising_or_writing(self):
        products = commercial_launch._candidate_products(
            economics.load_snapshot()
        )
        result = stars_launch_readiness(
            self.runtime_values(), products, now=self.now
        )

        self.assertFalse(result["ready"])
        self.assertEqual(result["status"], "blocked")
        self.assertEqual(
            result["blockers"],
            ["billing_profile", "test_credentials", "test_receipt"],
        )
        self.assertFalse(self.profile_path.exists())
        self.assertFalse(self.credentials_path.exists())
        self.assertFalse(self.receipt_path.exists())

    def test_enrollment_overview_never_returns_submitted_values(self):
        self.enroll_all()
        overview = stars_launch_enrollment_overview(
            self.settings, receipt_path=self.receipt_path, now=self.now
        )
        rendered = json.dumps(overview, sort_keys=True)

        self.assertEqual(overview["profile_status"], "consumed")
        self.assertEqual(overview["test_credentials_status"], "consumed")
        self.assertRegex(overview["profile_fingerprint"], r"^[a-f0-9]{12}$")
        self.assertRegex(
            overview["test_credentials_fingerprint"], r"^[a-f0-9]{12}$"
        )
        disabled = StarsLaunchEnrollmentSettings.from_mapping(
            {"STARS_LAUNCH_ENROLLMENT_ENABLED": "false"}
        )
        runtime_overview = stars_launch_enrollment_overview(
            disabled,
            runtime_profile_path=self.profile_path,
            runtime_test_credentials_path=self.credentials_path,
            now=self.now,
        )
        self.assertFalse(runtime_overview["enabled"])
        self.assertEqual(runtime_overview["profile_status"], "consumed")
        self.assertEqual(
            runtime_overview["test_credentials_status"], "consumed"
        )
        for forbidden in (
            "Example Learning",
            "@example_support",
            VALID_TEST_TOKEN,
            "7001",
            str(self.root),
        ):
            self.assertNotIn(forbidden, rendered)


if __name__ == "__main__":
    unittest.main()
