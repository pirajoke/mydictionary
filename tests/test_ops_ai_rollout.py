import copy
from datetime import date
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from mydictionary.economics import load_ai_economics_contract
from ops import mydictionary_economics as economics

try:
    from ops import mydictionary_ai_rollout as rollout
except ImportError:
    rollout = None


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "ai_tutor_eval.json"
EXPECTED_MIGRATION = "0017_admin_auth_recovery"


def parse_environment(rendered: str) -> dict[str, str]:
    return dict(line.split("=", 1) for line in rendered.splitlines() if line)


class AIPilotEconomicsContractTest(unittest.TestCase):
    def test_ac_05_only_ai_is_approved_with_forty_free_pilot_credits(self):
        snapshot = economics.load_snapshot()
        result = economics.validate_snapshot(snapshot)

        self.assertEqual(
            snapshot["snapshot_id"],
            "mydictionary-commercial-v4-2026-08-28",
        )
        self.assertEqual(snapshot["reviewed_on"], "2026-08-28")
        self.assertEqual(snapshot["ai"]["status"], "approved")
        self.assertNotEqual(snapshot.get("status"), "approved")
        self.assertEqual(result["pricing_max_age_days"], 30)
        self.assertEqual(result["initial_credits"], 40)
        self.assertEqual(result["credits_per_request"], 1)
        self.assertTrue(
            all(
                package["status"] == "candidate"
                for package in snapshot["stars"]["packages"]
            )
        )
        rendered = economics.render_environment(snapshot)
        self.assertIn("VOICE_TUTOR_ENABLED=false", rendered)
        self.assertIn("TELEGRAM_STARS_ENABLED=false", rendered)

    def test_ac_06_exact_prices_budgets_tier_and_zero_sdk_retries_are_rendered(self):
        snapshot = economics.load_snapshot()
        contract = load_ai_economics_contract(
            ROOT / "config" / "launch-economics.json",
            require_approved=True,
        )
        self.assertEqual(contract.input_usd_per_million, Decimal("0.20"))
        self.assertEqual(contract.cached_input_usd_per_million, Decimal("0.02"))
        self.assertEqual(contract.cache_write_usd_per_million, Decimal("0.25"))
        self.assertEqual(contract.output_usd_per_million, Decimal("1.20"))

        environment = parse_environment(economics.render_environment(snapshot))
        expected = {
            "AI_INPUT_USD_PER_MILLION": "0.20",
            "AI_CACHED_INPUT_USD_PER_MILLION": "0.02",
            "AI_CACHE_WRITE_USD_PER_MILLION": "0.25",
            "AI_OUTPUT_USD_PER_MILLION": "1.20",
            "AI_PRICING_REVIEWED_ON": "2026-08-28",
            "AI_PRICING_MAX_AGE_DAYS": "30",
            "AI_INITIAL_CREDITS": "40",
            "AI_CREDITS_PER_REQUEST": "1",
            "AI_MAX_DAILY_REQUESTS_PER_USER": "0",
            "AI_MAX_PREFLIGHT_COST_MICRO_USD_PER_REQUEST": "5000",
            "AI_RETROSPECTIVE_BREAKER_MICRO_USD_PER_RESPONSE": "5000",
            "AI_MAX_PROJECT_COST_MICRO_USD_PER_DAY": "25000",
            "AI_MAX_PROJECT_COST_MICRO_USD_PER_MONTH": "100000",
            "AI_MAX_IN_FLIGHT_COST_MICRO_USD": "5000",
            "AI_SERVICE_TIER": "default",
            "AI_SDK_MAX_RETRIES": "0",
        }
        for name, value in expected.items():
            with self.subTest(name=name):
                self.assertEqual(environment[name], value)


class AIPilotReadinessTest(unittest.TestCase):
    def require_rollout(self):
        self.assertIsNotNone(
            rollout,
            "public module ops.mydictionary_ai_rollout is required by AC-07",
        )
        return rollout

    def environment(self):
        values = parse_environment(
            economics.render_environment(economics.load_snapshot())
        )
        values.update(
            {
                "AI_TUTOR_ENABLED": "true",
                "OPENAI_API_KEY": "test-only-key",
                "AI_SAFETY_SALT": "s" * 32,
                "AI_CONSENT_VERSION": "ai-processing-2026-08-09",
                "AI_PROCESSING_NOTICE": (
                    "AI Tutor sends only the current question and active "
                    "learning block after explicit consent."
                ),
                "VOICE_TUTOR_ENABLED": "false",
                "TELEGRAM_STARS_ENABLED": "false",
            }
        )
        return values

    def runtime_state(self):
        return {
            "circuit_breaker_open": False,
            "in_flight_micro_usd": 0,
            "fallback_journal_entries": 0,
        }

    def test_ac_07_ai_readiness_ignores_disabled_voice_and_stars(self):
        api = self.require_rollout()
        environment = self.environment()

        result = api.evaluate_ai_pilot_readiness(
            environment,
            runtime_state=self.runtime_state(),
            database_revision=EXPECTED_MIGRATION,
            fixture_path=FIXTURE,
            today=date(2026, 8, 28),
        )

        self.assertTrue(result["ready"])
        self.assertEqual(result["migration_revision"], EXPECTED_MIGRATION)
        self.assertEqual(result["evaluation_languages"], 8)
        self.assertEqual(result["voice_status"], "disabled")
        self.assertEqual(result["stars_status"], "disabled")
        self.assertEqual(
            set(result["checks"]),
            {
                "economics",
                "model_and_tier",
                "rates",
                "consent",
                "migration",
                "eight_language_contract",
                "circuit_breaker",
                "in_flight",
                "fallback_journal",
            },
        )

    def test_err_02_bad_runtime_state_or_contract_fails_without_flag_mutation(self):
        api = self.require_rollout()
        cases = (
            ("tampered economics", {}, {"AI_ECONOMICS_SNAPSHOT_SHA256": "0" * 64}, EXPECTED_MIGRATION),
            ("open breaker", {"circuit_breaker_open": True}, {}, EXPECTED_MIGRATION),
            ("in flight", {"in_flight_micro_usd": 1}, {}, EXPECTED_MIGRATION),
            ("fallback journal", {"fallback_journal_entries": 1}, {}, EXPECTED_MIGRATION),
            ("wrong migration", {}, {}, "0012_ai_runtime_gates"),
        )
        for label, state_changes, env_changes, migration in cases:
            with self.subTest(case=label):
                environment = self.environment()
                environment.update(env_changes)
                original = dict(environment)
                state = self.runtime_state()
                state.update(state_changes)
                with self.assertRaises(api.AIPilotReadinessError):
                    api.evaluate_ai_pilot_readiness(
                        environment,
                        runtime_state=state,
                        database_revision=migration,
                        fixture_path=FIXTURE,
                        today=date(2026, 8, 28),
                    )
                self.assertEqual(environment, original)
                self.assertEqual(environment["AI_TUTOR_ENABLED"], "true")
                self.assertEqual(environment["VOICE_TUTOR_ENABLED"], "false")
                self.assertEqual(environment["TELEGRAM_STARS_ENABLED"], "false")

    def test_err_02_unapproved_snapshot_fails_without_flag_mutation(self):
        api = self.require_rollout()
        snapshot = copy.deepcopy(economics.load_snapshot())
        snapshot["ai"]["status"] = "candidate"
        with tempfile.TemporaryDirectory(prefix="ai-rollout-unapproved-") as raw:
            path = Path(raw) / "snapshot.json"
            path.write_text(
                json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            environment = self.environment()
            environment["AI_ECONOMICS_SNAPSHOT_PATH"] = str(path)
            environment["AI_ECONOMICS_SNAPSHOT_SHA256"] = hashlib.sha256(
                path.read_bytes()
            ).hexdigest()
            original = dict(environment)

            with self.assertRaises(api.AIPilotReadinessError):
                api.evaluate_ai_pilot_readiness(
                    environment,
                    runtime_state=self.runtime_state(),
                    database_revision=EXPECTED_MIGRATION,
                    fixture_path=FIXTURE,
                    today=date(2026, 8, 28),
                )

        self.assertEqual(environment, original)


if __name__ == "__main__":
    unittest.main()
