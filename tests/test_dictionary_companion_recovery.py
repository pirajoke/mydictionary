from contextlib import ExitStack
from dataclasses import replace
from decimal import Decimal
import json
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch
from urllib.parse import parse_qs, urlsplit

import bot
from mydictionary import ai_tutor
from mydictionary.localization import INTERFACE_LOCALES, translate
from mydictionary.storage import AIQuotaExceeded
from tests import test_ai_response_experience_v1 as response_tests
from tests import test_ai_learning_companion as companion_tests
from tests import test_dictionary_lookup_mode_v1 as dictionary_tests


class DictionaryCompanionRecoveryTest(unittest.IsolatedAsyncioTestCase):
    async def test_ec4_real_pricing_accepts_normal_deep_input_and_fails_closed_at_budget_boundary(self):
        pricing = ai_tutor.ModelPricing(
            Decimal("0.20"), Decimal("0.02"), Decimal("0.25"), Decimal("1.20")
        )
        empty_budget = ai_tutor.estimate_mirror_provider_budget(
            serialized_input="", pricing=pricing, max_output_tokens=1000,
        )
        # The approved worst-case input rate is 0.25 microUSD per UTF-8 byte;
        # 1000 output tokens reserve 1200 microUSD of the 5000 request cap.
        maximum_bytes = 15200 - empty_budget.input_tokens_upper_bound
        original = companion_tests.LearningCompanionServiceHardeningTest().valid_payload()
        original.update(question="explain this grammar rule", complexity_route="deep", is_continuation=False, recent_dialogue=[])
        for target_bytes, allowed in ((None, True), (maximum_bytes, True), (maximum_bytes + 1, False)):
            with self.subTest(target_bytes=target_bytes):
                payload = dict(original, grounded_snapshot={"has_progress": False, "synthetic_padding": ""})
                serialize = lambda value: json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
                if target_bytes is not None:
                    padding_bytes = target_bytes - len(serialize(payload).encode("utf-8"))
                    self.assertGreaterEqual(padding_bytes, 0)
                    payload["grounded_snapshot"]["synthetic_padding"] = "x" * padding_bytes
                serialized = serialize(payload)
                self.assertLessEqual(len(serialized), 12000)
                projected = ai_tutor.estimate_mirror_provider_budget(serialized_input=serialized, pricing=pricing, max_output_tokens=1000)
                service, store, provider, settings = companion_tests.LearningCompanionServiceHardeningTest.service_fixture(max_provider_input_chars=12000)
                settings.pricing = pricing
                settings.max_output_tokens = 1000
                settings.max_preflight_cost_micro_usd_per_request = 5000
                settings.max_in_flight_cost_micro_usd = 5000
                settings.max_project_cost_micro_usd_per_day = 25000
                settings.max_project_cost_micro_usd_per_month = 100000
                settings.retrospective_breaker_micro_usd_per_response = 5000
                if allowed:
                    self.assertLessEqual(projected.projected_cost_micro_usd, 5000)
                    await service.ask_mirror(user_id=1, payload=payload)
                    provider.generate_mirror.assert_awaited_once()
                    self.assertEqual(store.reserve_ai_usage.call_args.kwargs["projected_cost_micro_usd"], projected.projected_cost_micro_usd)
                else:
                    self.assertEqual(projected.projected_cost_micro_usd, 5001)
                    with self.assertRaises(AIQuotaExceeded):
                        await service.ask_mirror(user_id=1, payload=payload)
                    store.reserve_ai_usage.assert_not_called()
                    store.mark_ai_provider_attempt_started.assert_not_called()
                    provider.generate_mirror.assert_not_awaited()

    async def test_ac1_deep_provider_and_preflight_share_approved_output_ceiling(self):
        payload = companion_tests.LearningCompanionServiceHardeningTest().valid_payload()
        payload["question"] = "explain this grammar rule"
        payload["complexity_route"] = "deep"
        payload["is_continuation"] = False
        self.assertEqual(payload["complexity_route"], "deep")
        for configured, expected in ((1000, 1000), (700, 700), (1500, 1000)):
            with self.subTest(configured=configured):
                capture = response_tests.CaptureResponses()
                provider = ai_tutor.OpenAIResponsesProvider(
                    api_key="test-key", model="gpt-5.6-luna", service_tier="default",
                    safety_salt="recovery-test-safety-salt", max_output_tokens=configured,
                    client=SimpleNamespace(responses=capture),
                )
                await provider.generate_mirror(request_id="synthetic", user_id=1, payload=payload)
                self.assertEqual(capture.calls[-1]["max_output_tokens"], expected)
                service, store, _provider, settings = companion_tests.LearningCompanionServiceHardeningTest.service_fixture(max_provider_input_chars=12000)
                settings.max_output_tokens = configured
                with patch.object(ai_tutor, "estimate_mirror_provider_budget", wraps=ai_tutor.estimate_mirror_provider_budget) as estimate:
                    await service.ask_mirror(user_id=1, payload=payload)
                self.assertEqual(estimate.call_args.kwargs["max_output_tokens"], expected)
                store.complete_ai_usage.assert_called_once()

    async def test_err1_incomplete_provider_is_never_retried_or_billed(self):
        payload = companion_tests.LearningCompanionServiceHardeningTest().valid_payload()
        failed = ai_tutor.ProviderResult(answer=None, response_id="synthetic", model="test-model", status="incomplete", usage=ai_tutor.ProviderUsage(output_tokens=1000, reasoning_tokens=600))
        service, store, provider, _settings = companion_tests.LearningCompanionServiceHardeningTest.service_fixture(max_provider_input_chars=12000, provider_result=failed)
        with self.assertRaises(ai_tutor.AIProviderError):
            await service.ask_mirror(user_id=1, payload=payload)
        provider.generate_mirror.assert_awaited_once()
        store.complete_ai_usage.assert_not_called()
        store.fail_ai_usage.assert_called_once()
        store.record_ai_provider_response.assert_called_once()

    async def test_ac2_dictionary_is_a_fifth_localized_persistent_action(self):
        for locale in INTERFACE_LOCALES:
            label = f"📖 {translate('command_dictionary', locale)}"
            keyboard = bot.get_quick_actions_keyboard(locale)
            self.assertEqual(len([button for row in keyboard.keyboard for button in row]), 5)
            self.assertEqual(keyboard.keyboard[-1][0].text, label)
            self.assertEqual(bot.quick_action_for_text(label), "dictionary")
        update, context, _message = dictionary_tests.command_update([])
        update.message.text = "📖 Словарь"
        with patch.object(bot, "cmd_dictionary") as command:
            command.__wrapped__ = AsyncMock()
            await bot.handle_quick_action.__wrapped__(update, context)
            command.__wrapped__.assert_awaited_once_with(update, context)

    async def test_ac3_noarg_dictionary_has_identity_free_open_and_download_links(self):
        runtime = dictionary_tests.learner_runtime()
        update, context, message = dictionary_tests.command_update([])
        token = bot._ACTIVE_RUNTIME.set(runtime)
        try:
            with patch.object(bot, "MINIAPP_SETTINGS", replace(bot.MINIAPP_SETTINGS, enabled=True, public_url="https://dictionary.example/miniapp")):
                await bot.cmd_dictionary.__wrapped__(update, context)
        finally:
            bot._ACTIVE_RUNTIME.reset(token)
        self.assertIn(bot.PENDING_DICTIONARY_LOOKUP_KEY, context.user_data)
        markup = message.reply_text.await_args.kwargs.get("reply_markup")
        self.assertIsNotNone(markup)
        buttons = [button for row in markup.inline_keyboard for button in row]
        self.assertEqual(len(buttons), 2)
        self.assertEqual({urlsplit(button.url).path for button in buttons}, {"/dictionary/", "/dictionary/download"})
        for button in buttons:
            parsed = urlsplit(button.url)
            self.assertEqual(parsed.netloc, "dictionary.example")
            self.assertEqual(parse_qs(parsed.query), {"target": ["fr"], "native": ["ru"], "ui": ["ru"]})
            self.assertFalse(parsed.fragment)
            self.assertIsNone(button.web_app)

    async def test_err2_disabled_dictionary_keeps_typed_lookup_without_web_link(self):
        update, context, message = dictionary_tests.command_update([])
        with patch.object(bot, "MINIAPP_SETTINGS", replace(bot.MINIAPP_SETTINGS, enabled=False)):
            await bot.cmd_dictionary.__wrapped__(update, context)
        message.reply_text.assert_awaited_once_with(translate("dictionary_prompt", "ru"))

    async def test_ec1_dictionary_quick_action_works_with_noncommand_context(self):
        update, context, message = dictionary_tests.command_update([])
        context.args = None
        update.message.text = "📖 Словарь"
        with patch.object(bot, "MINIAPP_SETTINGS", replace(bot.MINIAPP_SETTINGS, enabled=False)):
            await bot.handle_quick_action.__wrapped__(update, context)
        message.reply_text.assert_awaited_once_with(translate("dictionary_prompt", "ru"))

    async def test_ec2_legacy_language_does_not_emit_a_broken_offline_link(self):
        runtime = dictionary_tests.learner_runtime(pack_id="ja-basics-100", active_language="ja")
        update, context, message = dictionary_tests.command_update([])
        token = bot._ACTIVE_RUNTIME.set(runtime)
        try:
            with patch.object(bot, "MINIAPP_SETTINGS", replace(bot.MINIAPP_SETTINGS, enabled=True, public_url="https://dictionary.example/miniapp")):
                await bot.cmd_dictionary.__wrapped__(update, context)
        finally:
            bot._ACTIVE_RUNTIME.reset(token)
        self.assertIsNone(message.reply_text.await_args.kwargs.get("reply_markup"))
        self.assertIn(translate("dictionary_offline_unsupported", "ru"), message.reply_text.await_args.args[0])

    async def test_ac6_retry_consumes_pending_question_once_and_never_bypasses_gates(self):
        update, context, message = dictionary_tests.command_update([])
        update.callback_query = SimpleNamespace(message=message, answer=AsyncMock())
        bot._remember_pending_ai_question(context, "explain this grammar rule")
        with patch.object(bot, "handle_mirror_question", new_callable=AsyncMock) as handler:
            await bot.mirror_retry_cb.__wrapped__(update, context)
            await bot.mirror_retry_cb.__wrapped__(update, context)
        handler.assert_awaited_once_with(update, context, question="explain this grammar rule")
        self.assertIsNone(bot._pending_ai_question(context))
        self.assertEqual(message.reply_text.await_args.args[0], translate("ai_tutor_pending_stale", "ru"))

    def test_ec3_explicit_plans_are_localized_and_do_not_capture_translation_questions(self):
        phrases = {"en": "plan for today", "fr": "plan pour aujourd’hui", "de": "Plan für heute", "ja": "今日の学習計画", "ar": "خطة اليوم", "zh": "今天的学习计划", "ru": "Составь план на сегодня!", "es": "plan para hoy"}
        for locale, question in phrases.items():
            self.assertEqual(bot.direct_mirror_daily_plan_locale(question), locale)
            rendered = bot.render_mirror_daily_plan({"due_count": 99}, locale=locale)
            self.assertIn(translate("companion_plan_review", locale, count=5), rendered)
            self.assertNotIn("99", rendered)
        self.assertIsNone(bot.direct_mirror_daily_plan_locale("translate 'plan for today' into German"))

    async def test_ac4_provider_and_quota_failures_offer_review_dictionary_and_retry(self):
        for failure in (ai_tutor.AIProviderError("private"), AIQuotaExceeded("private")):
            with self.subTest(failure=type(failure).__name__):
                update, context, message, _store, service, patches = response_tests.AIResponseHandlerContractTest().handler_fixture(locale="ru", question="объясни разницу времён", enabled=True, credits=3)
                service.ask.side_effect = failure
                with ExitStack() as stack:
                    for active_patch in patches:
                        stack.enter_context(active_patch)
                    await bot.handle_mirror_question(update, context, question="объясни разницу времён")
                final = message.reply_text.await_args
                self.assertEqual(final.args[0], translate("ai_unavailable_no_charge", "ru"))
                markup = final.kwargs.get("reply_markup")
                self.assertIsNotNone(markup)
                self.assertEqual({button.callback_data for row in markup.inline_keyboard for button in row}, {"start:review", "start:dictionary", "mirror:retry"})
                self.assertEqual(bot._pending_ai_question(context), "объясни разницу времён")

    async def test_err3_unknown_settlement_does_not_claim_no_charge(self):
        update, context, message, _store, service, patches = response_tests.AIResponseHandlerContractTest().handler_fixture(locale="ru", question="объясни разницу времён", enabled=True, credits=3)
        service.ask.side_effect = ai_tutor.AIUsageRecoveryError("private")
        with ExitStack() as stack:
            for active_patch in patches:
                stack.enter_context(active_patch)
            await bot.handle_mirror_question(update, context, question="объясни разницу времён")
        self.assertEqual(message.reply_text.await_args.args[0], translate("ai_failure", "ru"))
        self.assertNotIn(bot.PENDING_AI_QUESTION_KEY, context.user_data)

    async def test_ac5_explicit_daily_plan_is_free_useful_and_actionable(self):
        update, context, message, _store, service, patches = response_tests.AIResponseHandlerContractTest().handler_fixture(locale="ru", question="составь план на сегодня", enabled=False)
        with ExitStack() as stack:
            for active_patch in patches:
                stack.enter_context(active_patch)
            await bot.handle_mirror_question(update, context, question="составь план на сегодня")
        text = message.reply_text.await_args.args[0]
        self.assertIn("5 минут", text)
        self.assertIn("1.", text)
        self.assertIn("3.", text)
        service.ask.assert_not_awaited()
        self.assertIsNotNone(message.reply_text.await_args.kwargs.get("reply_markup"))
