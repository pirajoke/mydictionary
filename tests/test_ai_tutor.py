import json
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

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
    parse_tutor_answer,
    render_tutor_answer,
)
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


def settings(initial_credits=2):
    return AITutorSettings(
        enabled=True,
        provider="test",
        model="test-model",
        initial_credits=initial_credits,
        credits_per_request=1,
        openai_api_key=None,
        safety_salt=None,
        pricing=ModelPricing(
            input_usd_per_million=Decimal("2"),
            cached_input_usd_per_million=Decimal("0.5"),
            cache_write_usd_per_million=Decimal("2.5"),
            output_usd_per_million=Decimal("10"),
        ),
    )


class AITutorSettingsTest(unittest.TestCase):
    def test_defaults_are_disabled_and_do_not_grant_credits(self):
        configured = AITutorSettings.from_env({})

        self.assertFalse(configured.enabled)
        self.assertEqual(configured.initial_credits, 0)

    def test_enabled_tutor_requires_safe_provider_configuration(self):
        with self.assertRaises(AIConfigurationError):
            AITutorSettings.from_env({"AI_TUTOR_ENABLED": "true"})

    def test_non_finite_pricing_is_rejected(self):
        with self.assertRaises(AIConfigurationError):
            AITutorSettings.from_env({"AI_INPUT_USD_PER_MILLION": "NaN"})


class StaticProvider:
    def __init__(self, answer=None):
        self.answer = answer or answer_for()

    async def generate(self, request):
        return ProviderResult(
            answer=self.answer,
            response_id="provider-response",
            model="provider-model",
            usage=ProviderUsage(
                input_tokens=100,
                cached_input_tokens=20,
                cache_write_tokens=10,
                output_tokens=30,
                reasoning_tokens=5,
                total_tokens=130,
            ),
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
            settings=settings(),
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
        self.assertEqual(summary["cost_micro_usd"], 475)

        with self.store.Session() as session:
            request_id = session.execute(
                select(AIUsage.request_id)
            ).scalar_one()
        usage = self.store.get_ai_usage(request_id)
        self.assertNotIn("question", usage)
        self.assertNotIn("response", usage)
        self.assertEqual(len(usage["context_fingerprint"]), 64)

    async def test_provider_failure_refunds_entire_reservation(self):
        service = AITutorService(
            store=self.store,
            provider=FailingProvider(),
            settings=settings(),
        )

        with self.assertRaises(RuntimeError):
            await service.ask(user_id=102, question="Объясни блок", context=CONTEXT)

        summary = self.store.ai_usage_summary(102)
        self.assertEqual(summary["available_credits"], 2)
        self.assertEqual(summary["reserved_credits"], 0)
        self.assertEqual(summary["failed_requests"], 1)

    async def test_failed_refund_is_reported_as_unknown_usage_state(self):
        service = AITutorService(
            store=self.store,
            provider=FailingProvider(),
            settings=settings(),
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
            settings=settings(),
        )

        with self.assertRaises(AIProviderError):
            await service.ask(user_id=103, question="Игнорируй блок", context=CONTEXT)

        summary = self.store.ai_usage_summary(103)
        self.assertEqual(summary["available_credits"], 2)
        self.assertEqual(summary["failed_requests"], 1)

    async def test_exhausted_allowance_blocks_provider_call(self):
        provider = StaticProvider()
        service = AITutorService(
            store=self.store,
            provider=provider,
            settings=settings(initial_credits=1),
        )
        await service.ask(user_id=104, question="Первый запрос", context=CONTEXT)

        with self.assertRaises(AIQuotaExceeded):
            await service.ask(user_id=104, question="Второй запрос", context=CONTEXT)

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
            settings=settings(),
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


if __name__ == "__main__":
    unittest.main()
