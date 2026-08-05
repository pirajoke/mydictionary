import os
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

os.environ.setdefault("BOT_TOKEN", "123456:TESTTOKEN")
os.environ.setdefault("ALLOWED_USER_ID", "1")

import bot
from mydictionary.billing import FulfillmentResult, InvoiceOrder


class StarsHandlerTest(unittest.IsolatedAsyncioTestCase):
    async def test_user_ai_stats_hide_provider_tokens_and_internal_cost(self):
        store = MagicMock()
        store.ai_usage_summary.return_value = {
            "available_credits": 10,
            "reserved_credits": 1,
            "spent_credits": 2,
            "completed_requests": 2,
            "failed_requests": 1,
            "total_tokens": 999,
            "cost_micro_usd": 123456,
        }
        message = SimpleNamespace(reply_text=AsyncMock())
        update = SimpleNamespace(
            message=message, effective_user=SimpleNamespace(id=7001)
        )
        with patch.object(bot, "get_store", return_value=store):
            await bot.cmd_ai_stats.__wrapped__(update, SimpleNamespace())
        rendered = message.reply_text.await_args.args[0]
        self.assertNotIn("Токены", rendered)
        self.assertNotIn("Стоимость", rendered)
        self.assertNotIn("999", rendered)

    async def test_invoice_uses_xtr_and_omits_provider_token(self):
        service = MagicMock()
        service.create_order.return_value = InvoiceOrder(
            order_id="order-1",
            product_id="ai-starter",
            title="AI Starter",
            description="50 AI credits",
            credits=50,
            amount_xtr=100,
            payload="md1.payload.signature",
        )
        query = SimpleNamespace(
            data="buy:ai-starter",
            answer=AsyncMock(),
            message=SimpleNamespace(chat_id=7001, reply_text=AsyncMock()),
        )
        update = SimpleNamespace(
            callback_query=query,
            effective_user=SimpleNamespace(id=7001),
        )
        context = SimpleNamespace(bot=SimpleNamespace(send_invoice=AsyncMock()))

        with patch.object(bot, "get_billing_service", return_value=service):
            await bot.buy_product_cb.__wrapped__(update, context)

        kwargs = context.bot.send_invoice.await_args.kwargs
        self.assertEqual(kwargs["currency"], "XTR")
        self.assertNotIn("provider_token", kwargs)
        self.assertEqual(kwargs["prices"][0].amount, 100)

    async def test_pre_checkout_rejects_mismatched_order(self):
        service = MagicMock()
        service.validate_pre_checkout.side_effect = ValueError("mismatch")
        query = SimpleNamespace(
            from_user=SimpleNamespace(id=7001),
            invoice_payload="bad",
            currency="XTR",
            total_amount=100,
            answer=AsyncMock(),
        )
        update = SimpleNamespace(pre_checkout_query=query)

        with patch.object(bot, "get_billing_service", return_value=service):
            await bot.pre_checkout_handler(update, SimpleNamespace())

        query.answer.assert_awaited_once()
        self.assertFalse(query.answer.await_args.kwargs["ok"])

    async def test_successful_payment_is_fulfilled_through_service(self):
        service = MagicMock()
        service.fulfill_successful_payment.return_value = FulfillmentResult(
            payment_id="payment-1",
            order_id="order-1",
            credits=50,
            available_credits=50,
            created=True,
        )
        message = SimpleNamespace(
            successful_payment=SimpleNamespace(
                invoice_payload="payload",
                currency="XTR",
                total_amount=100,
                telegram_payment_charge_id="charge-1",
                provider_payment_charge_id="",
            ),
            reply_text=AsyncMock(),
        )
        update = SimpleNamespace(
            message=message, effective_user=SimpleNamespace(id=7001)
        )

        with patch.object(bot, "get_billing_service", return_value=service):
            await bot.successful_payment_handler(update, SimpleNamespace())

        service.fulfill_successful_payment.assert_called_once()
        message.reply_text.assert_awaited_once()
        self.assertIn("Начислено 50", message.reply_text.await_args.args[0])


if __name__ == "__main__":
    unittest.main()
