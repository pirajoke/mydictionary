import copy
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import tempfile
import unittest

try:
    from ops import mydictionary_ai_smoke as smoke
except ImportError:
    smoke = None


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "ai_tutor_eval.json"
APPROVAL = "synthetic-ai-pilot-v1"


class FakeProvider:
    def __init__(self, result=None, error=None):
        self.calls = []
        self.error = error
        cases = json.loads(FIXTURE.read_text(encoding="utf-8"))
        self.result = result or {
            "model": "gpt-5.6-luna",
            "service_tier": "default",
            "status": "completed",
            "structured_output": {
                "cases": [
                    {
                        "id": case["id"],
                        "term": case["term"],
                        "summary_ru": case["summary_ru"],
                        "explanation_ru": case["explanation_ru"],
                        "examples": case["examples"],
                    }
                    for case in cases
                ]
            },
            "usage": {
                "input_tokens": 100,
                "cached_input_tokens": 20,
                "cache_write_tokens": 10,
                "output_tokens": 30,
                "total_tokens": 130,
            },
            "cost_micro_usd": 53,
            "latency_ms": 250,
        }

    async def __call__(self, request):
        self.calls.append(request)
        if self.error is not None:
            raise self.error
        return copy.deepcopy(self.result)


class AILiveSmokeTest(unittest.IsolatedAsyncioTestCase):
    def require_smoke(self):
        self.assertIsNotNone(
            smoke,
            "public module ops.mydictionary_ai_smoke is required by AC-08",
        )
        return smoke

    def environment(self, root: Path):
        return {
            "AI_TUTOR_ENABLED": "false",
            "VOICE_TUTOR_ENABLED": "false",
            "TELEGRAM_STARS_ENABLED": "false",
            "AI_MODEL": "gpt-5.6-luna",
            "AI_SERVICE_TIER": "default",
            "AI_INPUT_USD_PER_MILLION": "0.20",
            "AI_CACHED_INPUT_USD_PER_MILLION": "0.02",
            "AI_CACHE_WRITE_USD_PER_MILLION": "0.25",
            "AI_OUTPUT_USD_PER_MILLION": "1.20",
            "AI_MAX_PREFLIGHT_COST_MICRO_USD_PER_REQUEST": "5000",
            "AI_SYNTHETIC_SMOKE_APPROVAL": APPROVAL,
            "OPENAI_API_KEY": "test-secret-key",
            "AI_SAFETY_SALT": "s" * 32,
            "AI_SYNTHETIC_SMOKE_RUNS_DIR": str(root / "runs"),
        }

    async def test_ac_08_preview_is_default_and_never_calls_provider(self):
        api = self.require_smoke()
        with tempfile.TemporaryDirectory(prefix="ai-smoke-preview-") as raw:
            root = Path(raw)
            provider = FakeProvider()
            result = await api.run_smoke(
                environment=self.environment(root),
                provider=provider,
                fixture_path=FIXTURE,
                receipt_path=root / "receipt.json",
                run_id="preview-20260809",
            )

            self.assertEqual(result["status"], "preview")
            self.assertEqual(provider.calls, [])
            self.assertFalse((root / "receipt.json").exists())
            self.assertNotIn("test-secret-key", repr(result))

        parser = api.parser()
        self.assertFalse(parser.parse_args([]).execute)

    async def test_ac_08_execute_requires_exact_approval_gate(self):
        api = self.require_smoke()
        for approval in (None, "true", "approved", APPROVAL + "-typo"):
            with self.subTest(approval=approval), tempfile.TemporaryDirectory(
                prefix="ai-smoke-gate-"
            ) as raw:
                root = Path(raw)
                environment = self.environment(root)
                if approval is None:
                    environment.pop("AI_SYNTHETIC_SMOKE_APPROVAL")
                else:
                    environment["AI_SYNTHETIC_SMOKE_APPROVAL"] = approval
                provider = FakeProvider()
                with self.assertRaises(api.AISmokeConfigurationError):
                    await api.run_smoke(
                        environment=environment,
                        provider=provider,
                        fixture_path=FIXTURE,
                        receipt_path=root / "receipt.json",
                        run_id="gate-20260809",
                        execute=True,
                    )
                self.assertEqual(provider.calls, [])

    async def test_ac_09_execute_uses_one_fixed_anonymous_grounded_request(self):
        api = self.require_smoke()
        with tempfile.TemporaryDirectory(prefix="ai-smoke-execute-") as raw:
            root = Path(raw)
            environment = self.environment(root)
            provider = FakeProvider()

            result = await api.run_smoke(
                environment=environment,
                provider=provider,
                fixture_path=FIXTURE,
                receipt_path=root / "receipt.json",
                run_id="execute-20260809",
                execute=True,
                now=datetime(2026, 8, 9, 12, 0, tzinfo=timezone.utc),
            )

        self.assertEqual(len(provider.calls), 1)
        request = provider.calls[0]
        self.assertEqual(request["model"], "gpt-5.6-luna")
        self.assertEqual(request["service_tier"], "default")
        self.assertEqual(len(request["evaluation_cases"]), 8)
        self.assertEqual(
            {case["language"] for case in request["evaluation_cases"]},
            {"en", "fr", "de", "ja", "ar", "zh", "ru", "es"},
        )
        rendered = json.dumps(request, ensure_ascii=False)
        for forbidden in (
            "telegram_user_id",
            "learner_id",
            "user_prompt",
            "history",
            "test-secret-key",
        ):
            self.assertNotIn(forbidden, rendered)
        self.assertTrue(result["passed"])
        self.assertEqual(result["cost_micro_usd"], 53)
        self.assertEqual(environment["AI_TUTOR_ENABLED"], "false")

    async def test_ac_10_receipt_is_atomic_private_and_strictly_aggregate(self):
        api = self.require_smoke()
        with tempfile.TemporaryDirectory(prefix="ai-smoke-receipt-") as raw:
            root = Path(raw)
            receipt_path = root / "receipt.json"
            await api.run_smoke(
                environment=self.environment(root),
                provider=FakeProvider(),
                fixture_path=FIXTURE,
                receipt_path=receipt_path,
                run_id="receipt-20260809",
                execute=True,
                now=datetime(2026, 8, 9, 12, 0, tzinfo=timezone.utc),
            )

            receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
            self.assertEqual(receipt_path.stat().st_mode & 0o777, 0o600)
            self.assertEqual(
                set(receipt),
                {
                    "date",
                    "model",
                    "service_tier",
                    "input_tokens",
                    "cached_input_tokens",
                    "cache_write_tokens",
                    "output_tokens",
                    "total_tokens",
                    "cost_micro_usd",
                    "latency_ms",
                    "passed",
                    "failure_code",
                },
            )
            self.assertTrue(receipt["passed"])
            self.assertIsNone(receipt["failure_code"])
            self.assertEqual(list(root.glob(".receipt.json.*")), [])
            rendered = json.dumps(receipt, ensure_ascii=False)
            for forbidden in (
                "prompt",
                "response",
                "api_key",
                "request_id",
                "telegram",
                "test-secret-key",
                str(root),
            ):
                self.assertNotIn(forbidden, rendered)

    async def test_ec_03_duplicate_run_or_existing_receipt_refuses_second_attempt(self):
        api = self.require_smoke()
        with tempfile.TemporaryDirectory(prefix="ai-smoke-idempotency-") as raw:
            root = Path(raw)
            provider = FakeProvider()
            kwargs = {
                "environment": self.environment(root),
                "provider": provider,
                "fixture_path": FIXTURE,
                "receipt_path": root / "receipt.json",
                "run_id": "one-attempt-20260809",
                "execute": True,
            }
            await api.run_smoke(**kwargs)
            with self.assertRaises(api.AISmokeAlreadyExecutedError):
                await api.run_smoke(**kwargs)

        self.assertEqual(len(provider.calls), 1)

    async def test_err_03_provider_failures_write_sanitized_receipt_and_fail_closed(self):
        api = self.require_smoke()
        failure_results = {
            "timeout": FakeProvider(error=TimeoutError("secret prompt timeout")),
            "wrong_model": FakeProvider(
                result={**FakeProvider().result, "model": "wrong-model"}
            ),
            "wrong_tier": FakeProvider(
                result={**FakeProvider().result, "service_tier": "priority"}
            ),
            "invalid_output": FakeProvider(
                result={**FakeProvider().result, "structured_output": {"cases": []}}
            ),
            "over_cost": FakeProvider(
                result={**FakeProvider().result, "cost_micro_usd": 5001}
            ),
        }
        for label, provider in failure_results.items():
            with self.subTest(case=label), tempfile.TemporaryDirectory(
                prefix="ai-smoke-failure-"
            ) as raw:
                root = Path(raw)
                environment = self.environment(root)
                receipt_path = root / "failed.json"
                with self.assertRaises(api.AISmokeExecutionError):
                    await api.run_smoke(
                        environment=environment,
                        provider=provider,
                        fixture_path=FIXTURE,
                        receipt_path=receipt_path,
                        run_id=f"{label}-20260809",
                        execute=True,
                    )
                receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
                self.assertFalse(receipt["passed"])
                self.assertTrue(receipt["failure_code"])
                self.assertEqual(receipt_path.stat().st_mode & 0o777, 0o600)
                self.assertNotIn("secret prompt", json.dumps(receipt))
                self.assertEqual(environment["AI_TUTOR_ENABLED"], "false")

    async def test_err_03_receipt_storage_failure_uses_sanitized_emergency_receipt(self):
        api = self.require_smoke()
        with tempfile.TemporaryDirectory(prefix="ai-smoke-storage-") as raw:
            root = Path(raw)
            primary_is_directory = root / "unwritable-receipt"
            primary_is_directory.mkdir()
            emergency = root / "emergency-failed.json"
            environment = self.environment(root)
            with self.assertRaises(api.AISmokeExecutionError):
                await api.run_smoke(
                    environment=environment,
                    provider=FakeProvider(),
                    fixture_path=FIXTURE,
                    receipt_path=primary_is_directory,
                    failure_receipt_path=emergency,
                    run_id="storage-failure-20260809",
                    execute=True,
                )

            receipt = json.loads(emergency.read_text(encoding="utf-8"))
            self.assertFalse(receipt["passed"])
            self.assertEqual(receipt["failure_code"], "receipt_storage_failure")
            self.assertEqual(emergency.stat().st_mode & 0o777, 0o600)
            self.assertNotIn(str(root), json.dumps(receipt))
            self.assertEqual(environment["AI_TUTOR_ENABLED"], "false")


if __name__ == "__main__":
    unittest.main()
