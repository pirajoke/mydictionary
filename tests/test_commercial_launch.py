import copy
import tempfile
import unittest
from pathlib import Path

from sqlalchemy import func, select

from mydictionary.admin_store import AdminStore
from mydictionary.commercial_launch import (
    CommercialLaunchError,
    commercial_launch_overview,
    load_measurement_report,
    validate_measurement_report,
)
from mydictionary.storage import AdminAuditLog, DatabaseStore
from ops import mydictionary_commercial_launch as launch_cli
from ops import mydictionary_economics as economics


class CommercialLaunchContractTest(unittest.TestCase):
    def setUp(self):
        self.snapshot = economics.load_snapshot()

    def test_measurement_report_is_privacy_safe_and_complete(self):
        report = load_measurement_report(
            self.snapshot["ai"]["measurement"], root=economics.ROOT
        )
        summary = validate_measurement_report(report)

        self.assertEqual(summary["model"], "gpt-5.6-luna")
        self.assertEqual(summary["service_tier"], "default")
        self.assertEqual(summary["provider_attempts"], 1)
        self.assertEqual(summary["input_tokens"], 313)
        self.assertEqual(summary["output_tokens"], 340)
        self.assertEqual(summary["total_tokens"], 653)
        self.assertEqual(summary["cost_micro_usd"], 2353)
        self.assertEqual(summary["latency_ms"], 4674)
        self.assertEqual(summary["validation_status"], "passed")
        self.assertFalse(summary["dashboard_charge_verified"])

    def test_measurement_report_rejects_sensitive_or_billable_identifiers(self):
        report = load_measurement_report(
            self.snapshot["ai"]["measurement"], root=economics.ROOT
        )
        for key in ("telegram_user_id", "request_id", "prompt", "response", "api_key", "charge_id"):
            with self.subTest(key=key):
                unsafe = copy.deepcopy(report)
                unsafe[key] = "must-not-appear"
                with self.assertRaisesRegex(CommercialLaunchError, "sensitive"):
                    validate_measurement_report(unsafe)

    def test_seed_products_is_explicit_draft_and_idempotent(self):
        with tempfile.TemporaryDirectory(prefix="commercial-launch-") as directory:
            store = DatabaseStore(f"sqlite:///{Path(directory) / 'launch.db'}")
            try:
                first = launch_cli.seed_products(
                    store, self.snapshot, actor="commercial-launch-test"
                )
                products = AdminStore(store).billing_products()
                with store.Session() as session:
                    first_audit_count = session.scalar(
                        select(func.count(AdminAuditLog.id))
                    )
                second = launch_cli.seed_products(
                    store, self.snapshot, actor="commercial-launch-test"
                )
                with store.Session() as session:
                    second_audit_count = session.scalar(
                        select(func.count(AdminAuditLog.id))
                    )
            finally:
                store.close()

        self.assertEqual(first, {"created": 3, "updated": 0, "unchanged": 0})
        self.assertEqual(second, {"created": 0, "updated": 0, "unchanged": 3})
        self.assertEqual(first_audit_count, second_audit_count)
        self.assertEqual(
            {row["product_id"]: (row["credits"], row["price_xtr"], row["status"]) for row in products},
            {
                "ai-starter": (50, 100, "draft"),
                "ai-value": (150, 240, "draft"),
                "ai-monthly": (100, 180, "draft"),
            },
        )

    def test_overview_exposes_individual_stress_blocks_and_catalog_drift(self):
        overview = commercial_launch_overview(
            self.snapshot,
            products=[],
            seller_complete=False,
            terms_approved=False,
            checkout_enabled=False,
            root=economics.ROOT,
        )

        self.assertEqual(overview["status"], "blocked")
        self.assertEqual(overview["catalog_status"], "missing")
        self.assertFalse(overview["seller_complete"])
        self.assertFalse(overview["terms_approved"])
        self.assertFalse(overview["checkout_enabled"])
        self.assertEqual(overview["measurement"]["provider_attempts"], 1)
        self.assertEqual(
            [row["product_id"] for row in overview["packages"] if not row["stress_ready"]],
            ["ai-starter", "ai-value", "ai-monthly"],
        )

    def test_cli_has_no_product_activation_action(self):
        parsed = launch_cli.parser().parse_args(["seed-products"])
        self.assertFalse(parsed.execute)
        with self.assertRaises(SystemExit):
            launch_cli.parser().parse_args(["activate-products"])

    def test_overview_rejects_tampered_package_formula(self):
        tampered = copy.deepcopy(self.snapshot)
        tampered["stars"]["packages"][0]["estimated_cost_micro_usd"] += 1

        with self.assertRaisesRegex(CommercialLaunchError, "formula"):
            commercial_launch_overview(
                tampered,
                products=[],
                seller_complete=False,
                terms_approved=False,
                checkout_enabled=False,
                root=economics.ROOT,
            )


if __name__ == "__main__":
    unittest.main()
