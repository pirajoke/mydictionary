import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, func, select, text

from mydictionary.admin_store import AdminStore
from mydictionary.billing import (
    BillingConfigurationError,
    BillingService,
    BillingSettings,
    BillingStateError,
    BillingValidationError,
)
from mydictionary.storage import (
    AIWallet,
    BillingCreditLedger,
    DatabaseStore,
    RefundRequest,
    StarsPayment,
)


def enabled_settings() -> BillingSettings:
    return BillingSettings(
        enabled=True,
        payload_secret="billing-test-secret-with-more-than-32-characters",
        support_contact="@mydictionary_support",
        terms_text="Test terms",
        order_ttl_seconds=1800,
        net_micro_usd_per_xtr=1000,
    )


class BillingServiceTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory(prefix="mydictionary-billing-")
        database_path = Path(self.temp_dir.name) / "billing.db"
        self.store = DatabaseStore(f"sqlite:///{database_path}")
        self.store.ensure_user_id(7001)
        self.settings = enabled_settings()
        self.service = BillingService(self.store, self.settings)
        self.admin = AdminStore(self.store, self.settings)
        self.admin.upsert_billing_product(
            product_id="ai-starter",
            title="AI Starter",
            description="50 AI credits",
            credits=50,
            price_xtr=100,
            status="active",
            estimated_cost_micro_usd=20_000,
            target_margin_bps=5000,
            display_order=10,
            actor="test",
        )

    def tearDown(self):
        self.store.close()
        self.temp_dir.cleanup()

    def test_defaults_are_disabled_and_enabled_configuration_fails_closed(self):
        settings = BillingSettings.from_env({})
        self.assertFalse(settings.enabled)
        self.assertEqual(settings.net_micro_usd_per_xtr, 0)
        with self.assertRaises(BillingConfigurationError):
            BillingSettings.from_env({"TELEGRAM_STARS_ENABLED": "true"})
        enabled = BillingSettings.from_env(
            {
                "TELEGRAM_STARS_ENABLED": "true",
                "BILLING_PAYLOAD_SECRET": "s" * 40,
                "BILLING_SUPPORT_CONTACT": "@support",
                "BILLING_TERMS_TEXT": "Explicit test terms",
                "BILLING_NET_MICRO_USD_PER_XTR": "1000",
            }
        )
        self.assertTrue(enabled.enabled)

    def test_migration_preserves_legacy_allowance_and_admin_ledger(self):
        legacy_path = Path(self.temp_dir.name) / "legacy.db"
        legacy_url = f"sqlite:///{legacy_path}"
        root = Path(__file__).resolve().parents[1]
        config = Config(str(root / "alembic.ini"))
        config.attributes["configure_logging"] = False
        config.set_main_option("script_location", str(root / "migrations"))
        config.set_main_option("sqlalchemy.url", legacy_url)
        command.upgrade(config, "0005_pilot_access")
        engine = create_engine(legacy_url)
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO users "
                    "(telegram_user_id, role, daily_word_goal, access_status, "
                    "created_at, updated_at) VALUES "
                    "(8001, 'learner', 10, 'active', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
                )
            )
            connection.execute(
                text(
                    "INSERT INTO ai_allowances "
                    "(telegram_user_id, available_credits, reserved_credits, "
                    "spent_credits, updated_at) VALUES "
                    "(8001, 5, 3, 2, CURRENT_TIMESTAMP)"
                )
            )
            connection.execute(
                text(
                    "INSERT INTO ai_credit_ledger "
                    "(entry_id, telegram_user_id, delta, balance_after, reason, "
                    "actor, created_at) VALUES "
                    "('legacy-entry', 8001, 5, 5, 'legacy grant', 'owner', "
                    "CURRENT_TIMESTAMP)"
                )
            )
        engine.dispose()

        command.upgrade(config, "head")
        migrated = DatabaseStore(legacy_url, migrate=False)
        try:
            with migrated.Session() as session:
                wallet = session.get(AIWallet, 8001)
                ledger = session.execute(
                    select(BillingCreditLedger).where(
                        BillingCreditLedger.idempotency_key
                        == "legacy:legacy-entry"
                    )
                ).scalar_one()
                self.assertEqual(wallet.balance_credits, 8)
                self.assertEqual(wallet.reserved_credits, 3)
                self.assertEqual(wallet.spent_credits, 2)
                self.assertEqual(ledger.entry_type, "legacy_admin_adjustment")
        finally:
            migrated.close()

    def test_product_activation_enforces_configured_margin_floor(self):
        with self.assertRaisesRegex(ValueError, "below"):
            self.admin.upsert_billing_product(
                product_id="ai-loss",
                title="AI Loss",
                description="Unsafe margin",
                credits=100,
                price_xtr=10,
                status="active",
                estimated_cost_micro_usd=9_000,
                target_margin_bps=5000,
                display_order=20,
                actor="test",
            )

    def test_payment_is_validated_and_fulfilled_exactly_once(self):
        order = self.service.create_order(user_id=7001, product_id="ai-starter")
        with self.assertRaises(BillingValidationError):
            self.service.validate_pre_checkout(
                user_id=7002,
                payload=order.payload,
                currency="XTR",
                total_amount=100,
            )
        with self.assertRaises(BillingValidationError):
            self.service.validate_pre_checkout(
                user_id=7001,
                payload=order.payload + "x",
                currency="XTR",
                total_amount=100,
            )
        with self.assertRaises(BillingValidationError):
            self.service.validate_pre_checkout(
                user_id=7001,
                payload=order.payload,
                currency="XTR",
                total_amount=101,
            )

        self.service.validate_pre_checkout(
            user_id=7001,
            payload=order.payload,
            currency="XTR",
            total_amount=100,
        )
        first = self.service.fulfill_successful_payment(
            user_id=7001,
            payload=order.payload,
            currency="XTR",
            total_amount=100,
            telegram_payment_charge_id="charge-1",
        )
        second = self.service.fulfill_successful_payment(
            user_id=7001,
            payload=order.payload,
            currency="XTR",
            total_amount=100,
            telegram_payment_charge_id="charge-1",
        )

        self.assertTrue(first.created)
        self.assertFalse(second.created)
        self.assertEqual(first.available_credits, 50)
        self.assertEqual(second.available_credits, 50)
        with self.store.Session() as session:
            wallet = session.get(AIWallet, 7001)
            self.assertEqual(wallet.balance_credits, 50)
            self.assertEqual(session.scalar(select(func.count(StarsPayment.payment_id))), 1)
            grants = session.execute(
                select(BillingCreditLedger).where(
                    BillingCreditLedger.entry_type == "stars_purchase"
                )
            ).scalars().all()
            self.assertEqual(len(grants), 1)

    def test_paid_order_is_fulfilled_after_checkout_flag_is_disabled(self):
        order = self.service.create_order(user_id=7001, product_id="ai-starter")
        disabled = BillingService(
            self.store,
            BillingSettings(
                enabled=False,
                payload_secret=self.settings.payload_secret,
                support_contact="",
                terms_text="Test terms",
                net_micro_usd_per_xtr=0,
            ),
        )
        result = disabled.fulfill_successful_payment(
            user_id=7001,
            payload=order.payload,
            currency="XTR",
            total_amount=100,
            telegram_payment_charge_id="charge-after-disable",
        )
        self.assertTrue(result.created)
        self.assertEqual(result.available_credits, 50)

    async def test_refund_holds_credits_and_uses_only_injected_gateway(self):
        order = self.service.create_order(user_id=7001, product_id="ai-starter")
        payment = self.service.fulfill_successful_payment(
            user_id=7001,
            payload=order.payload,
            currency="XTR",
            total_amount=100,
            telegram_payment_charge_id="charge-refund",
        )
        refund_id = self.service.request_refund(
            payment_id=payment.payment_id,
            reason="customer request",
            actor="owner",
        )
        with self.store.Session() as session:
            wallet = session.get(AIWallet, 7001)
            self.assertEqual(wallet.balance_credits, 50)
            self.assertEqual(wallet.reserved_credits, 50)

        gateway = AsyncMock()
        gateway.refund_star_payment.return_value = True
        self.assertTrue(
            await self.service.process_refund(refund_id=refund_id, gateway=gateway)
        )
        gateway.refund_star_payment.assert_awaited_once_with(
            user_id=7001, telegram_payment_charge_id="charge-refund"
        )
        self.assertTrue(
            await self.service.process_refund(refund_id=refund_id, gateway=gateway)
        )
        gateway.refund_star_payment.assert_awaited_once()
        with self.store.Session() as session:
            wallet = session.get(AIWallet, 7001)
            refund = session.get(RefundRequest, refund_id)
            payment_row = session.get(StarsPayment, payment.payment_id)
            self.assertEqual(wallet.balance_credits, 0)
            self.assertEqual(wallet.reserved_credits, 0)
            self.assertEqual(refund.status, "completed")
            self.assertEqual(payment_row.status, "refunded")

    async def test_failed_refund_keeps_hold_for_reconciliation(self):
        order = self.service.create_order(user_id=7001, product_id="ai-starter")
        payment = self.service.fulfill_successful_payment(
            user_id=7001,
            payload=order.payload,
            currency="XTR",
            total_amount=100,
            telegram_payment_charge_id="charge-refund-failed",
        )
        refund_id = self.service.request_refund(
            payment_id=payment.payment_id,
            reason="customer request",
            actor="owner",
        )
        gateway = AsyncMock()
        gateway.refund_star_payment.side_effect = TimeoutError()
        self.assertFalse(
            await self.service.process_refund(refund_id=refund_id, gateway=gateway)
        )
        with self.store.Session() as session:
            wallet = session.get(AIWallet, 7001)
            refund = session.get(RefundRequest, refund_id)
            self.assertEqual(wallet.reserved_credits, 50)
            self.assertEqual(refund.status, "failed")

    def test_duplicate_charge_cannot_fulfill_another_order(self):
        first = self.service.create_order(user_id=7001, product_id="ai-starter")
        second = self.service.create_order(user_id=7001, product_id="ai-starter")
        self.service.fulfill_successful_payment(
            user_id=7001,
            payload=first.payload,
            currency="XTR",
            total_amount=100,
            telegram_payment_charge_id="same-charge",
        )
        with self.assertRaises(BillingStateError):
            self.service.fulfill_successful_payment(
                user_id=7001,
                payload=second.payload,
                currency="XTR",
                total_amount=100,
                telegram_payment_charge_id="same-charge",
            )

    def test_reconciliation_detects_unknown_and_mismatched_remote_rows(self):
        order = self.service.create_order(user_id=7001, product_id="ai-starter")
        self.service.fulfill_successful_payment(
            user_id=7001,
            payload=order.payload,
            currency="XTR",
            total_amount=100,
            telegram_payment_charge_id="charge-reconcile",
        )
        issues = self.service.reconcile_transactions(
            [
                {
                    "telegram_payment_charge_id": "charge-reconcile",
                    "user_id": 7001,
                    "currency": "XTR",
                    "total_amount": 101,
                },
                {
                    "telegram_payment_charge_id": "remote-only",
                    "user_id": 7001,
                    "currency": "XTR",
                    "total_amount": 100,
                },
            ]
        )
        self.assertEqual(
            {issue.code for issue in issues},
            {"remote_payment_mismatch", "remote_payment_missing_locally"},
        )


if __name__ == "__main__":
    unittest.main()
