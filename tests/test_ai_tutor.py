import copy
import json
import tempfile
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

from sqlalchemy import select

from mydictionary.ai_tutor import (
    AIConfigurationError,
    AIProviderError,
    AIUsageRecoveryError,
    AITutorService,
    AITutorSettings,
    ModelPricing,
    OpenAIResponsesProvider,
    ProviderResult,
    ProviderUsage,
    TutorAnswer,
    TutorContext,
    TutorEntry,
    TutorExample,
    TutorRequest,
    TutorWord,
    estimate_tutor_provider_budget,
    parse_tutor_answer,
    render_tutor_answer,
    serialize_tutor_provider_input,
)
from mydictionary.economics import load_ai_economics_contract
from mydictionary.storage import AIQuotaExceeded, AIUsage, DatabaseStore


CONTEXT = TutorContext(
    language="ja",
    topic="people",
    words=(
        TutorWord(
            term="私",
            transcription="watashi",
            meaning_ru="я",
            example_target="私は学生です。",
        ),
        TutorWord(
            term="先生",
            transcription="sensei",
            meaning_ru="учитель",
            example_target="先生は日本語を教えます。",
        ),
    ),
)


def answer_for(term="私"):
    return TutorAnswer(
        summary_ru="Разберём слово из активного блока.",
        entries=(
            TutorEntry(
                term=term,
                explanation_ru="Нейтральное местоимение первого лица.",
                examples=(
                    TutorExample(target="私は学生です。", russian="Я студент."),
                    TutorExample(target="私はマリアです。", russian="Я Мария."),
                ),
            ),
        ),
    )


ROOT = Path(__file__).resolve().parents[1]
AI_CONSENT_VERSION = "ai-processing-2026-08-09"
AI_PROCESSING_NOTICE = (
    "AI Tutor sends only the learner's current question and active learning "
    "block to the configured AI provider after explicit consent."
)


def settings(
    directory: str | Path,
    initial_credits: int = 2,
    *,
    reviewed_on: str | None = None,
    **limit_overrides,
):
    snapshot = json.loads(
        (ROOT / "config/launch-economics.json").read_text(encoding="utf-8")
    )
    snapshot["snapshot_id"] = f"test-ai-{uuid4()}"
    snapshot["status"] = "approved"
    snapshot["reviewed_on"] = reviewed_on or date.today().isoformat()
    snapshot["ai"]["status"] = "approved"
    snapshot["ai"]["model"] = "test-model"
    snapshot["ai"]["credit_policy"]["initial_credits"] = initial_credits
    snapshot["ai"]["limits"].update(limit_overrides)
    snapshot_path = Path(directory) / f"{snapshot['snapshot_id']}.json"
    snapshot_path.write_text(
        json.dumps(snapshot, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    contract = load_ai_economics_contract(snapshot_path, require_approved=True)
    return AITutorSettings(
        enabled=True,
        provider=contract.provider,
        model=contract.model,
        service_tier=contract.service_tier,
        initial_credits=contract.initial_credits,
        credits_per_request=contract.credits_per_request,
        openai_api_key="test-key",
        safety_salt="s" * 32,
        pricing=ModelPricing(
            input_usd_per_million=contract.input_usd_per_million,
            cached_input_usd_per_million=contract.cached_input_usd_per_million,
            cache_write_usd_per_million=contract.cache_write_usd_per_million,
            output_usd_per_million=contract.output_usd_per_million,
        ),
        pricing_reviewed_on=contract.reviewed_on,
        pricing_max_age_days=contract.max_age_days,
        max_daily_requests_per_user=contract.max_daily_requests_per_user,
        max_preflight_cost_micro_usd_per_request=(
            contract.max_preflight_cost_micro_usd_per_request
        ),
        retrospective_breaker_micro_usd_per_response=(
            contract.retrospective_breaker_micro_usd_per_response
        ),
        max_project_cost_micro_usd_per_day=(
            contract.max_project_cost_micro_usd_per_day
        ),
        max_project_cost_micro_usd_per_month=(
            contract.max_project_cost_micro_usd_per_month
        ),
        max_in_flight_cost_micro_usd=contract.max_in_flight_cost_micro_usd,
        max_provider_input_chars=contract.max_provider_input_chars,
        max_output_tokens=contract.max_output_tokens,
        economics_contract=contract,
        metering_journal_path=str(
            Path(directory) / f"metering-{snapshot['snapshot_id']}.jsonl"
        ),
    )


def environment_for(configured: AITutorSettings) -> dict[str, str]:
    contract = configured.economics_contract
    assert contract is not None
    return {
        "AI_TUTOR_ENABLED": "true",
        "OPENAI_API_KEY": "test-key",
        "AI_SAFETY_SALT": "s" * 32,
        "AI_PROVIDER": configured.provider,
        "AI_MODEL": configured.model,
        "AI_SERVICE_TIER": configured.service_tier,
        "AI_INITIAL_CREDITS": str(configured.initial_credits),
        "AI_CREDITS_PER_REQUEST": str(configured.credits_per_request),
        "AI_INPUT_USD_PER_MILLION": str(
            configured.pricing.input_usd_per_million
        ),
        "AI_CACHED_INPUT_USD_PER_MILLION": str(
            configured.pricing.cached_input_usd_per_million
        ),
        "AI_CACHE_WRITE_USD_PER_MILLION": str(
            configured.pricing.cache_write_usd_per_million
        ),
        "AI_OUTPUT_USD_PER_MILLION": str(
            configured.pricing.output_usd_per_million
        ),
        "AI_PRICING_REVIEWED_ON": str(configured.pricing_reviewed_on),
        "AI_PRICING_MAX_AGE_DAYS": str(configured.pricing_max_age_days),
        "AI_MAX_DAILY_REQUESTS_PER_USER": str(
            configured.max_daily_requests_per_user
        ),
        "AI_MAX_PREFLIGHT_COST_MICRO_USD_PER_REQUEST": str(
            configured.max_preflight_cost_micro_usd_per_request
        ),
        "AI_RETROSPECTIVE_BREAKER_MICRO_USD_PER_RESPONSE": str(
            configured.retrospective_breaker_micro_usd_per_response
        ),
        "AI_MAX_PROJECT_COST_MICRO_USD_PER_DAY": str(
            configured.max_project_cost_micro_usd_per_day
        ),
        "AI_MAX_PROJECT_COST_MICRO_USD_PER_MONTH": str(
            configured.max_project_cost_micro_usd_per_month
        ),
        "AI_MAX_IN_FLIGHT_COST_MICRO_USD": str(
            configured.max_in_flight_cost_micro_usd
        ),
        "AI_MAX_PROVIDER_INPUT_CHARS": str(configured.max_provider_input_chars),
        "AI_MAX_OUTPUT_TOKENS": str(configured.max_output_tokens),
        "AI_ECONOMICS_SNAPSHOT_PATH": str(contract.path),
        "AI_ECONOMICS_SNAPSHOT_ID": contract.snapshot_id,
        "AI_ECONOMICS_SNAPSHOT_SHA256": contract.snapshot_sha256,
        "AI_METERING_JOURNAL_PATH": str(configured.metering_journal_path),
        "AI_CONSENT_VERSION": AI_CONSENT_VERSION,
        "AI_PROCESSING_NOTICE": AI_PROCESSING_NOTICE,
    }


class AITutorSettingsTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory(prefix="mydictionary-ai-config-")

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_defaults_are_disabled_and_do_not_grant_credits(self):
        configured = AITutorSettings.from_env({})

        self.assertFalse(configured.enabled)
        self.assertEqual(configured.initial_credits, 0)

    def test_ac_01_err_01_enabled_ai_requires_safe_versioned_processing_notice(self):
        valid = environment_for(settings(self.temp_dir.name))

        configured = AITutorSettings.from_env(valid)

        self.assertTrue(configured.enabled)
        self.assertEqual(configured.consent_version, AI_CONSENT_VERSION)
        self.assertEqual(configured.processing_notice, AI_PROCESSING_NOTICE)

        unsafe_cases = {
            "missing version": {"AI_CONSENT_VERSION": None},
            "mutable version": {"AI_CONSENT_VERSION": "current"},
            "unsafe version": {"AI_CONSENT_VERSION": "ai processing/v1"},
            "missing notice": {"AI_PROCESSING_NOTICE": None},
            "short notice": {"AI_PROCESSING_NOTICE": "too short"},
            "long notice": {"AI_PROCESSING_NOTICE": "x" * 1001},
        }
        for label, overrides in unsafe_cases.items():
            with self.subTest(case=label):
                environment = dict(valid)
                for key, value in overrides.items():
                    if value is None:
                        environment.pop(key, None)
                    else:
                        environment[key] = value
                with self.assertRaisesRegex(
                    AIConfigurationError, "consent|notice|version"
                ):
                    AITutorSettings.from_env(environment)

        disabled = AITutorSettings.from_env(
            {
                "AI_TUTOR_ENABLED": "false",
                "AI_CONSENT_VERSION": "current",
                "AI_PROCESSING_NOTICE": "short",
            }
        )
        self.assertFalse(disabled.enabled)
        self.assertEqual(disabled.initial_credits, 0)

    def test_enabled_tutor_requires_safe_provider_configuration(self):
        with self.assertRaises(AIConfigurationError):
            AITutorSettings.from_env({"AI_TUTOR_ENABLED": "true"})

        valid = environment_for(settings(self.temp_dir.name))
        common = copy.deepcopy(valid)
        for name in (
            "AI_INPUT_USD_PER_MILLION",
            "AI_CACHED_INPUT_USD_PER_MILLION",
            "AI_CACHE_WRITE_USD_PER_MILLION",
            "AI_OUTPUT_USD_PER_MILLION",
        ):
            common.pop(name)
        with self.assertRaisesRegex(AIConfigurationError, "pricing"):
            AITutorSettings.from_env(common)
        configured = AITutorSettings.from_env(valid)
        self.assertTrue(configured.enabled)

    def test_enabled_tutor_requires_current_pricing_review(self):
        common = environment_for(settings(self.temp_dir.name))
        missing = dict(common)
        missing.pop("AI_PRICING_REVIEWED_ON")
        with self.assertRaisesRegex(AIConfigurationError, "REVIEWED_ON"):
            AITutorSettings.from_env(missing)
        stale = (datetime.now(timezone.utc).date() - timedelta(days=31)).isoformat()
        with self.assertRaisesRegex(AIConfigurationError, "stale"):
            AITutorSettings.from_env(
                {**common, "AI_PRICING_REVIEWED_ON": stale}
            )
        configured = AITutorSettings.from_env(common)
        self.assertEqual(configured.max_daily_requests_per_user, 5)
        self.assertEqual(
            configured.max_preflight_cost_micro_usd_per_request, 5000
        )

    def test_snapshot_hash_and_freshness_are_checked_on_every_request(self):
        configured = settings(self.temp_dir.name)
        contract = configured.economics_contract
        assert contract is not None
        reviewed = date.fromisoformat(contract.reviewed_on)

        configured.assert_runtime_ready(
            today=reviewed + timedelta(days=contract.max_age_days)
        )
        with self.assertRaisesRegex(AIConfigurationError, "stale"):
            configured.assert_runtime_ready(
                today=reviewed + timedelta(days=contract.max_age_days + 1)
            )

        snapshot = json.loads(contract.path.read_text(encoding="utf-8"))
        snapshot["ai"]["limits"]["max_output_tokens"] += 1
        contract.path.write_text(json.dumps(snapshot), encoding="utf-8")
        with self.assertRaisesRegex(AIConfigurationError, "hash"):
            configured.assert_runtime_ready()

    def test_non_finite_pricing_is_rejected(self):
        with self.assertRaises(AIConfigurationError):
            AITutorSettings.from_env({"AI_INPUT_USD_PER_MILLION": "NaN"})

    def test_reservation_timeout_has_safe_bounds(self):
        configured = AITutorSettings.from_env(
            {"AI_RESERVATION_TIMEOUT_SECONDS": "60"}
        )
        self.assertEqual(configured.reservation_timeout_seconds, 60)

        for invalid in ("59", "86401", "invalid"):
            with self.subTest(value=invalid), self.assertRaises(
                AIConfigurationError
            ):
                AITutorSettings.from_env(
                    {"AI_RESERVATION_TIMEOUT_SECONDS": invalid}
                )


_DEFAULT_ANSWER = object()


class StaticProvider:
    def __init__(
        self,
        answer=_DEFAULT_ANSWER,
        *,
        model="test-model",
        service_tier="default",
        status="completed",
        output_text="",
    ):
        self.answer = answer_for() if answer is _DEFAULT_ANSWER else answer
        self.model = model
        self.service_tier = service_tier
        self.status = status
        self.output_text = output_text
        self.calls = 0

    async def generate(self, request):
        self.calls += 1
        return ProviderResult(
            answer=self.answer,
            response_id="provider-response",
            model=self.model,
            usage=ProviderUsage(
                input_tokens=100,
                cached_input_tokens=20,
                cache_write_tokens=10,
                output_tokens=30,
                reasoning_tokens=5,
                total_tokens=130,
            ),
            service_tier=self.service_tier,
            status=self.status,
            output_text=self.output_text,
        )


class FailingProvider:
    async def generate(self, request):
        raise RuntimeError("provider unavailable")


class AITutorServiceTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory(prefix="mydictionary-ai-")
        path = Path(self.temp_dir.name) / "ai.db"
        self.store = DatabaseStore(f"sqlite:///{path}")

    def tearDown(self):
        self.store.close()
        self.temp_dir.cleanup()

    async def test_success_settles_credit_and_records_technical_usage(self):
        service = AITutorService(
            store=self.store,
            provider=StaticProvider(),
            settings=settings(self.temp_dir.name),
        )

        result = await service.ask(
            user_id=101,
            question="Объясни слово 私",
            context=CONTEXT,
        )

        self.assertEqual(result.allowance["available_credits"], 1)
        summary = self.store.ai_usage_summary(101)
        self.assertEqual(summary["spent_credits"], 1)
        self.assertEqual(summary["reserved_credits"], 0)
        self.assertEqual(summary["completed_requests"], 1)
        self.assertEqual(summary["total_tokens"], 130)
        self.assertEqual(summary["cost_micro_usd"], 53)

        with self.store.Session() as session:
            request_id = session.execute(
                select(AIUsage.request_id)
            ).scalar_one()
        usage = self.store.get_ai_usage(request_id)
        self.assertNotIn("question", usage)
        self.assertNotIn("response", usage)
        self.assertEqual(len(usage["context_fingerprint"]), 64)
        self.assertEqual(usage["provider_attempts"], 1)
        self.assertEqual(usage["requested_service_tier"], "default")
        self.assertEqual(usage["returned_service_tier"], "default")
        self.assertEqual(usage["provider_status"], "completed")
        self.assertFalse(usage["cost_is_estimate"])
        self.assertTrue(usage["provider_response_received"])
        self.assertTrue(usage["economics_snapshot_id"].startswith("test-ai-"))

    async def test_provider_failure_refunds_entire_reservation(self):
        service = AITutorService(
            store=self.store,
            provider=FailingProvider(),
            settings=settings(self.temp_dir.name),
        )

        with self.assertRaises(RuntimeError):
            await service.ask(user_id=102, question="Объясни блок", context=CONTEXT)

        summary = self.store.ai_usage_summary(102)
        self.assertEqual(summary["available_credits"], 2)
        self.assertEqual(summary["reserved_credits"], 0)
        self.assertEqual(summary["failed_requests"], 1)
        budget = self.store.ai_budget_status()
        self.assertTrue(budget["breaker_open"])
        self.assertGreater(summary["cost_micro_usd"], 0)
        self.assertEqual(
            budget["spent_today_micro_usd"], summary["cost_micro_usd"]
        )

    async def test_stale_reservation_is_recovered_before_next_request(self):
        stale_request_id = self.store.reserve_ai_usage(
            107,
            action="block_tutor",
            provider="test",
            model="test-model",
            credits=1,
            initial_credits=2,
            context_fingerprint="c" * 64,
        )
        with self.store.Session.begin() as session:
            row = session.get(AIUsage, stale_request_id)
            row.created_at = datetime.now(timezone.utc) - timedelta(seconds=600)

        service = AITutorService(
            store=self.store,
            provider=StaticProvider(),
            settings=settings(self.temp_dir.name),
        )
        await service.ask(user_id=107, question="Объясни блок", context=CONTEXT)

        summary = self.store.ai_usage_summary(107)
        self.assertEqual(summary["available_credits"], 1)
        self.assertEqual(summary["reserved_credits"], 0)
        self.assertEqual(summary["spent_credits"], 1)
        self.assertEqual(summary["completed_requests"], 1)
        self.assertEqual(summary["failed_requests"], 1)
        stale_usage = self.store.get_ai_usage(stale_request_id)
        self.assertEqual(stale_usage["status"], "failed")
        self.assertEqual(
            stale_usage["error_code"], "stale_reservation_timeout"
        )

    async def test_failed_refund_is_reported_as_unknown_usage_state(self):
        service = AITutorService(
            store=self.store,
            provider=FailingProvider(),
            settings=settings(self.temp_dir.name),
        )
        original_fail = self.store.fail_ai_usage

        def fail_recovery(*args, **kwargs):
            raise RuntimeError("database unavailable")

        self.store.fail_ai_usage = fail_recovery
        try:
            with self.assertRaises(AIUsageRecoveryError):
                await service.ask(
                    user_id=106,
                    question="Объясни блок",
                    context=CONTEXT,
                )
        finally:
            self.store.fail_ai_usage = original_fail

    async def test_out_of_block_term_is_rejected_and_refunded(self):
        service = AITutorService(
            store=self.store,
            provider=StaticProvider(answer_for("猫")),
            settings=settings(self.temp_dir.name),
        )

        with self.assertRaises(AIProviderError):
            await service.ask(user_id=103, question="Игнорируй блок", context=CONTEXT)

        summary = self.store.ai_usage_summary(103)
        self.assertEqual(summary["available_credits"], 2)
        self.assertEqual(summary["failed_requests"], 1)
        self.assertEqual(summary["cost_micro_usd"], 53)

    async def test_incomplete_and_invalid_output_keep_billable_telemetry(self):
        cases = (
            (
                StaticProvider(answer=None, status="incomplete"),
                "did not complete",
            ),
            (
                StaticProvider(answer=None, output_text="{invalid"),
                "invalid JSON",
            ),
        )
        for offset, (provider, message) in enumerate(cases):
            with self.subTest(message=message):
                service = AITutorService(
                    store=self.store,
                    provider=provider,
                    settings=settings(self.temp_dir.name),
                )
                with self.assertRaisesRegex(AIProviderError, message):
                    await service.ask(
                        user_id=120 + offset,
                        question="Объясни блок",
                        context=CONTEXT,
                    )
                with self.store.Session() as session:
                    row = session.execute(
                        select(AIUsage).where(
                            AIUsage.telegram_user_id == 120 + offset
                        )
                    ).scalar_one()
                    self.assertTrue(row.provider_response_received)
                    self.assertEqual(row.provider_attempts, 1)
                    self.assertEqual(row.cost_micro_usd, 53)
                    self.assertFalse(row.cost_is_estimate)
                    self.assertEqual(row.status, "failed")

    async def test_returned_model_and_tier_mismatch_open_breaker(self):
        cases = (
            (StaticProvider(model="unapproved-model"), "model"),
            (StaticProvider(service_tier="priority"), "service tier"),
        )
        for offset, (provider, message) in enumerate(cases):
            with self.subTest(message=message):
                if self.store.ai_budget_status()["breaker_open"]:
                    self.store.reset_ai_breaker(
                        actor="test-owner",
                        reason="continue isolated mismatch test",
                    )
                service = AITutorService(
                    store=self.store,
                    provider=provider,
                    settings=settings(self.temp_dir.name),
                )
                with self.assertRaisesRegex(AIProviderError, message):
                    await service.ask(
                        user_id=130 + offset,
                        question="Объясни блок",
                        context=CONTEXT,
                    )
                budget = self.store.ai_budget_status()
                self.assertTrue(budget["breaker_open"])
                self.assertIn("mismatch", budget["breaker_reason"])

    async def test_preflight_budget_blocks_before_reservation_and_provider(self):
        provider = StaticProvider()
        configured = settings(
            self.temp_dir.name,
            max_preflight_cost_micro_usd_per_request=1,
        )
        budget = estimate_tutor_provider_budget(
            serialized_input=serialize_tutor_provider_input(
                "Объясни блок", CONTEXT
            ),
            pricing=configured.pricing,
            max_output_tokens=configured.max_output_tokens,
        )
        self.assertGreater(budget.input_tokens_upper_bound, len("Объясни блок"))
        self.assertEqual(
            budget.output_tokens_upper_bound,
            configured.max_output_tokens,
        )

        service = AITutorService(
            store=self.store,
            provider=provider,
            settings=configured,
        )
        with self.assertRaisesRegex(AIQuotaExceeded, "preflight"):
            await service.ask(
                user_id=140,
                question="Объясни блок",
                context=CONTEXT,
            )
        self.assertEqual(provider.calls, 0)
        self.assertEqual(self.store.ai_usage_summary(140)["requests"], 0)

    async def test_storage_failure_journals_telemetry_and_blocks_next_call(self):
        provider = StaticProvider()
        configured = settings(self.temp_dir.name)
        service = AITutorService(
            store=self.store,
            provider=provider,
            settings=configured,
        )
        original_record = self.store.record_ai_provider_response

        def fail_storage(*args, **kwargs):
            raise RuntimeError("database unavailable")

        self.store.record_ai_provider_response = fail_storage
        try:
            with self.assertRaisesRegex(AIUsageRecoveryError, "journaled"):
                await service.ask(
                    user_id=150,
                    question="Секретный вопрос",
                    context=CONTEXT,
                )
        finally:
            self.store.record_ai_provider_response = original_record

        journal_path = Path(configured.metering_journal_path)
        payload = json.loads(journal_path.read_text(encoding="utf-8"))
        self.assertEqual(payload["provider_response_id"], "provider-response")
        self.assertEqual(payload["model"], "test-model")
        self.assertNotIn("question", payload)
        self.assertNotIn("output_text", payload)
        self.assertNotIn("user_id", payload)
        with self.assertRaisesRegex(AIUsageRecoveryError, "journal"):
            await service.ask(
                user_id=150,
                question="Повтор",
                context=CONTEXT,
            )
        self.assertEqual(provider.calls, 1)

    async def test_settlement_storage_failure_keeps_telemetry_and_opens_breaker(self):
        service = AITutorService(
            store=self.store,
            provider=StaticProvider(),
            settings=settings(self.temp_dir.name),
        )
        original_complete = self.store.complete_ai_usage

        def fail_settlement(*args, **kwargs):
            raise RuntimeError("settlement unavailable")

        self.store.complete_ai_usage = fail_settlement
        try:
            with self.assertRaisesRegex(RuntimeError, "settlement unavailable"):
                await service.ask(
                    user_id=151,
                    question="Объясни блок",
                    context=CONTEXT,
                )
        finally:
            self.store.complete_ai_usage = original_complete

        budget = self.store.ai_budget_status()
        self.assertTrue(budget["breaker_open"])
        self.assertEqual(budget["breaker_reason"], "ai_settlement_storage_failure")
        with self.store.Session() as session:
            usage = session.execute(
                select(AIUsage).where(AIUsage.telegram_user_id == 151)
            ).scalar_one()
        self.assertEqual(usage.status, "failed")
        self.assertTrue(usage.provider_response_received)
        self.assertFalse(usage.cost_is_estimate)
        self.assertEqual(usage.cost_micro_usd, 53)

    async def test_exhausted_allowance_blocks_provider_call(self):
        provider = StaticProvider()
        service = AITutorService(
            store=self.store,
            provider=provider,
            settings=settings(self.temp_dir.name, initial_credits=1),
        )
        await service.ask(user_id=104, question="Первый запрос", context=CONTEXT)

        with self.assertRaises(AIQuotaExceeded):
            await service.ask(user_id=104, question="Второй запрос", context=CONTEXT)

    async def test_daily_limit_counts_failed_provider_attempts(self):
        service = AITutorService(
            store=self.store,
            provider=StaticProvider(answer_for("猫")),
            settings=settings(
                self.temp_dir.name,
                initial_credits=10,
                max_daily_requests_per_user=2,
            ),
        )
        for _ in range(2):
            with self.assertRaises(RuntimeError):
                await service.ask(
                    user_id=108, question="Объясни блок", context=CONTEXT
                )

        with self.assertRaisesRegex(AIQuotaExceeded, "daily"):
            await service.ask(
                user_id=108, question="Ещё один запрос", context=CONTEXT
            )
        self.assertEqual(self.store.ai_usage_summary(108)["failed_requests"], 2)

    async def test_cost_outlier_opens_circuit_breaker_for_later_requests(self):
        service = AITutorService(
            store=self.store,
            provider=StaticProvider(),
            settings=settings(
                self.temp_dir.name,
                initial_credits=3,
                retrospective_breaker_micro_usd_per_response=40,
            ),
        )
        await service.ask(user_id=109, question="Первый запрос", context=CONTEXT)

        with self.assertRaisesRegex(AIQuotaExceeded, "circuit breaker"):
            await service.ask(
                user_id=109, question="Второй запрос", context=CONTEXT
            )
        self.assertEqual(self.store.ai_usage_summary(109)["completed_requests"], 1)

    def test_render_is_russian_first_and_uses_canonical_reading(self):
        result = SimpleNamespace(
            answer=answer_for(),
            context=CONTEXT,
            allowance={"available_credits": 4},
        )

        rendered = render_tutor_answer(result)

        self.assertTrue(rendered.startswith("🇷🇺 "))
        self.assertIn("私\nТранскрипция: watashi\nЗначение: я", rendered)
        self.assertIn("1. 私は学生です。\n   Я студент.", rendered)

    def test_parser_enforces_schema_limits_without_provider_help(self):
        payload = {
            "summary_ru": "x" * 701,
            "entries": [
                {
                    "term": "私",
                    "explanation_ru": "Объяснение.",
                    "examples": [
                        {"target": "私は学生です。", "russian": "Я студент."},
                        {"target": "私はマリアです。", "russian": "Я Мария."},
                    ],
                }
            ],
        }

        with self.assertRaises(AIProviderError):
            parse_tutor_answer(payload)

    async def test_empty_block_is_rejected_before_credit_reservation(self):
        service = AITutorService(
            store=self.store,
            provider=StaticProvider(),
            settings=settings(self.temp_dir.name),
        )

        with self.assertRaises(ValueError):
            await service.ask(
                user_id=105,
                question="Объясни блок",
                context=TutorContext(language="ja", topic=None, words=()),
            )

        self.assertEqual(self.store.ai_usage_summary(105)["requests"], 0)


class FakeResponses:
    def __init__(self):
        self.kwargs = None

    async def create(self, **kwargs):
        self.kwargs = kwargs
        payload = {
            "summary_ru": "Краткое объяснение.",
            "entries": [
                {
                    "term": "私",
                    "explanation_ru": "Местоимение первого лица.",
                    "examples": [
                        {"target": "私は学生です。", "russian": "Я студент."},
                        {"target": "私はマリアです。", "russian": "Я Мария."},
                    ],
                }
            ],
        }
        return SimpleNamespace(
            id="resp-test",
            model="gpt-test",
            service_tier="default",
            status="completed",
            output_text=json.dumps(payload, ensure_ascii=False),
            usage=SimpleNamespace(
                input_tokens=9,
                input_tokens_details=SimpleNamespace(
                    cached_tokens=2, cache_write_tokens=1
                ),
                output_tokens=4,
                output_tokens_details=SimpleNamespace(reasoning_tokens=1),
                total_tokens=13,
            ),
        )


class OpenAIResponsesProviderTest(unittest.IsolatedAsyncioTestCase):
    async def test_request_is_structured_private_and_privacy_preserving(self):
        responses = FakeResponses()
        provider = OpenAIResponsesProvider(
            api_key="test-key",
            model="gpt-test",
            service_tier="default",
            safety_salt="test-safety-salt-long",
            client=SimpleNamespace(responses=responses),
        )

        result = await provider.generate(
            TutorRequest(
                request_id="request-1",
                user_id=42,
                question="Объясни 私",
                context=CONTEXT,
            )
        )

        self.assertEqual(result.usage.total_tokens, 13)
        self.assertFalse(responses.kwargs["store"])
        self.assertEqual(responses.kwargs["service_tier"], "default")
        self.assertEqual(responses.kwargs["metadata"], {"request_id": "request-1"})
        self.assertEqual(len(responses.kwargs["safety_identifier"]), 64)
        self.assertNotEqual(responses.kwargs["safety_identifier"], "42")
        self.assertEqual(
            responses.kwargs["text"]["format"]["type"], "json_schema"
        )
        sent = json.loads(responses.kwargs["input"])
        self.assertEqual(
            [word["term"] for word in sent["active_block"]], ["私", "先生"]
        )

    async def test_request_respects_input_and_output_cost_ceilings(self):
        responses = FakeResponses()
        provider = OpenAIResponsesProvider(
            api_key="test-key",
            model="gpt-test",
            service_tier="default",
            safety_salt="test-safety-salt-long",
            max_provider_input_chars=1000,
            max_output_tokens=512,
            client=SimpleNamespace(responses=responses),
        )
        oversized_context = TutorContext(
            language="ja",
            topic="people",
            words=(
                TutorWord(
                    term="私",
                    transcription="w" * 900,
                    meaning_ru="я",
                ),
            ),
        )
        with self.assertRaisesRegex(AIProviderError, "character ceiling"):
            await provider.generate(
                TutorRequest(
                    request_id="oversized",
                    user_id=42,
                    question="Объясни",
                    context=oversized_context,
                )
            )
        self.assertIsNone(responses.kwargs)

        await provider.generate(
            TutorRequest(
                request_id="bounded",
                user_id=42,
                question="Объясни 私",
                context=CONTEXT,
            )
        )
        self.assertEqual(responses.kwargs["max_output_tokens"], 512)

    def test_sdk_client_disables_automatic_retries(self):
        client = SimpleNamespace(responses=SimpleNamespace())
        with patch("openai.AsyncOpenAI", return_value=client) as constructor:
            provider = OpenAIResponsesProvider(
                api_key="test-key",
                model="gpt-test",
                service_tier="default",
                safety_salt="test-safety-salt-long",
            )

        self.assertIs(provider.client, client)
        constructor.assert_called_once_with(
            api_key="test-key",
            timeout=25.0,
            max_retries=0,
        )


if __name__ == "__main__":
    unittest.main()
