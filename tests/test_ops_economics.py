import copy
import unittest

from mydictionary.ai_tutor import AITutorSettings
from mydictionary.billing import BillingSettings
from ops import mydictionary_economics as economics


class EconomicsContractTest(unittest.TestCase):
    def setUp(self):
        self.snapshot = economics.load_snapshot()

    def test_checked_in_snapshot_is_draft_and_formula_consistent(self):
        result = economics.validate_snapshot(self.snapshot)

        self.assertEqual(result["packages"], 3)
        self.assertEqual(result["daily_limit"], 5)
        self.assertEqual(result["preflight_budget"], 5000)
        self.assertEqual(result["retrospective_breaker"], 5000)
        self.assertEqual(result["project_daily_budget"], 25000)
        self.assertEqual(result["project_monthly_budget"], 100000)
        self.assertEqual(result["in_flight_budget"], 5000)
        self.assertEqual(len(result["snapshot_sha256"]), 64)
        self.assertEqual(result["net_micro_usd_per_xtr"], 10000)
        self.assertTrue(
            all(
                package["status"] == "draft"
                for package in self.snapshot["stars"]["packages"]
            )
        )

    def test_tampered_package_cost_is_rejected(self):
        tampered = copy.deepcopy(self.snapshot)
        tampered["stars"]["packages"][0]["estimated_cost_micro_usd"] += 1

        with self.assertRaisesRegex(
            economics.EconomicsContractError, "estimated_cost"
        ):
            economics.validate_snapshot(tampered)

    def test_unapproved_source_is_rejected(self):
        tampered = copy.deepcopy(self.snapshot)
        tampered["sources"][0] = "https://example.com/pricing"

        with self.assertRaisesRegex(
            economics.EconomicsContractError, "Unapproved"
        ):
            economics.validate_snapshot(tampered)

    def test_approved_ai_copy_can_render_an_exact_disabled_environment(self):
        approved = copy.deepcopy(self.snapshot)
        approved["ai"]["status"] = "approved"

        rendered = economics.render_environment(approved)
        environment = dict(line.split("=", 1) for line in rendered.splitlines())

        self.assertEqual(environment["AI_TUTOR_ENABLED"], "false")
        self.assertEqual(environment["AI_SERVICE_TIER"], "default")
        self.assertEqual(
            len(environment["AI_ECONOMICS_SNAPSHOT_SHA256"]), 64
        )
        self.assertNotEqual(
            environment["AI_ECONOMICS_SNAPSHOT_SHA256"],
            economics.validate_snapshot(self.snapshot)["snapshot_sha256"],
        )

    def test_environment_renderer_is_disabled_and_contains_no_secrets(self):
        rendered = economics.render_environment(self.snapshot)

        self.assertIn("AI_TUTOR_ENABLED=false", rendered)
        self.assertIn("TELEGRAM_STARS_ENABLED=false", rendered)
        self.assertIn("BILLING_TERMS_APPROVED=false", rendered)
        self.assertIn(
            "AI_MAX_PREFLIGHT_COST_MICRO_USD_PER_REQUEST=5000", rendered
        )
        self.assertIn(
            "AI_RETROSPECTIVE_BREAKER_MICRO_USD_PER_RESPONSE=5000", rendered
        )
        self.assertIn("AI_MAX_PROJECT_COST_MICRO_USD_PER_DAY=25000", rendered)
        self.assertIn("AI_MAX_PROJECT_COST_MICRO_USD_PER_MONTH=100000", rendered)
        self.assertIn("AI_MAX_IN_FLIGHT_COST_MICRO_USD=5000", rendered)
        self.assertIn("AI_SERVICE_TIER=default", rendered)
        self.assertIn("AI_ECONOMICS_SNAPSHOT_SHA256=", rendered)
        for forbidden in (
            "OPENAI_API_KEY",
            "AI_SAFETY_SALT",
            "BILLING_PAYLOAD_SECRET",
            "BILLING_SUPPORT_CONTACT",
            "BILLING_TERMS_TEXT",
        ):
            self.assertNotIn(forbidden, rendered)
        environment = dict(line.split("=", 1) for line in rendered.splitlines())
        self.assertFalse(AITutorSettings.from_env(environment).enabled)
        self.assertFalse(BillingSettings.from_env(environment).enabled)


if __name__ == "__main__":
    unittest.main()
