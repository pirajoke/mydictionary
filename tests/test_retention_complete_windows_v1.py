from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch


import mydictionary.admin_store as admin_store_module
from mydictionary.admin_store import AdminStore
from mydictionary.storage import AnalyticsEvent, DatabaseStore


class FrozenDateTime(datetime):
    observed_at = datetime(2026, 9, 10, 12, 0, tzinfo=timezone.utc)

    @classmethod
    def now(cls, tz=None):
        value = cls.observed_at
        if tz is None:
            return value.replace(tzinfo=None)
        return value.astimezone(tz)


class RetentionCompleteWindowsV1Test(unittest.TestCase):
    def retention_scenario(
        self,
        *,
        surface: str,
        day: int,
        synthetic_user_id: int,
    ) -> dict[str, dict[str, float | int]]:
        with tempfile.TemporaryDirectory(prefix="retention-window-") as directory:
            store = DatabaseStore(f"sqlite:///{Path(directory) / 'retention.sqlite3'}")
            try:
                store.ensure_user(SimpleNamespace(id=synthetic_user_id))
                entry_event = (
                    "onboarding_started"
                    if surface == "product_funnel"
                    else "pilot_waitlist_joined"
                )
                entry_id = store.record_event(
                    synthetic_user_id,
                    entry_event,
                    source="synthetic-test",
                )
                activity_id = store.record_event(
                    synthetic_user_id,
                    "block_started",
                    source="synthetic-test",
                )
                cohort_at = datetime(2026, 9, 1, 0, 0, tzinfo=timezone.utc)
                activity_at = cohort_at + timedelta(days=day, hours=1)
                with store.Session.begin() as session:
                    session.get(AnalyticsEvent, entry_id).occurred_at = cohort_at
                    session.get(AnalyticsEvent, activity_id).occurred_at = activity_at

                admin_store = AdminStore(store)
                snapshots = {}
                for state, observed_at in (
                    ("incomplete", activity_at),
                    ("complete", cohort_at + timedelta(days=day + 1)),
                ):
                    FrozenDateTime.observed_at = observed_at
                    with patch.object(admin_store_module, "datetime", FrozenDateTime):
                        report = getattr(admin_store, surface)(days=30)
                    snapshots[state] = report["retention"][f"d{day}"]
                return snapshots
            finally:
                store.close()

    def assert_complete_window_boundary(self, day: int) -> None:
        observed = {
            surface: self.retention_scenario(
                surface=surface,
                day=day,
                synthetic_user_id=910_000 + day * 10 + index,
            )
            for index, surface in enumerate(("product_funnel", "pilot_overview"), 1)
        }
        expected = {
            surface: {
                "incomplete": {"eligible": 0, "users": 0, "rate": 0},
                "complete": {"eligible": 1, "users": 1, "rate": 100},
            }
            for surface in observed
        }
        self.assertEqual(observed, expected)

    def test_d1_requires_the_complete_24_to_48_hour_window(self):
        self.assert_complete_window_boundary(1)

    def test_d7_requires_the_complete_168_to_192_hour_window(self):
        self.assert_complete_window_boundary(7)


if __name__ == "__main__":
    unittest.main()
