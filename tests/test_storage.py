import json
import logging
import os
import stat
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import Barrier
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

from mydictionary.content import target_text
from mydictionary.ai_metering import AIMeteringJournal

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, select, text

from mydictionary.legacy import import_legacy_user
import mydictionary.storage as storage_module
from mydictionary.storage import (
    AIQuotaExceeded,
    AIUsage,
    AIUsageStateError,
    AdminAuditLog,
    AnalyticsEvent,
    BillingCreditLedger,
    DatabaseStore,
    TelegramNotification,
    UserConsent,
    UserPackEnrollment,
    vocabulary_id_for,
)


PROFILE_DEFAULTS = {
    "total_correct": 0,
    "total_wrong": 0,
    "sessions": 0,
    "xp": 0,
    "level": 1,
    "streak": 0,
    "streak_best": 0,
    "last_activity_date": None,
    "today_xp": 0,
    "today_date": None,
    "active_lang": "en",
    "active_pack_id": None,
}


class DatabaseStoreTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory(prefix="mydictionary-storage-")
        self.database_path = Path(self.temp_dir.name) / "test.db"
        self.store = DatabaseStore(f"sqlite:///{self.database_path}")

    def tearDown(self):
        self.store.close()
        self.temp_dir.cleanup()

    def test_ac_02_migration_creates_ai_processing_consent_schema(self):
        inspector = inspect(self.store.engine)
        tables = set(inspector.get_table_names())
        self.assertTrue(
            {
                "alembic_version",
                "users",
                "user_progress",
                "word_progress",
                "data_imports",
                "ai_allowances",
                "ai_usage",
                "ai_budget_state",
                "app_settings",
                "admin_credentials",
                "admin_audit_log",
                "ai_credit_ledger",
                "user_pack_enrollments",
                "analytics_events",
                "ai_wallets",
                "billing_products",
                "payment_orders",
                "stars_payments",
                "billing_credit_ledger",
                "refund_requests",
                "user_consents",
                "telegram_notifications",
            }.issubset(tables)
        )
        user_columns = {column["name"] for column in inspector.get_columns("users")}
        self.assertTrue(
            {
                "role",
                "native_language",
                "learning_goal",
                "daily_word_goal",
                "onboarding_completed_at",
                "acquisition_source",
                "access_status",
                "access_status_updated_at",
            }.issubset(user_columns)
        )
        progress_columns = {
            column["name"] for column in inspector.get_columns("user_progress")
        }
        self.assertIn("active_pack_id", progress_columns)
        with self.store.engine.connect() as connection:
            revision = connection.execute(
                text("select version_num from alembic_version")
            ).scalar_one()
        self.assertEqual(revision, "0017_admin_auth_recovery")

        ai_usage_columns = {
            column["name"] for column in inspector.get_columns("ai_usage")
        }
        self.assertTrue(
            {
                "requested_service_tier",
                "returned_service_tier",
                "economics_snapshot_id",
                "economics_snapshot_sha256",
                "provider_attempts",
                "provider_response_received",
                "cost_is_estimate",
                "projected_cost_micro_usd",
                "provider_completed_at",
            }.issubset(ai_usage_columns)
        )

    def test_notification_outbox_leases_retries_and_completes(self):
        user_id = 221
        observed_at = datetime(2026, 8, 6, 12, 0, tzinfo=timezone.utc)
        self.store.ensure_user_id(user_id)
        self.store.activate_user_access(user_id)
        with self.store.Session.begin() as session:
            session.add(
                TelegramNotification(
                    notification_id="notification-1",
                    telegram_user_id=user_id,
                    kind="pilot_access_approved",
                    status="pending",
                    idempotency_key="pilot-access:221:test",
                    available_at=observed_at,
                    created_at=observed_at,
                    updated_at=observed_at,
                )
            )

        first = self.store.claim_telegram_notifications(now=observed_at)
        self.assertEqual(len(first), 1)
        self.assertEqual(first[0]["attempts"], 1)
        self.assertEqual(
            self.store.claim_telegram_notifications(now=observed_at), []
        )

        status = self.store.retry_telegram_notification(
            "notification-1",
            error_code="Timed Out!",
            retry_seconds=10,
            now=observed_at,
        )
        self.assertEqual(status, "pending")
        self.assertEqual(
            self.store.claim_telegram_notifications(
                now=observed_at + timedelta(seconds=9)
            ),
            [],
        )

        second = self.store.claim_telegram_notifications(
            now=observed_at + timedelta(seconds=10)
        )
        self.assertEqual(second[0]["attempts"], 2)
        self.assertTrue(
            self.store.complete_telegram_notification(
                "notification-1",
                now=observed_at + timedelta(seconds=11),
            )
        )
        with self.store.Session() as session:
            notification = session.get(
                TelegramNotification, "notification-1"
            )
            self.assertEqual(notification.status, "sent")
            self.assertEqual(notification.last_error_code, None)
            self.assertIsNotNone(notification.sent_at)

    def test_notification_outbox_skips_restricted_users(self):
        user_id = 222
        observed_at = datetime(2026, 8, 6, 12, 0, tzinfo=timezone.utc)
        self.store.ensure_user_id(user_id)
        with self.store.Session.begin() as session:
            session.add(
                TelegramNotification(
                    notification_id="notification-pending-user",
                    telegram_user_id=user_id,
                    kind="pilot_access_approved",
                    status="pending",
                    idempotency_key="pilot-access:222:test",
                    available_at=observed_at,
                    created_at=observed_at,
                    updated_at=observed_at,
                )
            )

        self.assertEqual(
            self.store.claim_telegram_notifications(now=observed_at), []
        )

    def test_programmatic_migrations_preserve_application_logging(self):
        root_logger = logging.getLogger()
        previous_level = root_logger.level
        sentinel = logging.NullHandler()
        root_logger.addHandler(sentinel)
        root_logger.setLevel(logging.INFO)
        secondary_store = None
        try:
            secondary_store = DatabaseStore(
                f"sqlite:///{Path(self.temp_dir.name) / 'logging.db'}"
            )
            self.assertIn(sentinel, root_logger.handlers)
            self.assertEqual(root_logger.level, logging.INFO)
        finally:
            if secondary_store is not None:
                secondary_store.close()
            root_logger.removeHandler(sentinel)
            root_logger.setLevel(previous_level)

    def test_role_promotion_never_downgrades_owner(self):
        user = SimpleNamespace(id=210, username="owner")
        self.store.ensure_user(user)
        self.assertEqual(self.store.product_profile(210)["role"], "learner")
        self.store.ensure_user(user, role="admin")
        self.store.ensure_user(user, role="learner")
        profile = self.store.product_profile(210)
        self.assertEqual(profile["role"], "admin")
        self.assertEqual(profile["access_status"], "active")

    def test_new_learners_are_pending_until_access_is_activated(self):
        self.assertIsNone(self.store.access_profile(219))
        self.store.ensure_user_id(219)
        self.assertEqual(
            self.store.access_profile(219)["access_status"], "pending"
        )
        self.store.activate_user_access(219)
        self.assertEqual(
            self.store.access_profile(219)["access_status"], "active"
        )

    def test_pilot_migration_preserves_every_existing_account(self):
        user_id = 220
        self.store.ensure_user_id(user_id)
        self.store.close()
        root = Path(__file__).resolve().parents[1]
        config = Config(str(root / "alembic.ini"))
        config.attributes["configure_logging"] = False
        config.set_main_option("script_location", str(root / "migrations"))
        config.set_main_option(
            "sqlalchemy.url", f"sqlite:///{self.database_path}"
        )
        command.downgrade(config, "0004_product_foundation")
        self.store = DatabaseStore(f"sqlite:///{self.database_path}")

        self.assertEqual(
            self.store.access_profile(user_id)["access_status"], "active"
        )

    def test_onboarding_pack_and_preferences_are_persisted(self):
        self.store.ensure_user_id(211)
        self.store.activate_pack(
            211,
            pack_id="ja-basics-100",
            language="ja",
            source="onboarding",
        )
        profile = self.store.update_product_profile(
            211,
            native_language="ru",
            learning_goal="travel",
            daily_word_goal=20,
            acquisition_source="telegram-ad",
            complete_onboarding=True,
        )
        self.assertEqual(profile["active_pack_id"], "ja-basics-100")
        self.assertEqual(profile["active_lang"], "ja")
        self.assertEqual(profile["daily_word_goal"], 20)
        self.assertIsNotNone(profile["onboarding_completed_at"])
        self.assertEqual(self.store.enrolled_pack_ids(211), {"ja-basics-100"})
        with self.store.Session() as session:
            enrollment = session.get(UserPackEnrollment, (211, "ja-basics-100"))
            self.assertTrue(enrollment.active)

    def test_analytics_accepts_dimensions_but_rejects_private_text(self):
        event_id = self.store.record_event(
            212,
            "block_started",
            properties={"pack_id": "ja-basics-100", "word_count": 10},
            session_id="session-1",
        )
        with self.store.Session() as session:
            event = session.get(AnalyticsEvent, event_id)
            self.assertEqual(
                event.properties_json,
                '{"pack_id":"ja-basics-100","word_count":10}',
            )
        with self.assertRaisesRegex(ValueError, "forbidden"):
            self.store.record_event(
                212,
                "ai_answered",
                properties={"prompt_text": "private learner content"},
            )

    def test_ac_02_ec_01_versioned_ai_consent_is_supported_and_replaced(self):
        self.assertTrue(
            self.store.grant_consent(
                213,
                consent_type="ai_processing",
                document_version="ai-processing-2026-08-09",
                source="telegram",
            )
        )
        self.assertTrue(
            self.store.has_consent(
                213,
                consent_type="ai_processing",
                document_version="ai-processing-2026-08-09",
            )
        )
        self.assertFalse(
            self.store.has_consent(
                213,
                consent_type="ai_processing",
                document_version="ai-processing-2026-09-01",
            )
        )
        self.assertEqual(
            self.store.revoke_consent(213, consent_type="ai_processing"), 1
        )

        with self.assertRaisesRegex(ValueError, "consent"):
            self.store.grant_consent(
                213,
                consent_type="unreviewed_processing",
                document_version="v1",
                source="telegram",
            )

    def test_ec_02_migration_round_trip_preserves_billing_and_voice_consents(self):
        self.store.close()
        root = Path(__file__).resolve().parents[1]
        config = Config(str(root / "alembic.ini"))
        config.attributes["configure_logging"] = False
        config.set_main_option("script_location", str(root / "migrations"))
        config.set_main_option(
            "sqlalchemy.url", f"sqlite:///{self.database_path}"
        )
        command.downgrade(config, "0012_ai_runtime_gates")
        legacy = DatabaseStore(f"sqlite:///{self.database_path}", migrate=False)
        try:
            for consent_type, version in (
                ("billing_terms", "billing-v1"),
                ("voice_processing", "voice-v1"),
            ):
                legacy.grant_consent(
                    214,
                    consent_type=consent_type,
                    document_version=version,
                    source="telegram",
                )
        finally:
            legacy.close()

        command.upgrade(config, "head")
        migrated = DatabaseStore(f"sqlite:///{self.database_path}", migrate=False)
        try:
            self.assertTrue(
                migrated.grant_consent(
                    214,
                    consent_type="ai_processing",
                    document_version="ai-processing-2026-08-09",
                    source="telegram",
                )
            )
            with migrated.Session.begin() as session:
                ai_row = session.execute(
                    select(UserConsent).where(
                        UserConsent.telegram_user_id == 214,
                        UserConsent.consent_type == "ai_processing",
                    )
                ).scalar_one()
                session.delete(ai_row)
            with migrated.Session() as session:
                before = {
                    (row.consent_type, row.document_version, row.revoked_at)
                    for row in session.execute(
                        select(UserConsent).where(
                            UserConsent.telegram_user_id == 214
                        )
                    ).scalars()
                }
        finally:
            migrated.close()

        command.downgrade(config, "0012_ai_runtime_gates")
        downgraded = DatabaseStore(f"sqlite:///{self.database_path}", migrate=False)
        self.store = downgraded
        with downgraded.Session() as session:
            after = {
                (row.consent_type, row.document_version, row.revoked_at)
                for row in session.execute(
                    select(UserConsent).where(UserConsent.telegram_user_id == 214)
                ).scalars()
            }
        self.assertEqual(after, before)

    def test_versioned_voice_consent_can_be_replaced_and_revoked(self):
        self.assertTrue(
            self.store.grant_consent(
                213,
                consent_type="voice_processing",
                document_version="voice-2026-08",
                source="telegram",
            )
        )
        self.assertFalse(
            self.store.grant_consent(
                213,
                consent_type="voice_processing",
                document_version="voice-2026-08",
                source="telegram",
            )
        )
        self.assertTrue(
            self.store.has_consent(
                213,
                consent_type="voice_processing",
                document_version="voice-2026-08",
            )
        )
        self.assertFalse(
            self.store.has_consent(
                213,
                consent_type="voice_processing",
                document_version="voice-2026-09",
            )
        )
        self.assertEqual(
            self.store.revoke_consent(213, consent_type="voice_processing"), 1
        )
        self.assertFalse(
            self.store.has_consent(
                213,
                consent_type="voice_processing",
                document_version="voice-2026-08",
            )
        )
        with self.store.Session() as session:
            rows = session.execute(select(UserConsent)).scalars().all()
            self.assertEqual(len(rows), 1)
            self.assertIsNotNone(rows[0].revoked_at)

    def test_card_analytics_accepts_privacy_safe_interaction_dimensions(self):
        event_id = self.store.record_event(
            213,
            "card_rated",
            properties={
                "pack_id": "ja-basics-100",
                "language": "ja",
                "lesson_kind": "daily",
                "mode": "flash",
                "position": 2,
                "rating": "known",
                "word_count": 5,
                "word_index": 10,
            },
            session_id="abc123",
            source="home",
        )
        with self.store.Session() as session:
            event = session.get(AnalyticsEvent, event_id)
            self.assertIn('"lesson_kind":"daily"', event.properties_json)
            self.assertIn('"rating":"known"', event.properties_json)
            self.assertNotIn("target", event.properties_json)

    def test_profiles_and_words_are_isolated_by_telegram_user(self):
        user_one = dict(PROFILE_DEFAULTS, active_lang="ja", xp=25, total_correct=1)
        word_one = {
            "en": "私",
            "ru": "я",
            "correct_count": 1,
            "wrong_count": 0,
            "last_seen": "2026-08-03T12:00:00",
            "interval": 1,
            "next_review": "2026-08-04T12:00:00",
        }
        self.store.save_learning_state(101, user_one, "ja", 10, word_one)
        self.store.ensure_user_id(202)

        loaded_one = self.store.load_profile(101, PROFILE_DEFAULTS)
        loaded_two = self.store.load_profile(202, PROFILE_DEFAULTS)
        self.assertEqual(loaded_one["xp"], 25)
        self.assertEqual(loaded_one["active_lang"], "ja")
        self.assertEqual(loaded_two, PROFILE_DEFAULTS)
        self.assertEqual(
            self.store.load_word_progress(101, "ja")[
                vocabulary_id_for(word_one)
            ]["correct_count"],
            1,
        )
        self.assertEqual(self.store.load_word_progress(202, "ja"), {})

    def test_legacy_import_is_idempotent(self):
        data_dir = Path(self.temp_dir.name) / "legacy"
        base_dir = Path(self.temp_dir.name) / "base"
        data_dir.mkdir()
        base_dir.mkdir()
        (data_dir / "progress.json").write_text(
            json.dumps(dict(PROFILE_DEFAULTS, xp=140, active_lang="ja")),
            encoding="utf-8",
        )
        legacy_words = [
            {
                "en": "私",
                "ru": "я",
                "correct_count": 3,
                "wrong_count": 1,
                "last_seen": "2026-08-02T10:00:00",
                "interval": 7,
                "next_review": "2026-08-09T10:00:00",
            }
        ]
        (data_dir / "words_ja.json").write_text(
            json.dumps(legacy_words), encoding="utf-8"
        )

        first = import_legacy_user(
            self.store,
            303,
            data_dir,
            base_dir,
            {"ja": "words_ja.json"},
            PROFILE_DEFAULTS,
        )
        (data_dir / "progress.json").write_text(
            json.dumps(dict(PROFILE_DEFAULTS, xp=999)), encoding="utf-8"
        )
        second = import_legacy_user(
            self.store,
            303,
            data_dir,
            base_dir,
            {"ja": "words_ja.json"},
            PROFILE_DEFAULTS,
        )

        self.assertTrue(first)
        self.assertFalse(second)
        self.assertEqual(self.store.load_profile(303, PROFILE_DEFAULTS)["xp"], 140)
        self.assertEqual(
            self.store.load_word_progress(303, "ja")[
                vocabulary_id_for(legacy_words[0])
            ]["correct_count"],
            3,
        )

    def test_legacy_import_accepts_words_without_progress_fields(self):
        data_dir = Path(self.temp_dir.name) / "legacy-minimal"
        base_dir = Path(self.temp_dir.name) / "base-minimal"
        data_dir.mkdir()
        base_dir.mkdir()
        (data_dir / "progress.json").write_text(
            json.dumps(dict(PROFILE_DEFAULTS, xp=5)), encoding="utf-8"
        )
        (data_dir / "words_ja.json").write_text(
            json.dumps([{"en": "私", "ru": "я"}]), encoding="utf-8"
        )

        imported = import_legacy_user(
            self.store,
            304,
            data_dir,
            base_dir,
            {"ja": "words_ja.json"},
            PROFILE_DEFAULTS,
        )

        self.assertTrue(imported)
        self.assertEqual(self.store.load_profile(304, PROFILE_DEFAULTS)["xp"], 5)
        self.assertEqual(self.store.load_word_progress(304, "ja"), {})

    def test_vocabulary_identity_distinguishes_duplicate_target_terms(self):
        first = {"en": "Extend", "ru": "расширять"}
        second = {"en": "Extend", "ru": "продлевать"}

        self.assertNotEqual(vocabulary_id_for(first), vocabulary_id_for(second))

    def test_stale_recovery_does_not_release_fresh_ai_reservation(self):
        request_id = self.store.reserve_ai_usage(
            305,
            action="block_tutor",
            provider="test",
            model="test-model",
            credits=1,
            initial_credits=2,
            context_fingerprint="d" * 64,
        )

        recovered = self.store.recover_stale_ai_usage(timeout_seconds=300)

        self.assertEqual(recovered, 0)
        self.assertEqual(self.store.get_ai_usage(request_id)["status"], "reserved")
        summary = self.store.ai_usage_summary(305)
        self.assertEqual(summary["available_credits"], 1)
        self.assertEqual(summary["reserved_credits"], 1)

    def test_credit_exhaustion_has_a_distinct_paywall_signal(self):
        exhausted = getattr(storage_module, "AICreditExhausted")

        with self.assertRaises(exhausted):
            self.store.reserve_ai_usage(
                399,
                action="block_tutor",
                provider="test",
                model="test-model",
                credits=1,
                initial_credits=0,
                context_fingerprint="e" * 64,
            )

    def test_zero_credit_reservation_is_rejected_for_a_learner(self):
        with self.assertRaisesRegex(ValueError, "admin"):
            self.store.reserve_ai_usage(
                398,
                action="block_tutor",
                provider="test",
                model="test-model",
                credits=0,
                initial_credits=40,
                context_fingerprint="z" * 64,
            )

    def test_project_budget_reservation_is_released_on_failure(self):
        request_id = self.store.reserve_ai_usage(
            306,
            action="block_tutor",
            provider="openai",
            model="test-model",
            credits=1,
            initial_credits=2,
            context_fingerprint="e" * 64,
            projected_cost_micro_usd=100,
            max_project_cost_micro_usd_per_day=1000,
            max_project_cost_micro_usd_per_month=2000,
            max_in_flight_cost_micro_usd=100,
        )
        self.assertEqual(
            self.store.ai_budget_status()["in_flight_micro_usd"], 100
        )
        with self.assertRaisesRegex(AIQuotaExceeded, "in-flight"):
            self.store.reserve_ai_usage(
                307,
                action="block_tutor",
                provider="openai",
                model="test-model",
                credits=1,
                initial_credits=2,
                context_fingerprint="f" * 64,
                projected_cost_micro_usd=1,
                max_project_cost_micro_usd_per_day=1000,
                max_project_cost_micro_usd_per_month=2000,
                max_in_flight_cost_micro_usd=100,
            )

        self.assertTrue(
            self.store.fail_ai_usage(request_id, error_code="known_failure")
        )
        self.assertEqual(
            self.store.ai_budget_status()["in_flight_micro_usd"], 0
        )

    def test_billable_failure_telemetry_survives_credit_refund(self):
        request_id = self.store.reserve_ai_usage(
            308,
            action="block_tutor",
            provider="openai",
            model="test-model",
            credits=1,
            initial_credits=2,
            context_fingerprint="a" * 64,
            requested_service_tier="default",
            economics_snapshot_id="snapshot-test",
            economics_snapshot_sha256="1" * 64,
            projected_cost_micro_usd=100,
            max_project_cost_micro_usd_per_day=1000,
            max_project_cost_micro_usd_per_month=2000,
            max_in_flight_cost_micro_usd=100,
        )
        self.store.mark_ai_provider_attempt_started(request_id)
        self.store.record_ai_provider_response(
            request_id,
            provider_response_id="response-invalid",
            model="test-model",
            service_tier="default",
            provider_status="incomplete",
            usage={"input_tokens": 10, "output_tokens": 3, "total_tokens": 13},
            cost_micro_usd=27,
            latency_ms=14,
            expected_model="test-model",
            expected_service_tier="default",
            retrospective_breaker_micro_usd=100,
        )
        self.assertTrue(
            self.store.fail_ai_usage(request_id, error_code="invalid_output")
        )

        usage = self.store.get_ai_usage(request_id)
        self.assertEqual(usage["status"], "failed")
        self.assertEqual(usage["provider_status"], "incomplete")
        self.assertEqual(usage["provider_response_id"], "response-invalid")
        self.assertEqual(usage["cost_micro_usd"], 27)
        self.assertFalse(usage["cost_is_estimate"])
        self.assertEqual(self.store.ai_usage_summary(308)["available_credits"], 2)

    def test_ai_tutor_settlement_cannot_overwrite_provider_telemetry(self):
        request_id = self.store.reserve_ai_usage(
            310,
            action="block_tutor",
            provider="openai",
            model="test-model",
            credits=1,
            initial_credits=2,
            context_fingerprint="c" * 64,
            requested_service_tier="default",
            economics_snapshot_id="snapshot-test",
            economics_snapshot_sha256="2" * 64,
            projected_cost_micro_usd=100,
            max_project_cost_micro_usd_per_day=1000,
            max_project_cost_micro_usd_per_month=2000,
            max_in_flight_cost_micro_usd=100,
        )
        self.store.mark_ai_provider_attempt_started(request_id)
        usage = {"input_tokens": 10, "output_tokens": 3, "total_tokens": 13}
        self.store.record_ai_provider_response(
            request_id,
            provider_response_id="response-original",
            model="test-model",
            service_tier="default",
            provider_status="completed",
            usage=usage,
            cost_micro_usd=27,
            latency_ms=14,
            expected_model="test-model",
            expected_service_tier="default",
            retrospective_breaker_micro_usd=100,
        )

        with self.assertRaisesRegex(AIUsageStateError, "cannot alter"):
            self.store.complete_ai_usage(
                request_id,
                billed_credits=1,
                provider_response_id="response-original",
                model="test-model",
                usage={**usage, "output_tokens": 4},
                cost_micro_usd=28,
                latency_ms=14,
                returned_service_tier="default",
                provider_status="completed",
            )

        stored = self.store.get_ai_usage(request_id)
        self.assertEqual(stored["status"], "reserved")
        self.assertEqual(stored["output_tokens"], 3)
        self.assertEqual(stored["cost_micro_usd"], 27)
        self.assertTrue(
            self.store.fail_ai_usage(request_id, error_code="test_cleanup")
        )

    def test_breaker_reset_is_visible_and_audited(self):
        self.store.open_ai_breaker(reason="returned_model_mismatch")
        status = self.store.ai_budget_status()
        self.assertTrue(status["breaker_open"])
        self.assertEqual(status["breaker_reason"], "returned_model_mismatch")

        self.assertTrue(
            self.store.reset_ai_breaker(
                actor="owner",
                reason="verified dashboard and provider telemetry",
            )
        )
        status = self.store.ai_budget_status()
        self.assertFalse(status["breaker_open"])
        self.assertEqual(status["breaker_acknowledged_by"], "owner")
        with self.store.Session() as session:
            audit = session.execute(
                select(AdminAuditLog).where(
                    AdminAuditLog.action == "ai_breaker_reset"
                )
            ).scalar_one()
        self.assertIn("returned_model_mismatch", audit.details_json)

    def test_breaker_cannot_reset_with_in_flight_request(self):
        request_id = self.store.reserve_ai_usage(
            310,
            action="block_tutor",
            provider="openai",
            model="test-model",
            credits=1,
            initial_credits=1,
            context_fingerprint="c" * 64,
            projected_cost_micro_usd=100,
            max_project_cost_micro_usd_per_day=1000,
            max_project_cost_micro_usd_per_month=2000,
            max_in_flight_cost_micro_usd=100,
        )
        self.store.open_ai_breaker(reason="operator_hold")

        with self.assertRaisesRegex(RuntimeError, "in flight"):
            self.store.reset_ai_breaker(
                actor="owner",
                reason="must wait for active request",
            )

        self.store.fail_ai_usage(request_id, error_code="test_cleanup")
        self.assertTrue(
            self.store.reset_ai_breaker(
                actor="owner",
                reason="active request released",
            )
        )

    def test_fallback_journal_reconciliation_is_private_and_audited(self):
        request_id = self.store.reserve_ai_usage(
            309,
            action="block_tutor",
            provider="openai",
            model="test-model",
            credits=1,
            initial_credits=2,
            context_fingerprint="b" * 64,
            projected_cost_micro_usd=100,
            max_project_cost_micro_usd_per_day=1000,
            max_project_cost_micro_usd_per_month=2000,
            max_in_flight_cost_micro_usd=100,
        )
        self.store.mark_ai_provider_attempt_started(request_id)
        self.store.fail_ai_usage(
            request_id,
            error_code="provider_telemetry_storage_failure",
            open_breaker_reason="provider_telemetry_storage_failure",
        )
        journal_path = Path(self.temp_dir.name) / "metering.jsonl"
        journal = AIMeteringJournal(journal_path)
        journal.append(
            {
                "request_id": request_id,
                "provider_response_id": "response-recovered",
                "model": "test-model",
                "service_tier": "default",
                "provider_status": "completed",
                "input_tokens": 10,
                "output_tokens": 3,
                "total_tokens": 13,
                "cost_micro_usd": 27,
                "latency_ms": 14,
                "error_code": "provider_telemetry_storage_failure",
            }
        )
        self.assertEqual(stat.S_IMODE(journal_path.stat().st_mode), 0o600)

        def reject_record(record):
            raise RuntimeError("review failed")

        with self.assertRaisesRegex(RuntimeError, "review failed"):
            journal.reconcile(reject_record)
        self.assertEqual(journal.pending_count(), 1)

        processed = journal.reconcile(
            lambda record: self.store.reconcile_ai_provider_response(
                record,
                actor="owner",
            )
        )

        self.assertEqual(processed, 1)
        self.assertEqual(journal.pending_count(), 0)
        usage = self.store.get_ai_usage(request_id)
        self.assertTrue(usage["provider_response_received"])
        self.assertFalse(usage["cost_is_estimate"])
        self.assertEqual(usage["cost_micro_usd"], 27)
        self.assertTrue(self.store.ai_budget_status()["breaker_open"])
        with self.store.Session() as session:
            audit = session.execute(
                select(AdminAuditLog).where(
                    AdminAuditLog.action == "ai_metering_reconciled"
                )
            ).scalar_one()
        self.assertEqual(audit.target_id, request_id)


class BotRuntimeIsolationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.setdefault("BOT_TOKEN", "123456:TESTTOKEN")
        os.environ.setdefault("ALLOWED_USER_ID", "1")
        import bot

        cls.bot = bot

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory(prefix="mydictionary-runtime-")
        path = Path(self.temp_dir.name) / "runtime.db"
        self.store = DatabaseStore(f"sqlite:///{path}")

    def tearDown(self):
        self.store.close()
        self.temp_dir.cleanup()

    def test_runtime_progress_is_isolated_and_content_is_not_rewritten(self):
        dictionary_path = Path(self.bot.__file__).parent / "words_ja.json"
        original_content = dictionary_path.read_bytes()
        user_one = SimpleNamespace(id=1001)
        user_two = SimpleNamespace(id=1002)

        with (
            patch.object(self.bot, "_STORE", self.store),
            patch.object(self.bot, "LEGACY_USER_ID", None),
        ):
            with self.bot.learner_scope(user_one):
                self.bot.PROGRESS["active_lang"] = "ja"
                self.bot.mark_correct(10)
                self.assertEqual(self.bot.W()[10]["correct_count"], 1)

            with self.bot.learner_scope(user_two):
                self.assertEqual(self.bot.PROGRESS["active_lang"], "en")
                self.assertEqual(self.bot.W("ja")[10]["correct_count"], 0)

            with self.bot.learner_scope(user_one):
                self.assertEqual(self.bot.PROGRESS["active_lang"], "ja")
                self.assertEqual(self.bot.W()[10]["correct_count"], 1)
                self.assertGreater(self.bot.PROGRESS["xp"], 0)

        self.assertEqual(dictionary_path.read_bytes(), original_content)

    def test_configured_admin_keeps_legacy_english_pack_and_progress(self):
        user_id = 1000
        self.store.save_profile(
            user_id, dict(PROFILE_DEFAULTS, active_lang="en", xp=140)
        )
        with (
            patch.object(self.bot, "_STORE", self.store),
            patch.object(self.bot, "LEGACY_USER_ID", None),
            patch.object(self.bot, "ADMIN_USER_IDS", {user_id}),
            self.bot.learner_scope(SimpleNamespace(id=user_id)) as runtime,
        ):
            self.assertEqual(runtime.role, "admin")
            self.assertTrue(runtime.onboarding_completed)
            self.assertEqual(
                self.bot.PROGRESS["active_pack_id"], "pirajoke-en-personal"
            )
            self.assertEqual(self.bot.PROGRESS["xp"], 140)
            self.assertEqual(len(self.bot.W()), 661)

    def test_new_users_do_not_inherit_progress_from_dictionary_json(self):
        with (
            patch.object(self.bot, "_STORE", self.store),
            patch.object(self.bot, "LEGACY_USER_ID", None),
            self.bot.learner_scope(SimpleNamespace(id=1003)),
        ):
            with self.assertRaises(PermissionError):
                self.bot.W("pirajoke-en-personal")
            for pack in self.bot.CATALOG.visible_packs("learner"):
                for word in self.bot.W(pack.pack_id):
                    with self.subTest(
                        pack=pack.pack_id, term=target_text(word)
                    ):
                        self.assertEqual(word["correct_count"], 0)
                        self.assertEqual(word["wrong_count"], 0)
                        self.assertIsNone(word["last_seen"])
                        self.assertEqual(word["interval"], 1)
                        self.assertIsNone(word["next_review"])

    def test_word_progress_follows_vocabulary_when_dictionary_is_reordered(self):
        user = SimpleNamespace(id=1004)
        original_words = self.bot.PACK_DICTS["ja-basics-100"]
        learned_term = target_text(original_words[0])

        with (
            patch.object(self.bot, "_STORE", self.store),
            patch.object(self.bot, "LEGACY_USER_ID", None),
            self.bot.learner_scope(user),
        ):
            self.bot.PROGRESS["active_lang"] = "ja"
            self.bot.mark_correct(0)

        reordered = [original_words[1], original_words[0], *original_words[2:]]
        with (
            patch.object(self.bot, "_STORE", self.store),
            patch.object(self.bot, "LEGACY_USER_ID", None),
            patch.dict(self.bot.PACK_DICTS, {"ja-basics-100": reordered}),
            self.bot.learner_scope(user),
        ):
            self.assertEqual(
                target_text(self.bot.W("ja")[1]), learned_term
            )
            self.assertEqual(self.bot.W("ja")[1]["correct_count"], 1)
            self.assertEqual(self.bot.W("ja")[0]["correct_count"], 0)

    def test_access_mode_is_fail_closed_and_validated(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(self.bot._configured_access_mode(), "allowlist")
        with patch.dict(os.environ, {"BOT_ACCESS_MODE": "public"}, clear=True):
            self.assertEqual(self.bot._configured_access_mode(), "public")
        with patch.dict(os.environ, {"BOT_ACCESS_MODE": "pilot"}, clear=True):
            self.assertEqual(self.bot._configured_access_mode(), "pilot")
        with patch.dict(os.environ, {"BOT_ACCESS_MODE": "typo"}, clear=True):
            with self.assertRaises(RuntimeError):
                self.bot._configured_access_mode()

    def test_access_decision_matrix_blocks_before_public_admission(self):
        decide = self.bot.access_decision
        self.assertEqual(
            decide(
                mode="pilot",
                configured=False,
                stored_role=None,
                stored_status=None,
                is_start=True,
            ),
            "waitlist",
        )
        self.assertEqual(
            decide(
                mode="pilot",
                configured=False,
                stored_role="learner",
                stored_status="active",
                is_start=False,
            ),
            "allow",
        )
        self.assertEqual(
            decide(
                mode="public",
                configured=True,
                stored_role="learner",
                stored_status="blocked",
                is_start=True,
            ),
            "blocked",
        )
        self.assertEqual(
            decide(
                mode="allowlist",
                configured=False,
                stored_role="admin",
                stored_status="active",
                is_start=False,
            ),
            "allow",
        )

    def test_database_url_requires_explicit_sqlite_development_opt_in(self):
        with (
            patch.dict(os.environ, {}, clear=True),
            patch.object(self.bot, "DATA_DIR", Path(self.temp_dir.name)),
        ):
            with self.assertRaises(RuntimeError):
                self.bot.database_url()

        with (
            patch.dict(
                os.environ, {"ALLOW_SQLITE_DEV": "true"}, clear=True
            ),
            patch.object(self.bot, "DATA_DIR", Path(self.temp_dir.name)),
        ):
            self.assertTrue(self.bot.database_url().startswith("sqlite:///"))


@unittest.skipUnless(os.environ.get("TEST_POSTGRES_URL"), "PostgreSQL URL not set")
class PostgresStoreTest(unittest.TestCase):
    def test_concurrent_first_reservations_do_not_double_grant(self):
        store = DatabaseStore(os.environ["TEST_POSTGRES_URL"])
        user_id = 1_000_000 + (uuid4().int % 1_000_000_000)
        store.ensure_user_id(user_id)
        barrier = Barrier(2)

        def reserve():
            barrier.wait()
            try:
                return store.reserve_ai_usage(
                    user_id,
                    action="block_tutor",
                    provider="test",
                    model="test-model",
                    credits=1,
                    initial_credits=1,
                    context_fingerprint="b" * 64,
                )
            except AIQuotaExceeded:
                return None

        try:
            with ThreadPoolExecutor(max_workers=2) as executor:
                request_ids = list(executor.map(lambda _: reserve(), range(2)))

            self.assertEqual(sum(item is not None for item in request_ids), 1)
            summary = store.ai_usage_summary(user_id)
            self.assertEqual(summary["available_credits"], 0)
            self.assertEqual(summary["reserved_credits"], 1)
        finally:
            store.close()

    def test_concurrent_users_cannot_oversubscribe_in_flight_budget(self):
        store = DatabaseStore(os.environ["TEST_POSTGRES_URL"])
        user_ids = [
            1_000_000 + (uuid4().int % 1_000_000_000)
            for _ in range(2)
        ]
        for user_id in user_ids:
            store.ensure_user_id(user_id)
        current = store.ai_budget_status()["in_flight_micro_usd"]
        projected = 4000
        barrier = Barrier(2)

        def reserve(user_id):
            barrier.wait()
            try:
                return store.reserve_ai_usage(
                    user_id,
                    action="block_tutor",
                    provider="openai",
                    model="test-model",
                    credits=1,
                    initial_credits=1,
                    context_fingerprint="c" * 64,
                    projected_cost_micro_usd=projected,
                    max_project_cost_micro_usd_per_day=100_000_000,
                    max_project_cost_micro_usd_per_month=1_000_000_000,
                    max_in_flight_cost_micro_usd=current + projected,
                )
            except AIQuotaExceeded:
                return None

        try:
            with ThreadPoolExecutor(max_workers=2) as executor:
                request_ids = list(executor.map(reserve, user_ids))

            accepted = [request_id for request_id in request_ids if request_id]
            self.assertEqual(len(accepted), 1)
            self.assertEqual(
                store.ai_budget_status()["in_flight_micro_usd"],
                current + projected,
            )
            self.assertTrue(
                store.fail_ai_usage(accepted[0], error_code="test_cleanup")
            )
            self.assertEqual(
                store.ai_budget_status()["in_flight_micro_usd"], current
            )
        finally:
            store.close()

    def test_migrations_and_isolated_round_trip(self):
        store = DatabaseStore(os.environ["TEST_POSTGRES_URL"])
        try:
            profile = dict(PROFILE_DEFAULTS, xp=55, active_lang="vi")
            word = {
                "en": "xin chào",
                "ru": "привет",
                "correct_count": 2,
                "wrong_count": 0,
                "last_seen": "2026-08-03T12:00:00",
                "interval": 3,
                "next_review": "2026-08-06T12:00:00",
            }
            store.save_learning_state(900001, profile, "vi", 0, word)
            self.assertEqual(store.load_profile(900001, PROFILE_DEFAULTS)["xp"], 55)
            self.assertEqual(
                store.load_word_progress(900001, "vi")[
                    vocabulary_id_for(word)
                ]["correct_count"],
                2,
            )
            request_id = store.reserve_ai_usage(
                900001,
                action="block_tutor",
                provider="test",
                model="test-model",
                credits=1,
                initial_credits=2,
                context_fingerprint="a" * 64,
            )
            store.mark_ai_provider_attempt_started(request_id)
            store.record_ai_provider_response(
                request_id,
                provider_response_id="response-1",
                model="test-model",
                service_tier="default",
                provider_status="completed",
                usage={"input_tokens": 5, "output_tokens": 3, "total_tokens": 8},
                cost_micro_usd=7,
                latency_ms=10,
                expected_model="test-model",
                expected_service_tier="default",
                retrospective_breaker_micro_usd=100,
            )
            store.complete_ai_usage(
                request_id,
                billed_credits=1,
                provider_response_id="response-1",
                model="test-model",
                usage={"input_tokens": 5, "output_tokens": 3, "total_tokens": 8},
                cost_micro_usd=7,
                latency_ms=10,
            )
            summary = store.ai_usage_summary(900001)
            self.assertEqual(summary["available_credits"], 1)
            self.assertEqual(summary["total_tokens"], 8)

            stale_request_id = store.reserve_ai_usage(
                900001,
                action="block_tutor",
                provider="test",
                model="test-model",
                credits=1,
                initial_credits=2,
                context_fingerprint="e" * 64,
            )
            with store.Session.begin() as session:
                stale_row = session.get(AIUsage, stale_request_id)
                stale_row.created_at = datetime.now(timezone.utc) - timedelta(
                    seconds=600
                )
            self.assertEqual(
                store.recover_stale_ai_usage(
                    timeout_seconds=300, user_id=900001
                ),
                1,
            )
            recovered = store.ai_usage_summary(900001)
            self.assertEqual(recovered["available_credits"], 1)
            self.assertEqual(recovered["reserved_credits"], 0)
            self.assertEqual(recovered["failed_requests"], 1)
            with store.Session() as session:
                initial_grants = session.execute(
                    select(BillingCreditLedger).where(
                        BillingCreditLedger.telegram_user_id == 900001,
                        BillingCreditLedger.entry_type == "initial_grant",
                    )
                ).scalars().all()
            self.assertEqual(len(initial_grants), 1)
        finally:
            store.close()


if __name__ == "__main__":
    unittest.main()
