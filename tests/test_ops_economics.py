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

    def test_environment_renderer_is_disabled_and_contains_no_secrets(self):
        rendered = economics.render_environment(self.snapshot)

        self.assertIn("AI_TUTOR_ENABLED=false", rendered)
        self.assertIn("TELEGRAM_STARS_ENABLED=false", rendered)
        self.assertIn("BILLING_TERMS_APPROVED=false", rendered)
        self.assertIn("AI_MAX_COST_MICRO_USD_PER_REQUEST=5000", rendered)
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
