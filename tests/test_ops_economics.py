import copy
import unittest

from mydictionary.ai_tutor import AITutorSettings
from mydictionary.billing import BillingSettings
from ops import mydictionary_economics as economics


class EconomicsContractTest(unittest.TestCase):
    def setUp(self):
        self.snapshot = economics.load_snapshot()

    def test_checked_in_snapshot_has_approved_ai_and_candidate_stars(self):
        result = economics.validate_snapshot(self.snapshot)

        self.assertEqual(result["packages"], 4)
        self.assertEqual(result["snapshot_id"], "mydictionary-commercial-v3-2026-08-14")
        self.assertEqual(self.snapshot["ai"]["status"], "approved")
        self.assertEqual(self.snapshot["status"], "candidate")
        self.assertEqual(result["minimum_margin_bps"], 5000)
        self.assertEqual(result["stress_net_micro_usd_per_xtr"], 8500)
        self.assertTrue(result["stress_launchable"])
        self.assertEqual(result["daily_limit"], 5)
        self.assertEqual(result["preflight_budget"], 5000)
        self.assertEqual(result["modelled_cost_per_credit"], 6000)
        self.assertEqual(result["retrospective_breaker"], 5000)
        self.assertEqual(result["project_daily_budget"], 25000)
        self.assertEqual(result["project_monthly_budget"], 100000)
        self.assertEqual(result["in_flight_budget"], 5000)
        self.assertEqual(len(result["snapshot_sha256"]), 64)
        self.assertEqual(result["net_micro_usd_per_xtr"], 10000)
        packages = {
            package["product_id"]: package
            for package in self.snapshot["stars"]["packages"]
        }
        self.assertEqual(
            {
                product_id: (package["credits"], package["price_xtr"])
                for product_id, package in packages.items()
            },
            {
                "ai-mini": (20, 69),
                "ai-starter": (50, 129),
                "ai-value": (150, 319),
                "ai-monthly": (100, 229),
            },
        )
        self.assertTrue(
            all(package["status"] == "candidate" for package in packages.values())
        )
        self.assertTrue(
            all(package["estimated_margin_bps"] >= 5000 for package in packages.values())
        )
        self.assertTrue(
            all(package["stress_margin_bps"] >= 5000 for package in packages.values())
        )
        self.assertEqual(result["measurement_provider_attempts"], 1)
        self.assertEqual(result["measurement_cost_micro_usd"], 2353)
        self.assertFalse(result["measurement_dashboard_charge_verified"])
        self.assertEqual(result["voice_cost_micro_usd_per_hour"], 111000)
        self.assertEqual(result["voice_minimum_billable_seconds"], 10)
        self.assertEqual(result["voice_max_request_cost_micro_usd"], 925)
        self.assertTrue(result["voice_zdr_required"])

    def test_tampered_package_cost_is_rejected(self):
        tampered = copy.deepcopy(self.snapshot)
        tampered["stars"]["packages"][0]["estimated_cost_micro_usd"] += 1

        with self.assertRaisesRegex(
            economics.EconomicsContractError, "estimated_cost"
        ):
            economics.validate_snapshot(tampered)

    def test_modelled_credit_cost_is_independent_from_runtime_preflight_limit(self):
        tampered = copy.deepcopy(self.snapshot)
        tampered["ai"]["limits"]["max_preflight_cost_micro_usd_per_request"] = 4500
        tampered["ai"]["limits"]["max_in_flight_cost_micro_usd"] = 4500

        result = economics.validate_snapshot(tampered)

        self.assertEqual(result["preflight_budget"], 4500)
        self.assertEqual(result["modelled_cost_per_credit"], 6000)

    def test_tampered_groq_voice_contract_is_rejected(self):
        for key, value in (
            ("provider", "openai"),
            ("cost_micro_usd_per_hour", 110999),
            ("minimum_billable_seconds", 0),
            ("max_request_cost_micro_usd", 924),
            ("zdr_required_for_production", False),
        ):
            with self.subTest(key=key):
                tampered = copy.deepcopy(self.snapshot)
                tampered["voice"][key] = value
                with self.assertRaises(economics.EconomicsContractError):
                    economics.validate_snapshot(tampered)

    def test_package_price_or_status_tampering_is_rejected(self):
        for key, value in (("price_xtr", 99), ("status", "active")):
            with self.subTest(key=key):
                tampered = copy.deepcopy(self.snapshot)
                tampered["stars"]["packages"][0][key] = value
                with self.assertRaises(economics.EconomicsContractError):
                    economics.validate_snapshot(tampered)

    def test_measurement_digest_tampering_is_rejected(self):
        self.assertIn("measurement", self.snapshot["ai"])
        tampered = copy.deepcopy(self.snapshot)
        tampered["ai"]["measurement"]["sha256"] = "0" * 64

        with self.assertRaisesRegex(
            economics.EconomicsContractError, "measurement"
        ):
            economics.validate_snapshot(tampered)

    def test_terms_digest_tampering_is_rejected(self):
        tampered = copy.deepcopy(self.snapshot)
        tampered["stars"]["terms_sha256"] = "0" * 64

        with self.assertRaisesRegex(
            economics.EconomicsContractError, "terms SHA-256"
        ):
            economics.validate_snapshot(tampered)

    def test_unapproved_source_is_rejected(self):
        tampered = copy.deepcopy(self.snapshot)
        tampered["sources"][0] = "https://example.com/pricing"

        with self.assertRaisesRegex(
            economics.EconomicsContractError, "Unapproved"
        ):
            economics.validate_snapshot(tampered)

    def test_approved_ai_snapshot_renders_an_exact_disabled_environment(self):
        rendered = economics.render_environment(self.snapshot)
        environment = dict(line.split("=", 1) for line in rendered.splitlines())

        self.assertEqual(environment["AI_TUTOR_ENABLED"], "false")
        self.assertEqual(environment["AI_SERVICE_TIER"], "default")
        self.assertEqual(
            len(environment["AI_ECONOMICS_SNAPSHOT_SHA256"]), 64
        )
        self.assertEqual(
            environment["AI_ECONOMICS_SNAPSHOT_SHA256"],
            economics.validate_snapshot(self.snapshot)["snapshot_sha256"],
        )

    def test_environment_renderer_is_disabled_and_contains_no_secrets(self):
        rendered = economics.render_environment(self.snapshot)

        self.assertIn("AI_TUTOR_ENABLED=false", rendered)
        self.assertIn("VOICE_TUTOR_ENABLED=false", rendered)
        self.assertIn("VOICE_PROVIDER=groq", rendered)
        self.assertIn("VOICE_TRANSCRIPTION_MODEL=whisper-large-v3", rendered)
        self.assertIn("VOICE_COST_MICRO_USD_PER_MINUTE=1850", rendered)
        self.assertIn("VOICE_MINIMUM_BILLABLE_SECONDS=10", rendered)
        self.assertIn("VOICE_MAX_DURATION_SECONDS=30", rendered)
        self.assertIn("VOICE_GROQ_ZDR_VERIFIED=false", rendered)
        self.assertIn("VOICE_TRANSLATION_ENABLED=false", rendered)
        self.assertIn("VOICE_TRANSLATION_PROVIDER=groq", rendered)
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
            "BILLING_SELLER_LEGAL_NAME",
            "BILLING_SELLER_ADDRESS",
            "BILLING_SELLER_EMAIL",
            "BILLING_SELLER_PHONE",
        ):
            self.assertNotIn(forbidden, rendered)
        environment = dict(line.split("=", 1) for line in rendered.splitlines())
        self.assertFalse(AITutorSettings.from_env(environment).enabled)
        self.assertFalse(BillingSettings.from_env(environment).enabled)


if __name__ == "__main__":
    unittest.main()
