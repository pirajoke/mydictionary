from datetime import datetime, timedelta, timezone
import tempfile
import unittest

from sqlalchemy import func, select

from mydictionary.safety import (
    PersistentRateLimiter,
    RateLimitPolicy,
    SafetyConfigurationError,
    SafetySettings,
)
from mydictionary.storage import AbuseEvent, DatabaseStore, RateLimitBucket


class SafetySettingsTest(unittest.TestCase):
    def test_defaults_are_enabled_and_sensitive_scopes_are_tighter(self):
        settings = SafetySettings.from_env({})

        self.assertTrue(settings.enabled)
        self.assertLess(settings.ai.limit, settings.default.limit)
        self.assertEqual(settings.for_handler("cmd_buy")[0], "billing")
        self.assertEqual(settings.for_handler("billing_consent_cb")[0], "billing")
        self.assertEqual(settings.for_handler("billing_open_cb")[0], "billing")
        self.assertEqual(settings.for_handler("billing_resume_ai_cb")[0], "ai")
        self.assertEqual(settings.for_handler("block_quiz_cb")[0], "learning")
        self.assertEqual(settings.for_handler("cmd_continue")[0], "learning")

    def test_invalid_values_fail_closed(self):
        with self.assertRaises(SafetyConfigurationError):
            SafetySettings.from_env({"SAFETY_RATE_LIMITS_ENABLED": "maybe"})
        with self.assertRaises(SafetyConfigurationError):
            SafetySettings.from_env({"SAFETY_AI_REQUESTS_PER_WINDOW": "0"})


class PersistentRateLimiterTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="mydictionary-safety-")
        self.store = DatabaseStore(
            f"sqlite:///{self.temporary.name}/test.sqlite3"
        )
        self.observed_at = datetime(2026, 8, 5, 12, 0, tzinfo=timezone.utc)
        self.limiter = PersistentRateLimiter(
            self.store, now=lambda: self.observed_at
        )
        self.policy = RateLimitPolicy(limit=2, window_seconds=60, block_seconds=30)

    def tearDown(self):
        self.store.close()
        self.temporary.cleanup()

    def test_threshold_blocks_and_records_one_privacy_minimized_event(self):
        first = self.limiter.consume(user_id=101, scope="ai", policy=self.policy)
        second = self.limiter.consume(user_id=101, scope="ai", policy=self.policy)
        denied = self.limiter.consume(user_id=101, scope="ai", policy=self.policy)
        repeated = self.limiter.consume(user_id=101, scope="ai", policy=self.policy)

        self.assertTrue(first.allowed)
        self.assertTrue(second.allowed)
        self.assertFalse(denied.allowed)
        self.assertEqual(denied.retry_after_seconds, 30)
        self.assertFalse(repeated.allowed)
        with self.store.Session() as session:
            self.assertEqual(
                session.scalar(select(func.count()).select_from(AbuseEvent)), 1
            )
            event = session.execute(select(AbuseEvent)).scalar_one()
            self.assertEqual(event.scope, "ai")
            self.assertEqual(event.rule, "rate_limit_exceeded")
            self.assertEqual(event.observed_count, 3)

    def test_expired_block_starts_a_fresh_window(self):
        for _ in range(3):
            self.limiter.consume(user_id=202, scope="billing", policy=self.policy)
        self.observed_at += timedelta(seconds=31)

        decision = self.limiter.consume(
            user_id=202, scope="billing", policy=self.policy
        )

        self.assertTrue(decision.allowed)
        self.assertEqual(decision.remaining, 1)
        with self.store.Session() as session:
            bucket = session.get(RateLimitBucket, (202, "billing"))
            self.assertEqual(bucket.attempts, 1)

    def test_scopes_are_independent_per_user(self):
        for _ in range(3):
            self.limiter.consume(user_id=303, scope="ai", policy=self.policy)

        self.assertTrue(
            self.limiter.consume(
                user_id=303, scope="learning", policy=self.policy
            ).allowed
        )
        self.assertTrue(
            self.limiter.consume(
                user_id=404, scope="ai", policy=self.policy
            ).allowed
        )
