from datetime import datetime, timedelta, timezone
import tempfile
import unittest
from types import SimpleNamespace

from sqlalchemy import func, select

from mydictionary.privacy import (
    PrivacyStateError,
    RetentionPolicy,
    apply_retention,
    erase_user_learning_data,
    retention_report,
)
from mydictionary.storage import (
    AIUsage,
    AbuseEvent,
    AnalyticsEvent,
    BillingCreditLedger,
    DatabaseStore,
    User,
    UserProgress,
)


class PrivacyTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="mydictionary-privacy-")
        self.store = DatabaseStore(
            f"sqlite:///{self.temporary.name}/test.sqlite3"
        )
        self.user_id = 1234
        self.store.ensure_user(
            SimpleNamespace(
                id=self.user_id,
                username="learner",
                first_name="Test",
                last_name="User",
                language_code="ru",
            )
        )

    def tearDown(self):
        self.store.close()
        self.temporary.cleanup()

    def test_retention_preview_and_execute_exclude_reserved_ai_usage(self):
        old = datetime(2025, 1, 1, tzinfo=timezone.utc)
        self.store.record_event(self.user_id, "start_received")
        with self.store.Session.begin() as session:
            event = session.execute(select(AnalyticsEvent)).scalar_one()
            event.occurred_at = old
            session.add(
                AbuseEvent(
                    event_id="abuse-old",
                    telegram_user_id=self.user_id,
                    scope="ai",
                    rule="rate_limit_exceeded",
                    limit_value=2,
                    observed_count=3,
                    occurred_at=old,
                )
            )
            for request_id, status in (("usage-old", "completed"), ("reserved", "reserved")):
                session.add(
                    AIUsage(
                        request_id=request_id,
                        telegram_user_id=self.user_id,
                        action="block_tutor",
                        provider="test",
                        model="test",
                        status=status,
                        context_fingerprint="a" * 64,
                        reserved_credits=1,
                        created_at=old,
                    )
                )
        policy = RetentionPolicy(30, 30, 30, 1)
        now = datetime(2026, 8, 5, tzinfo=timezone.utc)

        preview = retention_report(self.store, policy, now=now)
        applied = apply_retention(self.store, policy, now=now)

        self.assertEqual(preview.analytics_events, 1)
        self.assertEqual(preview.ai_usage, 1)
        self.assertEqual(applied, preview)
        with self.store.Session() as session:
            self.assertIsNotNone(session.get(AIUsage, "reserved"))
            self.assertIsNone(session.get(AIUsage, "usage-old"))

    def test_erasure_removes_learning_data_and_preserves_financial_ledger(self):
        with self.store.Session.begin() as session:
            session.add(
                BillingCreditLedger(
                    entry_id="financial-entry",
                    telegram_user_id=self.user_id,
                    delta=10,
                    balance_after=10,
                    entry_type="admin_grant",
                    idempotency_key="privacy-test",
                    reason="retained financial record",
                    actor="test",
                )
            )

        result = erase_user_learning_data(
            self.store, user_id=self.user_id, actor="self-service"
        )
        repeated = erase_user_learning_data(
            self.store, user_id=self.user_id, actor="self-service"
        )

        self.assertFalse(result.already_erased)
        self.assertTrue(repeated.already_erased)
        with self.store.Session() as session:
            user = session.get(User, self.user_id)
            self.assertEqual(user.privacy_status, "erased")
            self.assertEqual(user.access_status, "blocked")
            self.assertIsNone(user.username)
            self.assertIsNone(session.get(UserProgress, self.user_id))
            self.assertEqual(
                session.scalar(
                    select(func.count()).select_from(BillingCreditLedger)
                ),
                1,
            )

    def test_admin_cannot_be_erased(self):
        with self.store.Session.begin() as session:
            session.get(User, self.user_id).role = "admin"

        with self.assertRaises(PrivacyStateError):
            erase_user_learning_data(
                self.store, user_id=self.user_id, actor="self-service"
            )
