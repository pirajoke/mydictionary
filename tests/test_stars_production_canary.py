import asyncio
import hashlib
import json
import os
import tempfile
import threading
import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, call, patch

from sqlalchemy import func, select


os.environ.setdefault("BOT_TOKEN", "123456:TESTTOKEN")
os.environ.setdefault("ALLOWED_USER_ID", "1")
os.environ.setdefault("ALLOW_SQLITE_DEV", "true")

import bot
import mydictionary.billing as billing
import mydictionary.stars_launch as stars_launch
from mydictionary.admin_store import AdminStore
from mydictionary.billing import (
    BillingConfigurationError,
    BillingSettings,
    BillingStateError,
    BillingValidationError,
    FulfillmentResult,
    InvoiceOrder,
    StarTransactionPage,
)
from mydictionary.storage import (
    AIWallet,
    AppSetting,
    BillingCreditLedger,
    DatabaseStore,
    PaymentOrder,
    RefundRequest,
    StarsPayment,
)


OWNER_ID = 7001
NON_OWNER_ID = 7002
PRODUCT_ID = "ai-mini"
CANARY_AMOUNT_XTR = 10
CATALOG_AMOUNT_XTR = 69
CREDITS = 20
TERMS_VERSION = "stars-production-canary-v1"
TERMS_TEXT = "Owner-only production canary terms for immediate digital delivery."
PRIVATE_CHARGE = "PRIVATE-CANARY-CHARGE-ID"
LEGACY_CANARY_MARKER_KEY = "telegram_stars_production_canary_v1"


def required_public(testcase, owner, name):
    owner_name = getattr(owner, "__name__", owner.__class__.__name__)
    testcase.assertTrue(
        hasattr(owner, name),
        f"missing production Stars canary behavior: {owner_name}.{name}",
    )
    return getattr(owner, name)


def canary_environment(**overrides):
    values = {
        "TELEGRAM_STARS_ENABLED": "false",
        "STARS_PRODUCTION_CANARY_ENABLED": "true",
        "STARS_PRODUCTION_CANARY_OWNER_ID": str(OWNER_ID),
        "STARS_PRODUCTION_CANARY_PRODUCT_ID": PRODUCT_ID,
        "STARS_PRODUCTION_CANARY_AMOUNT_XTR": str(CANARY_AMOUNT_XTR),
    }
    values.update(overrides)
    return values


def handler_canary_settings():
    return SimpleNamespace(
        enabled=True,
        owner_user_id=OWNER_ID,
        product_id=PRODUCT_ID,
        amount_xtr=CANARY_AMOUNT_XTR,
        public_checkout_enabled=False,
        is_owner=lambda user_id: int(user_id) == OWNER_ID,
        allows_user=lambda user_id: int(user_id) == OWNER_ID,
    )


def disabled_billing_settings():
    return SimpleNamespace(
        enabled=False,
        terms_version=TERMS_VERSION,
        terms_text=TERMS_TEXT,
        support_contact="@canary_support",
        seller_legal_name="Canary Seller SAS",
        seller_address="1 Canary Street, Paris",
        seller_email="billing@example.test",
        seller_phone="+33102030405",
    )


def message_update(user_id, text="/buy"):
    message = SimpleNamespace(text=text, reply_text=AsyncMock())
    update = SimpleNamespace(
        message=message,
        effective_message=message,
        effective_user=SimpleNamespace(
            id=user_id,
            language_code="en",
            first_name=None,
        ),
        effective_chat=SimpleNamespace(id=user_id),
    )
    return update, message


def callback_update(user_id, data):
    message = SimpleNamespace(chat_id=user_id, reply_text=AsyncMock())
    query = SimpleNamespace(
        data=data,
        answer=AsyncMock(),
        edit_message_reply_markup=AsyncMock(),
        message=message,
    )
    update = SimpleNamespace(
        callback_query=query,
        effective_message=message,
        effective_user=SimpleNamespace(
            id=user_id,
            language_code="en",
            first_name=None,
        ),
        effective_chat=SimpleNamespace(id=user_id),
    )
    return update, query


def successful_payment_update(
    user_id,
    payload,
    charge_id,
    *,
    total_amount=CANARY_AMOUNT_XTR,
):
    payment = SimpleNamespace(
        invoice_payload=payload,
        currency="XTR",
        total_amount=total_amount,
        telegram_payment_charge_id=charge_id,
        provider_payment_charge_id="",
        is_recurring=False,
        is_first_recurring=False,
        subscription_expiration_date=None,
    )
    message = SimpleNamespace(
        successful_payment=payment,
        reply_text=AsyncMock(),
    )
    update = SimpleNamespace(
        message=message,
        effective_message=message,
        effective_user=SimpleNamespace(id=user_id, language_code="en"),
    )
    return update, message


def remote_canary_row(*, refunded=False):
    return {
        "telegram_payment_charge_id": PRIVATE_CHARGE,
        "user_id": OWNER_ID,
        "currency": "XTR",
        "total_amount": CANARY_AMOUNT_XTR,
        "is_refund": bool(refunded),
        "subscription_period": None,
    }


class ProductionStarsCanarySettingsContractTest(unittest.TestCase):
    def test_ac_1_ac_2_public_checkout_off_and_exact_owner_canary_config(self):
        settings_type = required_public(
            self, billing, "ProductionStarsCanarySettings"
        )

        settings = settings_type.from_env(canary_environment())

        self.assertTrue(settings.enabled)
        self.assertFalse(settings.public_checkout_enabled)
        self.assertEqual(settings.owner_user_id, OWNER_ID)
        self.assertEqual(settings.product_id, PRODUCT_ID)
        self.assertEqual(settings.amount_xtr, CANARY_AMOUNT_XTR)
        self.assertTrue(settings.is_owner(OWNER_ID))
        self.assertFalse(settings.is_owner(NON_OWNER_ID))
        self.assertFalse(BillingSettings.from_env({}).enabled)

    def test_ac_2_missing_multiple_or_non_exact_canary_config_fails_closed(self):
        settings_type = required_public(
            self, billing, "ProductionStarsCanarySettings"
        )
        invalid = (
            {"STARS_PRODUCTION_CANARY_OWNER_ID": ""},
            {"STARS_PRODUCTION_CANARY_OWNER_ID": "0"},
            {"STARS_PRODUCTION_CANARY_OWNER_ID": "-1"},
            {"STARS_PRODUCTION_CANARY_OWNER_ID": "owner"},
            {"STARS_PRODUCTION_CANARY_OWNER_ID": f"{OWNER_ID},{NON_OWNER_ID}"},
            {"STARS_PRODUCTION_CANARY_PRODUCT_ID": "ai-starter"},
            {"STARS_PRODUCTION_CANARY_AMOUNT_XTR": "9"},
            {"STARS_PRODUCTION_CANARY_AMOUNT_XTR": "11"},
            {"STARS_PRODUCTION_CANARY_AMOUNT_XTR": str(CATALOG_AMOUNT_XTR)},
            {"TELEGRAM_STARS_ENABLED": "true"},
        )
        for override in invalid:
            with self.subTest(override=override), self.assertRaises(
                BillingConfigurationError
            ):
                settings_type.from_env(canary_environment(**override))

        disabled = settings_type.from_env(
            {
                "TELEGRAM_STARS_ENABLED": "false",
                "STARS_PRODUCTION_CANARY_ENABLED": "false",
            }
        )
        self.assertFalse(disabled.enabled)
        self.assertFalse(disabled.public_checkout_enabled)

        alias_only = settings_type.from_env(
            {
                "TELEGRAM_STARS_ENABLED": "false",
                "STARS_CANARY_ENABLED": "true",
                "STARS_CANARY_OWNER_ID": str(OWNER_ID),
                "STARS_CANARY_PRODUCT_ID": PRODUCT_ID,
                "STARS_CANARY_AMOUNT_XTR": str(CANARY_AMOUNT_XTR),
            }
        )
        self.assertFalse(alias_only.enabled)


class ProductionStarsCanaryHandlerContractTest(unittest.IsolatedAsyncioTestCase):
    async def test_ac_3_owner_can_open_terms_accept_and_reach_catalog(self):
        canary = handler_canary_settings()
        for stage in ("open_terms", "accept_terms", "open_catalog"):
            with self.subTest(stage=stage):
                store = MagicMock()
                send_terms = AsyncMock()
                send_products = AsyncMock()
                with (
                    patch.object(bot, "BILLING_SETTINGS", disabled_billing_settings()),
                    patch.object(
                        bot,
                        "STARS_PRODUCTION_CANARY_SETTINGS",
                        canary,
                        create=True,
                    ),
                    patch.object(bot, "get_store", return_value=store),
                    patch.object(bot, "send_billing_terms", new=send_terms),
                    patch.object(bot, "send_billing_products", new=send_products),
                    patch.object(bot, "record_product_event"),
                ):
                    if stage == "open_terms":
                        store.has_consent.return_value = False
                        update, _message = message_update(OWNER_ID)
                        await bot.cmd_buy.__wrapped__(update, SimpleNamespace())
                        send_terms.assert_awaited_once()
                        send_products.assert_not_awaited()
                    elif stage == "accept_terms":
                        store.grant_consent.return_value = True
                        update, query = callback_update(
                            OWNER_ID, "billing:accept_terms"
                        )
                        await bot.billing_consent_cb.__wrapped__(
                            update, SimpleNamespace()
                        )
                        store.grant_consent.assert_called_once_with(
                            OWNER_ID,
                            consent_type="billing_terms",
                            document_version=TERMS_VERSION,
                            source="telegram",
                        )
                        send_products.assert_awaited_once()
                        self.assertFalse(
                            query.answer.await_args.kwargs.get("show_alert", False)
                        )
                    else:
                        store.has_consent.return_value = True
                        update, _query = callback_update(OWNER_ID, "billing:open")
                        await bot.billing_open_cb.__wrapped__(
                            update, SimpleNamespace()
                        )
                        send_products.assert_awaited_once()

    async def test_ac_3_owner_order_invoice_precheckout_and_fulfillment_flow(self):
        canary = handler_canary_settings()
        service = MagicMock()
        service.create_order.return_value = InvoiceOrder(
            order_id="canary-order",
            product_id=PRODUCT_ID,
            title="AI Mini",
            description="20 AI credits",
            credits=CREDITS,
            amount_xtr=CANARY_AMOUNT_XTR,
            payload="md1.canary.signed-payload",
        )
        service.fulfill_successful_payment.return_value = FulfillmentResult(
            payment_id="canary-payment",
            order_id="canary-order",
            credits=CREDITS,
            available_credits=0,
            created=True,
        )
        store = MagicMock()
        store.has_consent.return_value = True

        with self.subTest(stage="invoice"):
            update, query = callback_update(OWNER_ID, f"buy:{PRODUCT_ID}")
            context = SimpleNamespace(bot=SimpleNamespace(send_invoice=AsyncMock()))
            with (
                patch.object(bot, "BILLING_SETTINGS", disabled_billing_settings()),
                patch.object(
                    bot,
                    "STARS_PRODUCTION_CANARY_SETTINGS",
                    canary,
                    create=True,
                ),
                patch.object(bot, "get_store", return_value=store),
                patch.object(bot, "get_billing_service", return_value=service),
                patch.object(bot, "record_product_event"),
            ):
                await bot.buy_product_cb.__wrapped__(update, context)
            service.create_order.assert_called_once_with(
                user_id=OWNER_ID, product_id=PRODUCT_ID
            )
            invoice = context.bot.send_invoice.await_args.kwargs
            self.assertEqual(invoice["currency"], "XTR")
            self.assertEqual(invoice["prices"][0].amount, CANARY_AMOUNT_XTR)
            self.assertNotIn("subscription_period", invoice)
            self.assertNotIn("provider_token", invoice)
            self.assertIsNone(query.answer.await_args.kwargs.get("show_alert"))

        with self.subTest(stage="precheckout"):
            service.validate_pre_checkout.reset_mock()
            query = SimpleNamespace(
                from_user=SimpleNamespace(id=OWNER_ID, language_code="en"),
                invoice_payload="md1.canary.signed-payload",
                currency="XTR",
                total_amount=CANARY_AMOUNT_XTR,
                answer=AsyncMock(),
            )
            update = SimpleNamespace(
                pre_checkout_query=query,
                effective_user=query.from_user,
            )
            with (
                patch.object(
                    bot,
                    "STARS_PRODUCTION_CANARY_SETTINGS",
                    canary,
                    create=True,
                ),
                patch.object(bot, "get_billing_service", return_value=service),
            ):
                await bot.pre_checkout_handler(update, SimpleNamespace())
            service.validate_pre_checkout.assert_called_once()
            query.answer.assert_awaited_once_with(ok=True)

        with self.subTest(stage="fulfillment"):
            service.fulfill_successful_payment.reset_mock()
            payment = SimpleNamespace(
                invoice_payload="md1.canary.signed-payload",
                currency="XTR",
                total_amount=CANARY_AMOUNT_XTR,
                telegram_payment_charge_id=PRIVATE_CHARGE,
                provider_payment_charge_id="",
                is_recurring=False,
                is_first_recurring=False,
                subscription_expiration_date=None,
            )
            message = SimpleNamespace(
                successful_payment=payment,
                reply_text=AsyncMock(),
            )
            update = SimpleNamespace(
                message=message,
                effective_message=message,
                effective_user=SimpleNamespace(
                    id=OWNER_ID, language_code="en"
                ),
            )
            with (
                patch.object(
                    bot,
                    "STARS_PRODUCTION_CANARY_SETTINGS",
                    canary,
                    create=True,
                ),
                patch.object(bot, "get_billing_service", return_value=service),
                patch.object(bot, "record_product_event"),
            ):
                await bot.successful_payment_handler(
                    update, SimpleNamespace(user_data={})
                )
            service.fulfill_successful_payment.assert_called_once()
            message.reply_text.assert_awaited_once()

    async def test_ac_4_non_owner_is_rejected_before_service_order_or_invoice(self):
        canary = handler_canary_settings()
        for stage in (
            "command",
            "open",
            "accept",
            "order",
            "precheckout",
            "fulfillment",
        ):
            with self.subTest(stage=stage):
                service = MagicMock()
                service.create_order.return_value = InvoiceOrder(
                    order_id="forbidden-order",
                    product_id=PRODUCT_ID,
                    title="AI Mini",
                    description="20 AI credits",
                    credits=CREDITS,
                    amount_xtr=CANARY_AMOUNT_XTR,
                    payload="md1.forbidden.signed",
                )
                service.fulfill_successful_payment.return_value = FulfillmentResult(
                    payment_id="forbidden-payment",
                    order_id="forbidden-order",
                    credits=CREDITS,
                    available_credits=CREDITS,
                    created=True,
                )
                store = MagicMock()
                store.has_consent.return_value = True
                send_invoice = AsyncMock()
                send_terms = AsyncMock()
                send_products = AsyncMock()
                with (
                    patch.object(bot, "BILLING_SETTINGS", disabled_billing_settings()),
                    patch.object(
                        bot,
                        "STARS_PRODUCTION_CANARY_SETTINGS",
                        canary,
                        create=True,
                    ),
                    patch.object(bot, "get_store", return_value=store),
                    patch.object(bot, "get_billing_service", return_value=service),
                    patch.object(bot, "send_billing_terms", new=send_terms),
                    patch.object(bot, "send_billing_products", new=send_products),
                    patch.object(bot, "record_product_event"),
                ):
                    if stage == "command":
                        update, _message = message_update(NON_OWNER_ID)
                        await bot.cmd_buy.__wrapped__(update, SimpleNamespace())
                    elif stage == "open":
                        update, _query = callback_update(
                            NON_OWNER_ID, "billing:open"
                        )
                        await bot.billing_open_cb.__wrapped__(
                            update, SimpleNamespace()
                        )
                    elif stage == "accept":
                        update, _query = callback_update(
                            NON_OWNER_ID, "billing:accept_terms"
                        )
                        await bot.billing_consent_cb.__wrapped__(
                            update, SimpleNamespace()
                        )
                    elif stage == "order":
                        update, _query = callback_update(
                            NON_OWNER_ID, f"buy:{PRODUCT_ID}"
                        )
                        await bot.buy_product_cb.__wrapped__(
                            update,
                            SimpleNamespace(
                                bot=SimpleNamespace(send_invoice=send_invoice)
                            ),
                        )
                    elif stage == "precheckout":
                        query = SimpleNamespace(
                            from_user=SimpleNamespace(
                                id=NON_OWNER_ID, language_code="en"
                            ),
                            invoice_payload="md1.forged.payload",
                            currency="XTR",
                            total_amount=CANARY_AMOUNT_XTR,
                            answer=AsyncMock(),
                        )
                        update = SimpleNamespace(
                            pre_checkout_query=query,
                            effective_user=query.from_user,
                        )
                        await bot.pre_checkout_handler(update, SimpleNamespace())
                        self.assertFalse(query.answer.await_args.kwargs["ok"])
                    else:
                        payment = SimpleNamespace(
                            invoice_payload="md1.forged.payload",
                            currency="XTR",
                            total_amount=CANARY_AMOUNT_XTR,
                            telegram_payment_charge_id=PRIVATE_CHARGE,
                            provider_payment_charge_id="",
                        )
                        message = SimpleNamespace(
                            successful_payment=payment,
                            reply_text=AsyncMock(),
                        )
                        update = SimpleNamespace(
                            message=message,
                            effective_message=message,
                            effective_user=SimpleNamespace(
                                id=NON_OWNER_ID, language_code="en"
                            ),
                        )
                        await bot.successful_payment_handler(
                            update, SimpleNamespace(user_data={})
                        )

                service.active_products.assert_not_called()
                service.create_order.assert_not_called()
                service.validate_pre_checkout.assert_not_called()
                service.fulfill_successful_payment.assert_not_called()
                store.grant_consent.assert_not_called()
                send_terms.assert_not_awaited()
                send_products.assert_not_awaited()
                send_invoice.assert_not_awaited()


class ProductionStarsCanaryServiceContractTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="stars-canary-")
        self.store = DatabaseStore(
            f"sqlite:///{self.temporary.name}/stars-canary.sqlite3"
        )
        self.billing_settings = BillingSettings(
            enabled=False,
            payload_secret="production-canary-payload-secret-0123456789",
            support_contact="@canary_support",
            terms_text=TERMS_TEXT,
            terms_version=TERMS_VERSION,
            net_micro_usd_per_xtr=10_000,
            terms_approved=True,
            economics_reviewed_on=datetime.now(timezone.utc).date().isoformat(),
            seller_legal_name="Canary Seller SAS",
            seller_address="1 Canary Street, Paris",
            seller_email="billing@example.test",
            seller_phone="+33102030405",
            terms_sha256=hashlib.sha256(TERMS_TEXT.encode("utf-8")).hexdigest(),
        )
        self.store.ensure_user_id(OWNER_ID)
        self.store.ensure_user_id(NON_OWNER_ID)
        self.store.grant_consent(
            OWNER_ID,
            consent_type="billing_terms",
            document_version=TERMS_VERSION,
            source="test",
        )
        admin = AdminStore(self.store, self.billing_settings)
        admin.upsert_billing_product(
            product_id=PRODUCT_ID,
            title="AI Mini",
            description="20 one-time AI credits",
            credits=CREDITS,
            price_xtr=CATALOG_AMOUNT_XTR,
            status="active",
            estimated_cost_micro_usd=289_000,
            target_margin_bps=5_000,
            display_order=1,
            actor="test",
        )
        admin.upsert_billing_product(
            product_id="ai-other",
            title="AI Other",
            description="Other active product",
            credits=30,
            price_xtr=99,
            status="active",
            estimated_cost_micro_usd=300_000,
            target_margin_bps=5_000,
            display_order=2,
            actor="test",
        )
        admin.upsert_billing_product(
            product_id="ai-monthly",
            title="AI Monthly",
            description="Subscription product",
            credits=20,
            price_xtr=CATALOG_AMOUNT_XTR,
            status="active",
            estimated_cost_micro_usd=289_000,
            target_margin_bps=5_000,
            display_order=3,
            actor="test",
            billing_mode="subscription",
            subscription_period_seconds=billing.SUBSCRIPTION_PERIOD_SECONDS,
        )

    async def asyncTearDown(self):
        self.store.close()
        self.temporary.cleanup()

    def canary_settings(self):
        settings_type = required_public(
            self, billing, "ProductionStarsCanarySettings"
        )
        return settings_type.from_env(canary_environment())

    def service(self, *, billing_settings=None):
        service_type = required_public(
            self, billing, "ProductionStarsCanaryService"
        )
        return service_type(
            self.store,
            billing_settings or self.billing_settings,
            self.canary_settings(),
        )

    def ordinary_service(self):
        service_type = required_public(self, billing, "BillingService")
        return service_type(
            self.store,
            replace(self.billing_settings, enabled=True),
        )

    def create_canary_payment(self, service=None):
        service = service or self.service()
        order = service.create_order(user_id=OWNER_ID, product_id=PRODUCT_ID)
        result = service.fulfill_successful_payment(
            user_id=OWNER_ID,
            payload=order.payload,
            currency="XTR",
            total_amount=CANARY_AMOUNT_XTR,
            telegram_payment_charge_id=PRIVATE_CHARGE,
        )
        self.assertTrue(result.created)
        self.assertIsNotNone(result.refund_id)
        return service, order, result

    def test_ac_6_tampered_marker_actor_does_not_authorize_fulfillment(self):
        service = self.service()
        order = service.create_order(user_id=OWNER_ID, product_id=PRODUCT_ID)
        with self.store.Session.begin() as session:
            marker = session.get(AppSetting, service.MARKER_KEY)
            marker.updated_by = "generic-admin"

        with self.subTest(surface="fulfillment"), self.assertRaises(
            BillingValidationError
        ):
            service.fulfill_successful_payment(
                user_id=OWNER_ID,
                payload=order.payload,
                currency="XTR",
                total_amount=CANARY_AMOUNT_XTR,
                telegram_payment_charge_id=PRIVATE_CHARGE,
            )
        with self.subTest(surface="status"):
            self.assertEqual(service.status()["state"], "armed")
        with self.store.Session() as session:
            self.assertEqual(
                session.scalar(select(func.count(StarsPayment.payment_id))),
                0,
            )
            self.assertEqual(
                session.scalar(select(func.count(RefundRequest.refund_id))),
                0,
            )

    async def test_ac_7_tampered_marker_actor_rejects_refund_and_recovery(self):
        service, _order, result = self.create_canary_payment()
        with self.store.Session.begin() as session:
            marker = session.get(AppSetting, service.MARKER_KEY)
            marker.updated_by = "generic-admin"
        automatic_gateway = AsyncMock()
        automatic_gateway.refund_star_payment.return_value = True
        recovery_gateway = AsyncMock()
        recovery_gateway.get_star_transactions.return_value = StarTransactionPage(
            rows=(remote_canary_row(), remote_canary_row(refunded=True)),
            fetched_count=2,
        )

        with self.subTest(surface="refund"), self.assertRaises(
            BillingValidationError
        ):
            await service.process_refund(
                refund_id=result.refund_id,
                gateway=automatic_gateway,
            )
        with self.subTest(surface="recovery"), self.assertRaises(
            BillingValidationError
        ):
            await service.recover_refund(
                user_id=OWNER_ID,
                refund_id=result.refund_id,
                gateway=recovery_gateway,
            )
        with self.subTest(surface="status"):
            self.assertEqual(service.status()["state"], "armed")
        automatic_gateway.refund_star_payment.assert_not_awaited()
        recovery_gateway.get_star_transactions.assert_not_awaited()
        recovery_gateway.refund_star_payment.assert_not_awaited()

    async def test_ac_7_recovery_scans_second_full_history_page(self):
        service, _order, result = self.create_canary_payment()
        with self.store.Session.begin() as session:
            refund = session.get(RefundRequest, result.refund_id)
            refund.status = "processing"
        first_page = tuple(
            {
                **remote_canary_row(),
                "telegram_payment_charge_id": f"PRIVATE-DECOY-{index}",
            }
            for index in range(100)
        )
        gateway = AsyncMock()
        gateway.get_star_transactions.side_effect = (
            StarTransactionPage(rows=first_page, fetched_count=100),
            StarTransactionPage(
                rows=(remote_canary_row(), remote_canary_row(refunded=True)),
                fetched_count=2,
            ),
        )

        try:
            recovered = await service.recover_refund(
                user_id=OWNER_ID,
                refund_id=result.refund_id,
                gateway=gateway,
            )
        except BillingStateError:
            recovered = False

        self.assertTrue(
            recovered,
            "recovery must continue past a full first page to find the canary",
        )

        self.assertEqual(
            gateway.get_star_transactions.await_args_list,
            [
                call(offset=0, limit=100),
                call(offset=100, limit=100),
            ],
        )
        gateway.refund_star_payment.assert_not_awaited()
        with self.store.Session() as session:
            refund = session.get(RefundRequest, result.refund_id)
            wallet = session.get(AIWallet, OWNER_ID)
            self.assertEqual(refund.status, "completed")
            self.assertEqual(wallet.balance_credits, 0)
            self.assertEqual(wallet.reserved_credits, 0)

    async def test_error_recovery_capped_history_is_uncertain_and_never_refunds(self):
        service, _order, result = self.create_canary_payment()
        with self.store.Session.begin() as session:
            refund = session.get(RefundRequest, result.refund_id)
            refund.status = "failed"
        full_page = StarTransactionPage(
            rows=tuple(
                {
                    **remote_canary_row(),
                    "telegram_payment_charge_id": f"PRIVATE-DECOY-{index}",
                }
                for index in range(100)
            ),
            fetched_count=100,
        )
        gateway = AsyncMock()
        gateway.get_star_transactions.return_value = full_page

        with self.assertRaisesRegex(
            BillingStateError,
            "uncertain|truncated|capped",
        ):
            await asyncio.wait_for(
                service.recover_refund(
                    user_id=OWNER_ID,
                    refund_id=result.refund_id,
                    gateway=gateway,
                ),
                timeout=1,
            )

        self.assertGreaterEqual(gateway.get_star_transactions.await_count, 1)
        self.assertLessEqual(gateway.get_star_transactions.await_count, 10)
        gateway.refund_star_payment.assert_not_awaited()
        with self.store.Session() as session:
            refund = session.get(RefundRequest, result.refund_id)
            wallet = session.get(AIWallet, OWNER_ID)
            self.assertEqual(refund.status, "failed")
            self.assertEqual(wallet.balance_credits, CREDITS)
            self.assertEqual(wallet.reserved_credits, CREDITS)

    async def test_ac_11_service_discovers_only_provenance_valid_refund(self):
        ordinary = self.ordinary_service()
        historical_order = ordinary.create_order(
            user_id=OWNER_ID,
            product_id=PRODUCT_ID,
        )
        historical_payment = ordinary.fulfill_successful_payment(
            user_id=OWNER_ID,
            payload=historical_order.payload,
            currency="XTR",
            total_amount=CATALOG_AMOUNT_XTR,
            telegram_payment_charge_id="PRIVATE-HISTORICAL-CHARGE-ID",
        )
        historical_refund_id = ordinary.request_refund(
            payment_id=historical_payment.payment_id,
            reason="Historical ordinary refund request",
            actor="generic-admin",
        )
        service, _canary_order, canary_payment = self.create_canary_payment()
        recover_current_refund = required_public(
            self,
            service,
            "recover_current_refund",
        )
        gateway = AsyncMock()
        gateway.get_star_transactions.return_value = StarTransactionPage(
            rows=(remote_canary_row(), remote_canary_row(refunded=True)),
            fetched_count=2,
        )

        self.assertTrue(
            await recover_current_refund(gateway=gateway)
        )

        gateway.get_star_transactions.assert_awaited_once_with(
            offset=0,
            limit=100,
        )
        gateway.refund_star_payment.assert_not_awaited()
        with self.store.Session() as session:
            historical_refund = session.get(RefundRequest, historical_refund_id)
            canary_refund = session.get(
                RefundRequest,
                canary_payment.refund_id,
            )
            wallet = session.get(AIWallet, OWNER_ID)
            self.assertEqual(historical_refund.status, "requested")
            self.assertEqual(canary_refund.status, "completed")
            self.assertEqual(wallet.balance_credits, CREDITS)
            self.assertEqual(wallet.reserved_credits, CREDITS)

    async def test_ac_6_concurrent_owner_order_claim_yields_one_invoice(self):
        service = self.service()
        rendezvous = threading.Barrier(2)
        ordinary_create_order = billing.BillingService.create_order

        def synchronized_create_order(base_service, *, user_id, product_id):
            rendezvous.wait(timeout=5)
            return ordinary_create_order(
                base_service,
                user_id=user_id,
                product_id=product_id,
            )

        async def attempt_order():
            try:
                return await asyncio.to_thread(
                    service.create_order,
                    user_id=OWNER_ID,
                    product_id=PRODUCT_ID,
                )
            except Exception as exc:
                return exc

        with patch.object(
            billing.BillingService,
            "create_order",
            new=synchronized_create_order,
        ):
            outcomes = await asyncio.gather(attempt_order(), attempt_order())

        invoices = [
            outcome for outcome in outcomes if isinstance(outcome, InvoiceOrder)
        ]
        rejected = [outcome for outcome in outcomes if isinstance(outcome, Exception)]
        self.assertEqual(len(invoices), 1, "only one owner tap may become payable")
        self.assertEqual(len(rejected), 1)
        self.assertIsInstance(
            rejected[0],
            (BillingStateError, BillingValidationError),
            "the durable claim must reject the loser without leaking a DB error",
        )
        with self.store.Session() as session:
            self.assertEqual(
                session.scalar(select(func.count(PaymentOrder.order_id))),
                1,
            )

    async def test_ac_4_legacy_non_owner_payment_is_fulfilled_but_precheckout_and_forgery_fail(
        self,
    ):
        self.store.grant_consent(
            NON_OWNER_ID,
            consent_type="billing_terms",
            document_version=TERMS_VERSION,
            source="test",
        )
        ordinary = self.ordinary_service()
        legacy_order = ordinary.create_order(
            user_id=NON_OWNER_ID,
            product_id=PRODUCT_ID,
        )
        canary = self.service()

        precheckout = SimpleNamespace(
            from_user=SimpleNamespace(id=NON_OWNER_ID, language_code="en"),
            invoice_payload=legacy_order.payload,
            currency="XTR",
            total_amount=CATALOG_AMOUNT_XTR,
            answer=AsyncMock(),
        )
        precheckout_update = SimpleNamespace(
            pre_checkout_query=precheckout,
            effective_user=precheckout.from_user,
        )
        valid_update, valid_message = successful_payment_update(
            NON_OWNER_ID,
            legacy_order.payload,
            "PRIVATE-LEGACY-CHARGE-ID",
            total_amount=CATALOG_AMOUNT_XTR,
        )
        forged_update, forged_message = successful_payment_update(
            NON_OWNER_ID,
            f"{legacy_order.payload}x",
            "PRIVATE-FORGED-CHARGE-ID",
            total_amount=CATALOG_AMOUNT_XTR,
        )
        with (
            patch.object(
                bot,
                "STARS_PRODUCTION_CANARY_SETTINGS",
                self.canary_settings(),
            ),
            patch.object(bot, "BILLING_SETTINGS", self.billing_settings),
            patch.object(bot, "get_billing_service", return_value=canary),
            patch.object(bot, "record_product_event"),
        ):
            await bot.pre_checkout_handler(precheckout_update, SimpleNamespace())
            await bot.successful_payment_handler(
                valid_update,
                SimpleNamespace(user_data={}),
            )
            await bot.successful_payment_handler(
                forged_update,
                SimpleNamespace(user_data={}),
            )

        self.assertFalse(precheckout.answer.await_args.kwargs["ok"])
        valid_message.reply_text.assert_awaited_once()
        forged_message.reply_text.assert_awaited_once()
        with self.store.Session() as session:
            wallet = session.get(AIWallet, NON_OWNER_ID)
            self.assertIsNotNone(wallet)
            self.assertEqual(wallet.balance_credits, CREDITS)
            self.assertEqual(wallet.reserved_credits, 0)
            self.assertEqual(
                session.scalar(select(func.count(StarsPayment.payment_id))),
                1,
            )
            self.assertEqual(
                session.scalar(select(func.count(RefundRequest.refund_id))),
                0,
            )

    async def test_ac_7_handler_refunds_once_and_confirms_refund_explicitly(self):
        service = self.service()
        order = service.create_order(user_id=OWNER_ID, product_id=PRODUCT_ID)
        update, message = successful_payment_update(
            OWNER_ID,
            order.payload,
            PRIVATE_CHARGE,
        )
        bot_api = SimpleNamespace(refund_star_payment=AsyncMock(return_value=True))

        with (
            patch.object(
                bot,
                "STARS_PRODUCTION_CANARY_SETTINGS",
                self.canary_settings(),
            ),
            patch.object(bot, "get_billing_service", return_value=service),
            patch.object(bot, "record_product_event"),
        ):
            await bot.successful_payment_handler(
                update,
                SimpleNamespace(user_data={}, bot=bot_api),
            )

        bot_api.refund_star_payment.assert_awaited_once_with(
            user_id=OWNER_ID,
            telegram_payment_charge_id=PRIVATE_CHARGE,
        )
        message.reply_text.assert_awaited_once()
        confirmation = str(message.reply_text.await_args.args[0]).lower()
        self.assertIn("refund", confirmation)
        self.assertNotIn("available", confirmation)
        with self.store.Session() as session:
            refund = session.execute(select(RefundRequest)).scalar_one()
            wallet = session.get(AIWallet, OWNER_ID)
            self.assertEqual(refund.status, "completed")
            self.assertEqual(wallet.balance_credits, 0)
            self.assertEqual(wallet.reserved_credits, 0)

    async def test_error_handler_refund_gateway_failure_keeps_recovery_state(self):
        service = self.service()
        order = service.create_order(user_id=OWNER_ID, product_id=PRODUCT_ID)
        update, message = successful_payment_update(
            OWNER_ID,
            order.payload,
            PRIVATE_CHARGE,
        )
        bot_api = SimpleNamespace(
            refund_star_payment=AsyncMock(side_effect=TimeoutError("gateway timeout"))
        )

        with (
            patch.object(
                bot,
                "STARS_PRODUCTION_CANARY_SETTINGS",
                self.canary_settings(),
            ),
            patch.object(bot, "get_billing_service", return_value=service),
            patch.object(bot, "record_product_event"),
        ):
            await bot.successful_payment_handler(
                update,
                SimpleNamespace(user_data={}, bot=bot_api),
            )

        bot_api.refund_star_payment.assert_awaited_once()
        message.reply_text.assert_awaited_once()
        with self.store.Session() as session:
            refund = session.execute(select(RefundRequest)).scalar_one()
            wallet = session.get(AIWallet, OWNER_ID)
            self.assertEqual(refund.status, "failed")
            self.assertIsNotNone(refund.error_code)
            self.assertEqual(wallet.balance_credits, CREDITS)
            self.assertEqual(wallet.reserved_credits, CREDITS)

    def test_ac_4_ac_5_catalog_order_and_precheckout_are_exact_owner_only(self):
        service = self.service()

        with self.store.Session() as session:
            underlying = session.get(billing.BillingProduct, PRODUCT_ID)
            self.assertEqual(underlying.price_xtr, CATALOG_AMOUNT_XTR)
            self.assertEqual(underlying.credits, CREDITS)
            self.assertEqual(underlying.status, "active")
            self.assertEqual(underlying.billing_mode, "one_time")

        products = service.active_products(user_id=OWNER_ID)
        self.assertEqual(len(products), 1)
        self.assertEqual(
            {
                key: products[0][key]
                for key in (
                    "product_id",
                    "credits",
                    "price_xtr",
                    "billing_mode",
                    "subscription_period_seconds",
                )
            },
            {
                "product_id": PRODUCT_ID,
                "credits": CREDITS,
                "price_xtr": CANARY_AMOUNT_XTR,
                "billing_mode": "one_time",
                "subscription_period_seconds": None,
            },
        )
        with self.assertRaises(BillingValidationError):
            service.active_products(user_id=NON_OWNER_ID)
        with self.assertRaises(BillingValidationError):
            service.create_order(user_id=OWNER_ID, product_id="ai-other")
        with self.assertRaises(BillingValidationError):
            service.create_order(user_id=OWNER_ID, product_id="ai-monthly")
        with self.assertRaises(BillingValidationError):
            service.create_order(user_id=NON_OWNER_ID, product_id=PRODUCT_ID)

        order = service.create_order(user_id=OWNER_ID, product_id=PRODUCT_ID)
        self.assertEqual(order.product_id, PRODUCT_ID)
        self.assertEqual(order.credits, CREDITS)
        self.assertEqual(order.amount_xtr, CANARY_AMOUNT_XTR)
        self.assertIsNone(order.subscription_period_seconds)
        with self.store.Session() as session:
            persisted_order = session.get(PaymentOrder, order.order_id)
            self.assertEqual(persisted_order.amount_xtr, CANARY_AMOUNT_XTR)
            self.assertEqual(
                session.get(billing.BillingProduct, PRODUCT_ID).price_xtr,
                CATALOG_AMOUNT_XTR,
            )
        with self.assertRaises(BillingValidationError):
            service.validate_pre_checkout(
                user_id=NON_OWNER_ID,
                payload=order.payload,
                currency="XTR",
                total_amount=CANARY_AMOUNT_XTR,
            )
        with self.assertRaises(BillingValidationError):
            service.validate_pre_checkout(
                user_id=OWNER_ID,
                payload=order.payload,
                currency="XTR",
                total_amount=CANARY_AMOUNT_XTR + 1,
            )
        with self.assertRaises(BillingValidationError):
            service.validate_pre_checkout(
                user_id=OWNER_ID,
                payload=f"{order.payload}x",
                currency="XTR",
                total_amount=CANARY_AMOUNT_XTR,
            )
        service.validate_pre_checkout(
            user_id=OWNER_ID,
            payload=order.payload,
            currency="XTR",
            total_amount=CANARY_AMOUNT_XTR,
        )
        with self.assertRaises(BillingValidationError):
            service.fulfill_successful_payment(
                user_id=OWNER_ID,
                payload=order.payload,
                currency="XTR",
                total_amount=CANARY_AMOUNT_XTR,
                telegram_payment_charge_id="recurring-is-forbidden",
                is_recurring=True,
                is_first_recurring=True,
                subscription_expiration_date=(
                    datetime.now(timezone.utc) + timedelta(days=30)
                ),
            )

    def test_error_repricing_base_catalog_to_canary_amount_fails_closed(self):
        service = self.service()
        with self.store.Session.begin() as session:
            session.get(
                billing.BillingProduct,
                PRODUCT_ID,
            ).price_xtr = CANARY_AMOUNT_XTR

        with self.assertRaises(BillingValidationError):
            service.active_products(user_id=OWNER_ID)
        with self.assertRaises(BillingValidationError):
            service.create_order(user_id=OWNER_ID, product_id=PRODUCT_ID)

    async def test_ac_6_ac_7_fulfillment_and_refund_request_are_idempotent(self):
        service = self.service()
        order = service.create_order(user_id=OWNER_ID, product_id=PRODUCT_ID)
        service.validate_pre_checkout(
            user_id=OWNER_ID,
            payload=order.payload,
            currency="XTR",
            total_amount=CANARY_AMOUNT_XTR,
        )

        first = service.fulfill_successful_payment(
            user_id=OWNER_ID,
            payload=order.payload,
            currency="XTR",
            total_amount=CANARY_AMOUNT_XTR,
            telegram_payment_charge_id=PRIVATE_CHARGE,
        )
        duplicate = service.fulfill_successful_payment(
            user_id=OWNER_ID,
            payload=order.payload,
            currency="XTR",
            total_amount=CANARY_AMOUNT_XTR,
            telegram_payment_charge_id=PRIVATE_CHARGE,
        )

        self.assertTrue(first.created)
        self.assertFalse(duplicate.created)
        completed_status = service.status()
        self.assertEqual(completed_status["state"], "completed")
        self.assertTrue(completed_status["payment_completed"])
        self.assertTrue(completed_status["refund_pending"])
        self.assertFalse(completed_status["refund_completed"])
        with self.store.Session() as session:
            wallet = session.get(AIWallet, OWNER_ID)
            refunds = session.execute(select(RefundRequest)).scalars().all()
            self.assertEqual(wallet.balance_credits, CREDITS)
            self.assertEqual(wallet.reserved_credits, CREDITS)
            self.assertEqual(
                session.scalar(select(func.count(StarsPayment.payment_id))), 1
            )
            self.assertEqual(
                session.scalar(
                    select(func.count(BillingCreditLedger.entry_id)).where(
                        BillingCreditLedger.entry_type == "stars_purchase"
                    )
                ),
                1,
            )
            self.assertEqual(len(refunds), 1)
            self.assertEqual(refunds[0].status, "requested")
            refund_id = refunds[0].refund_id

        gateway = AsyncMock()
        gateway.refund_star_payment.return_value = True
        self.assertTrue(
            await service.process_refund(refund_id=refund_id, gateway=gateway)
        )
        self.assertTrue(
            await service.process_refund(refund_id=refund_id, gateway=gateway)
        )
        gateway.refund_star_payment.assert_awaited_once_with(
            user_id=OWNER_ID,
            telegram_payment_charge_id=PRIVATE_CHARGE,
        )
        refunded_status = service.status()
        self.assertEqual(refunded_status["state"], "refunded")
        self.assertTrue(refunded_status["payment_completed"])
        self.assertFalse(refunded_status["refund_pending"])
        self.assertTrue(refunded_status["refund_completed"])
        with self.store.Session() as session:
            wallet = session.get(AIWallet, OWNER_ID)
            refund = session.get(RefundRequest, refund_id)
            payment = session.get(StarsPayment, first.payment_id)
            self.assertEqual(wallet.balance_credits, 0)
            self.assertEqual(wallet.reserved_credits, 0)
            self.assertEqual(refund.status, "completed")
            self.assertEqual(payment.status, "refunded")
            self.assertEqual(
                session.scalar(
                    select(func.count(BillingCreditLedger.entry_id)).where(
                        BillingCreditLedger.entry_type == "stars_refund"
                    )
                ),
                1,
            )

    async def test_error_refund_failure_keeps_durable_manual_recovery_evidence(self):
        service = self.service()
        order = service.create_order(user_id=OWNER_ID, product_id=PRODUCT_ID)
        result = service.fulfill_successful_payment(
            user_id=OWNER_ID,
            payload=order.payload,
            currency="XTR",
            total_amount=CANARY_AMOUNT_XTR,
            telegram_payment_charge_id=PRIVATE_CHARGE,
        )
        with self.store.Session() as session:
            refund = session.execute(
                select(RefundRequest).where(
                    RefundRequest.payment_id == result.payment_id
                )
            ).scalar_one()
            refund_id = refund.refund_id
        gateway = AsyncMock()
        gateway.refund_star_payment.side_effect = TimeoutError("gateway timeout")

        self.assertFalse(
            await service.process_refund(refund_id=refund_id, gateway=gateway)
        )

        gateway.refund_star_payment.assert_awaited_once()
        with self.store.Session() as session:
            refund = session.get(RefundRequest, refund_id)
            wallet = session.get(AIWallet, OWNER_ID)
            self.assertEqual(refund.status, "failed")
            self.assertEqual(wallet.balance_credits, CREDITS)
            self.assertEqual(wallet.reserved_credits, CREDITS)

    async def test_ac_7_failed_refund_recovery_reconciles_before_one_retry(self):
        service, _order, result = self.create_canary_payment()
        first_gateway = AsyncMock()
        first_gateway.refund_star_payment.side_effect = TimeoutError(
            "gateway timeout"
        )
        self.assertFalse(
            await service.process_refund(
                refund_id=result.refund_id,
                gateway=first_gateway,
            )
        )
        recover_refund = required_public(self, service, "recover_refund")
        recovery_gateway = AsyncMock()
        recovery_gateway.get_star_transactions.return_value = StarTransactionPage(
            rows=(remote_canary_row(),),
            fetched_count=1,
        )
        recovery_gateway.refund_star_payment.return_value = True

        with self.assertRaises(BillingValidationError):
            await recover_refund(
                user_id=NON_OWNER_ID,
                refund_id=result.refund_id,
                gateway=recovery_gateway,
            )
        self.assertTrue(
            await recover_refund(
                user_id=OWNER_ID,
                refund_id=result.refund_id,
                gateway=recovery_gateway,
            )
        )
        self.assertTrue(
            await recover_refund(
                user_id=OWNER_ID,
                refund_id=result.refund_id,
                gateway=recovery_gateway,
            )
        )

        recovery_gateway.get_star_transactions.assert_awaited_once()
        recovery_gateway.refund_star_payment.assert_awaited_once_with(
            user_id=OWNER_ID,
            telegram_payment_charge_id=PRIVATE_CHARGE,
        )
        with self.store.Session() as session:
            refund = session.get(RefundRequest, result.refund_id)
            wallet = session.get(AIWallet, OWNER_ID)
            self.assertEqual(refund.status, "completed")
            self.assertEqual(wallet.balance_credits, 0)
            self.assertEqual(wallet.reserved_credits, 0)

    async def test_ac_7_processing_recovery_finalizes_remote_refund_without_retry(
        self,
    ):
        service, _order, result = self.create_canary_payment()
        with self.store.Session.begin() as session:
            refund = session.get(RefundRequest, result.refund_id)
            refund.status = "processing"
        recover_refund = required_public(self, service, "recover_refund")
        gateway = AsyncMock()
        gateway.get_star_transactions.return_value = StarTransactionPage(
            rows=(remote_canary_row(), remote_canary_row(refunded=True)),
            fetched_count=2,
        )

        self.assertTrue(
            await recover_refund(
                user_id=OWNER_ID,
                refund_id=result.refund_id,
                gateway=gateway,
            )
        )

        gateway.get_star_transactions.assert_awaited_once()
        gateway.refund_star_payment.assert_not_awaited()
        with self.store.Session() as session:
            refund = session.get(RefundRequest, result.refund_id)
            payment = session.get(StarsPayment, result.payment_id)
            wallet = session.get(AIWallet, OWNER_ID)
            self.assertEqual(refund.status, "completed")
            self.assertEqual(payment.status, "refunded")
            self.assertEqual(wallet.balance_credits, 0)
            self.assertEqual(wallet.reserved_credits, 0)

    async def test_ac_6_v2_claim_preserves_unpaid_v1_order_and_evidence_ignores_it(
        self,
    ):
        ordinary = self.ordinary_service()
        legacy_order = ordinary.create_order(
            user_id=OWNER_ID,
            product_id=PRODUCT_ID,
        )
        self.assertEqual(legacy_order.amount_xtr, CATALOG_AMOUNT_XTR)
        with self.store.Session.begin() as session:
            session.add(
                AppSetting(
                    key=LEGACY_CANARY_MARKER_KEY,
                    value=legacy_order.order_id,
                    updated_by="stars_canary",
                )
            )
        with self.store.Session() as session:
            legacy_before = session.get(PaymentOrder, legacy_order.order_id)
            legacy_snapshot = (
                legacy_before.invoice_payload,
                legacy_before.amount_xtr,
                legacy_before.status,
            )

        service = self.service()
        self.assertNotEqual(service.MARKER_KEY, LEGACY_CANARY_MARKER_KEY)
        v2_order = service.create_order(user_id=OWNER_ID, product_id=PRODUCT_ID)
        self.assertEqual(v2_order.amount_xtr, CANARY_AMOUNT_XTR)
        self.assertNotEqual(v2_order.order_id, legacy_order.order_id)
        with self.assertRaises(BillingValidationError):
            service.validate_pre_checkout(
                user_id=OWNER_ID,
                payload=legacy_order.payload,
                currency="XTR",
                total_amount=CATALOG_AMOUNT_XTR,
            )

        result = service.fulfill_successful_payment(
            user_id=OWNER_ID,
            payload=v2_order.payload,
            currency="XTR",
            total_amount=CANARY_AMOUNT_XTR,
            telegram_payment_charge_id=PRIVATE_CHARGE,
        )
        gateway = AsyncMock()
        gateway.refund_star_payment.return_value = True
        self.assertTrue(
            await service.process_refund(
                refund_id=result.refund_id,
                gateway=gateway,
            )
        )
        disabled = billing.ProductionStarsCanarySettings.from_env(
            {
                "TELEGRAM_STARS_ENABLED": "false",
                "STARS_PRODUCTION_CANARY_ENABLED": "false",
            }
        )
        evidence = billing.read_production_stars_canary_status(
            store=self.store,
            canary_settings=disabled,
        )
        self.assertEqual(evidence["state"], "refunded")
        self.assertEqual(evidence["amount_xtr"], CANARY_AMOUNT_XTR)
        receipt = stars_launch.build_production_stars_canary_receipt(evidence)
        self.assertEqual(receipt["status"]["amount_xtr"], CANARY_AMOUNT_XTR)

        with self.store.Session() as session:
            legacy_after = session.get(PaymentOrder, legacy_order.order_id)
            legacy_marker = session.get(AppSetting, LEGACY_CANARY_MARKER_KEY)
            v2_marker = session.get(AppSetting, service.MARKER_KEY)
            self.assertEqual(
                (
                    legacy_after.invoice_payload,
                    legacy_after.amount_xtr,
                    legacy_after.status,
                ),
                legacy_snapshot,
            )
            self.assertEqual(legacy_marker.value, legacy_order.order_id)
            self.assertEqual(legacy_marker.updated_by, "stars_canary")
            self.assertEqual(v2_marker.value, v2_order.order_id)

    def test_ac_7_ac_8_historical_matching_purchase_is_not_canary_provenance(
        self,
    ):
        ordinary = self.ordinary_service()
        historical = ordinary.create_order(
            user_id=OWNER_ID,
            product_id=PRODUCT_ID,
        )
        ordinary.fulfill_successful_payment(
            user_id=OWNER_ID,
            payload=historical.payload,
            currency="XTR",
            total_amount=CATALOG_AMOUNT_XTR,
            telegram_payment_charge_id="PRIVATE-HISTORICAL-CHARGE-ID",
        )

        service = self.service()
        self.assertEqual(service.status()["state"], "armed")
        canary_order = service.create_order(
            user_id=OWNER_ID,
            product_id=PRODUCT_ID,
        )
        self.assertNotEqual(canary_order.order_id, historical.order_id)

    async def test_ac_10_disabled_status_reader_reports_refunded_canary(self):
        service, _order, result = self.create_canary_payment()
        gateway = AsyncMock()
        gateway.refund_star_payment.return_value = True
        self.assertTrue(
            await service.process_refund(
                refund_id=result.refund_id,
                gateway=gateway,
            )
        )
        settings_type = required_public(
            self,
            billing,
            "ProductionStarsCanarySettings",
        )
        disabled = settings_type.from_env(
            {
                "TELEGRAM_STARS_ENABLED": "false",
                "STARS_PRODUCTION_CANARY_ENABLED": "false",
            }
        )
        read_status = required_public(
            self,
            billing,
            "read_production_stars_canary_status",
        )

        status = read_status(
            store=self.store,
            canary_settings=disabled,
        )

        self.assertEqual(
            status,
            {
                "public_checkout_enabled": False,
                "canary_enabled": False,
                "state": "refunded",
                "product_id": PRODUCT_ID,
                "amount_xtr": CANARY_AMOUNT_XTR,
                "payment_completed": True,
                "refund_pending": False,
                "refund_completed": True,
            },
        )

    def test_error_archived_terms_seller_economics_and_unsigned_order_fail_closed(self):
        service = self.service()
        self.store.revoke_consent(OWNER_ID, consent_type="billing_terms")
        with self.assertRaises(BillingValidationError):
            service.create_order(user_id=OWNER_ID, product_id=PRODUCT_ID)

        self.store.grant_consent(
            OWNER_ID,
            consent_type="billing_terms",
            document_version=TERMS_VERSION,
            source="test",
        )
        with self.store.Session.begin() as session:
            session.get(billing.BillingProduct, PRODUCT_ID).status = "archived"
        with self.assertRaises(BillingValidationError):
            service.create_order(user_id=OWNER_ID, product_id=PRODUCT_ID)

        for bad_settings in (
            replace(self.billing_settings, seller_legal_name=""),
            replace(
                self.billing_settings,
                economics_reviewed_on=(
                    datetime.now(timezone.utc).date() - timedelta(days=31)
                ).isoformat(),
            ),
        ):
            with self.subTest(settings=bad_settings), self.assertRaises(
                BillingConfigurationError
            ):
                self.service(billing_settings=bad_settings)

        with self.assertRaises(BillingValidationError):
            service.validate_pre_checkout(
                user_id=OWNER_ID,
                payload="unsigned-canary-order",
                currency="XTR",
                total_amount=CANARY_AMOUNT_XTR,
            )

    def test_ac_8_status_is_aggregate_and_contains_no_identifiers(self):
        service = self.service()

        status = service.status()

        self.assertEqual(
            set(status),
            {
                "public_checkout_enabled",
                "canary_enabled",
                "state",
                "product_id",
                "amount_xtr",
                "payment_completed",
                "refund_pending",
                "refund_completed",
            },
        )
        self.assertEqual(status["public_checkout_enabled"], False)
        self.assertEqual(status["canary_enabled"], True)
        self.assertEqual(status["state"], "armed")
        self.assertEqual(status["product_id"], PRODUCT_ID)
        self.assertEqual(status["amount_xtr"], CANARY_AMOUNT_XTR)
        serialized = json.dumps(status, ensure_ascii=False, sort_keys=True)
        for forbidden in (
            str(OWNER_ID),
            str(NON_OWNER_ID),
            PRIVATE_CHARGE,
            "telegram_user_id",
            "charge_id",
            "order_id",
            "payment_id",
            "refund_id",
        ):
            self.assertNotIn(forbidden, serialized)


class ProductionStarsCanaryEvidenceContractTest(unittest.TestCase):
    def test_ac_9_production_canary_receipt_is_labelled_and_rejected_as_test(self):
        build_receipt = required_public(
            self,
            stars_launch,
            "build_production_stars_canary_receipt",
        )
        now = datetime(2026, 8, 23, 12, 0, tzinfo=timezone.utc)
        status = {
            "public_checkout_enabled": False,
            "canary_enabled": False,
            "state": "refunded",
            "product_id": PRODUCT_ID,
            "amount_xtr": CANARY_AMOUNT_XTR,
            "payment_completed": True,
            "refund_pending": False,
            "refund_completed": True,
        }

        receipt = build_receipt(status, completed_at=now)

        self.assertEqual(receipt["environment"], "telegram_production_canary")
        rendered = json.dumps(receipt, ensure_ascii=False, sort_keys=True)
        for forbidden in (
            str(OWNER_ID),
            PRIVATE_CHARGE,
            "telegram_user_id",
            "charge_id",
            "payment_id",
            "refund_id",
        ):
            self.assertNotIn(forbidden, rendered)

        with tempfile.TemporaryDirectory(prefix="stars-canary-receipt-") as raw:
            path = Path(raw) / "receipt.json"
            path.write_text(rendered, encoding="utf-8")
            os.chmod(path, 0o600)
            with self.assertRaises(stars_launch.StarsLaunchError):
                stars_launch.validate_stars_test_receipt(path, now=now)

    def test_ac_10_final_receipt_rejects_enabled_or_unfinished_canary(self):
        build_receipt = required_public(
            self,
            stars_launch,
            "build_production_stars_canary_receipt",
        )
        base = {
            "public_checkout_enabled": False,
            "canary_enabled": False,
            "state": "refunded",
            "product_id": PRODUCT_ID,
            "amount_xtr": CANARY_AMOUNT_XTR,
            "payment_completed": True,
            "refund_pending": False,
            "refund_completed": True,
        }
        invalid_statuses = (
            {**base, "canary_enabled": True},
            {
                **base,
                "canary_enabled": True,
                "state": "armed",
                "payment_completed": False,
                "refund_completed": False,
            },
            {
                **base,
                "canary_enabled": True,
                "state": "completed",
                "refund_pending": True,
                "refund_completed": False,
            },
        )

        for status in invalid_statuses:
            with self.subTest(status=status), self.assertRaises(
                stars_launch.StarsLaunchError
            ):
                build_receipt(status)


if __name__ == "__main__":
    unittest.main()
