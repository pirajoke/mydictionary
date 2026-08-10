import tempfile
import unittest
from types import SimpleNamespace

from mydictionary.storage import DatabaseStore

try:
    from ops import mydictionary_credit_rollout as rollout
except ImportError:
    rollout = None


class InitialCreditRolloutTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="credit-rollout-")
        self.store = DatabaseStore(
            f"sqlite:///{self.temporary.name}/credit-rollout.sqlite3"
        )
        for user_id in (801, 802):
            self.store.ensure_user(
                SimpleNamespace(
                    id=user_id,
                    username=None,
                    first_name="Pilot",
                    last_name=None,
                    language_code="ru",
                )
            )
            self.store.activate_user_access(user_id)
        request_id = self.store.reserve_ai_usage(
            801,
            action="block_tutor",
            provider="openai",
            model="gpt-test",
            credits=1,
            initial_credits=5,
            context_fingerprint="a" * 64,
            max_daily_requests=5,
            requested_service_tier="default",
            economics_snapshot_id="test-snapshot",
            economics_snapshot_sha256="b" * 64,
            projected_cost_micro_usd=100,
            max_project_cost_micro_usd_per_day=10_000,
            max_project_cost_micro_usd_per_month=100_000,
            max_in_flight_cost_micro_usd=10_000,
            request_id="initial-credit-fixture",
        )
        self.store.fail_ai_usage(request_id, error_code="fixture")

    def tearDown(self):
        self.store.close()
        self.temporary.cleanup()

    def require_rollout(self):
        self.assertIsNotNone(rollout, "credit rollout operator module is required")
        return rollout

    def test_ac_06_preview_is_aggregate_and_does_not_write(self):
        api = self.require_rollout()
        result = api.rollout_initial_credits(
            self.store,
            target_credits=40,
            rollout_id="pilot-40-v1",
            actor="test",
            execute=False,
        )
        self.assertEqual(
            result,
            {
                "active_users": 2,
                "pending_users": 2,
                "planned_credits": 75,
                "applied_users": 0,
                "applied_credits": 0,
                "target_credits": 40,
                "executed": False,
            },
        )
        self.assertEqual(self.store.ai_usage_summary(801)["available_credits"], 5)
        self.assertEqual(self.store.ai_usage_summary(802)["available_credits"], 0)
        self.assertNotIn("801", str(result))

    def test_err_03_execute_is_idempotent_and_preserves_spend(self):
        api = self.require_rollout()
        first = api.rollout_initial_credits(
            self.store,
            target_credits=40,
            rollout_id="pilot-40-v1",
            actor="test",
            execute=True,
        )
        second = api.rollout_initial_credits(
            self.store,
            target_credits=40,
            rollout_id="pilot-40-v1",
            actor="test",
            execute=True,
        )
        self.assertEqual(first["applied_users"], 2)
        self.assertEqual(first["applied_credits"], 75)
        self.assertEqual(second["pending_users"], 0)
        self.assertEqual(second["applied_credits"], 0)
        self.assertEqual(self.store.ai_usage_summary(801)["available_credits"], 40)
        self.assertEqual(self.store.ai_usage_summary(802)["available_credits"], 40)
