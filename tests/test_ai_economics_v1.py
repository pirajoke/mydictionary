import json
import os
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import AsyncMock, patch


os.environ.setdefault("BOT_TOKEN", "123456:TESTTOKEN")
os.environ.setdefault("ALLOWED_USER_ID", "1")
os.environ.setdefault("ALLOW_SQLITE_DEV", "true")

import bot
from mydictionary.ai_tutor import AIConfigurationError, AITutorSettings
from mydictionary.economics import load_ai_economics_contract
from mydictionary.localization import INTERFACE_LOCALES, translate
from tests.test_ai_tutor import environment_for, settings


ROOT = Path(__file__).resolve().parents[1]


class AIEconomicsConfigurationContractTest(unittest.TestCase):
    def test_ac1_ec1_approved_snapshot_explicitly_disables_per_user_cap(self):
        snapshot = json.loads(
            (ROOT / "config/launch-economics.json").read_text(encoding="utf-8")
        )
        self.assertEqual(
            snapshot["snapshot_id"],
            "mydictionary-commercial-v4-2026-08-28",
        )
        self.assertEqual(snapshot["reviewed_on"], "2026-08-28")
        self.assertIn("max_daily_requests_per_user", snapshot["ai"]["limits"])
        self.assertIsNone(
            snapshot["ai"]["limits"]["max_daily_requests_per_user"]
        )

        contract = load_ai_economics_contract(
            ROOT / "config/launch-economics.json",
            require_approved=True,
        )
        self.assertIsNone(contract.max_daily_requests_per_user)

    def test_ec1_enabled_runtime_requires_explicit_zero_wire_sentinel(self):
        with tempfile.TemporaryDirectory(prefix="ai-economics-runtime-") as temp:
            configured = settings(temp)
            environment = environment_for(configured)

            self.assertEqual(environment["AI_MAX_DAILY_REQUESTS_PER_USER"], "0")
            loaded = AITutorSettings.from_env(environment)
            self.assertIsNone(loaded.max_daily_requests_per_user)

            malformed = {
                "missing": None,
                "empty": "",
                "legacy-five": "5",
                "negative": "-1",
                "word": "disabled",
            }
            for label, value in malformed.items():
                with self.subTest(case=label):
                    candidate = dict(environment)
                    if value is None:
                        candidate.pop("AI_MAX_DAILY_REQUESTS_PER_USER", None)
                    else:
                        candidate["AI_MAX_DAILY_REQUESTS_PER_USER"] = value
                    with self.assertRaises(AIConfigurationError):
                        AITutorSettings.from_env(candidate)


class AIEconomicsUserSurfaceContractTest(unittest.IsolatedAsyncioTestCase):
    def test_ac7_legacy_limit_copy_is_removed_and_neutral_copy_is_complete(self):
        expected = {
            "en": "The AI tutor is temporarily unavailable. No AI credit was charged.",
            "fr": "Le tuteur IA est temporairement indisponible. Aucun crédit IA n’a été débité.",
            "de": "Der AI-Tutor ist vorübergehend nicht verfügbar. Es wurde kein AI-Guthaben abgezogen.",
            "ja": "AIチューターは一時的に利用できません。AIクレジットは消費されていません。",
            "ar": "مدرّس AI غير متاح مؤقتاً. لم يُخصم أي رصيد AI.",
            "zh": "AI 导师暂时不可用，未扣除 AI 点数。",
            "ru": "AI-репетитор временно недоступен. AI-кредит не списан.",
            "es": "El tutor de IA no está disponible temporalmente. No se cobró ningún crédito de IA.",
        }
        self.assertEqual(set(expected), set(INTERFACE_LOCALES))
        for locale in INTERFACE_LOCALES:
            with self.subTest(locale=locale):
                self.assertEqual(
                    translate("ai_unavailable_no_charge", locale),
                    expected[locale],
                )
                with self.assertRaises(KeyError):
                    translate("ai_limit_reached", locale)

    async def test_ac7_typed_tutor_global_budget_error_uses_no_charge_copy(self):
        for locale in INTERFACE_LOCALES:
            with self.subTest(locale=locale):
                message = SimpleNamespace(reply_text=AsyncMock())
                context = SimpleNamespace(user_data={})
                service = SimpleNamespace(
                    ask=AsyncMock(side_effect=bot.AIQuotaExceeded("global budget"))
                )
                with (
                    patch.object(bot, "AI_SETTINGS", SimpleNamespace(enabled=True)),
                    patch.object(bot, "active_tutor_context", return_value=object()),
                    patch.object(bot, "get_ai_tutor_service", return_value=service),
                ):
                    await bot.send_ai_tutor_answer(
                        message,
                        context,
                        "Explain this word",
                        user_id=901,
                        locale=locale,
                    )

                service.ask.assert_awaited_once()
                message.reply_text.assert_awaited_once_with(
                    translate("ai_unavailable_no_charge", locale)
                )


class AIEconomicsDocumentationContractTest(unittest.TestCase):
    def setUp(self):
        self.documents = {
            name: (ROOT / relative).read_text(encoding="utf-8")
            for name, relative in {
                "economics": "docs/ai-stars-economics.md",
                "launch": "docs/launch-readiness.md",
                "billing": "docs/billing-assumptions.md",
                "mirror": "docs/mirror-control-plane-v1.md",
                "stage2": "docs/ai-tutor-stage2.md",
            }.items()
        }
        self.normalized_documents = {
            name: " ".join(document.split())
            for name, document in self.documents.items()
        }

    def test_canonical_docs_remove_the_shared_text_ai_attempt_cap(self):
        forbidden_claims = (
            "5 attempts/user/rolling 24h",
            "AI requests have a rolling per-user attempt limit",
            "AI_MAX_DAILY_REQUESTS_PER_USER=<1-100; draft 5>",
            "Voice operations share the AI project day/month/in-flight caps "
            "and per-user rolling limit",
        )
        for name, document in self.documents.items():
            for claim in forbidden_claims:
                with self.subTest(document=name, stale_claim=claim):
                    self.assertFalse(
                        claim in self.normalized_documents[name],
                        f"{name} still contains stale text-AI cap claim",
                    )
        economics = self.normalized_documents["economics"]
        for label, present in (
            ("old snapshot date", "Snapshot date: 2026-08-12." in economics),
            ("old daily-limit gate", "one credit, daily limit one" in economics),
            ("current snapshot date", "Snapshot date: 2026-08-28." not in economics),
        ):
            with self.subTest(document="economics", stale_claim=label):
                self.assertFalse(present)

    def test_docs_separate_text_wallet_global_budgets_and_voice_cap(self):
        required = {
            "economics": (
                "credit wallet",
                "no per-user daily request cap",
                "AI_MAX_DAILY_REQUESTS_PER_USER=0",
                "AI_MAX_PROJECT_COST_MICRO_USD_PER_DAY",
                "AI_MAX_PROJECT_COST_MICRO_USD_PER_MONTH",
                "AI_MAX_IN_FLIGHT_COST_MICRO_USD",
            ),
            "launch": (
                "credit wallet",
                "no per-user daily request cap",
                "AI_MAX_DAILY_REQUESTS_PER_USER=0",
                "AI_MAX_PROJECT_COST_MICRO_USD_PER_DAY",
                "AI_MAX_PROJECT_COST_MICRO_USD_PER_MONTH",
                "AI_MAX_IN_FLIGHT_COST_MICRO_USD",
                "VOICE_TRANSLATION_MAX_DAILY_REQUESTS_PER_USER",
            ),
            "billing": (
                "credit wallet",
                "no per-user daily request cap",
                "project day/month/in-flight budgets",
                "VOICE_TRANSLATION_MAX_DAILY_REQUESTS_PER_USER",
            ),
            "mirror": (
                "credit wallet",
                "no per-user daily request cap",
                "project day/month/in-flight budgets",
                "VOICE_TRANSLATION_MAX_DAILY_REQUESTS_PER_USER",
            ),
            "stage2": (
                "credit wallet",
                "no per-user daily request cap",
                "project day/month/in-flight budgets",
                "VOICE_TRANSLATION_MAX_DAILY_REQUESTS_PER_USER",
                "AI_MAX_DAILY_REQUESTS_PER_USER=0",
            ),
        }
        for name, markers in required.items():
            with self.subTest(document=name):
                missing = [
                    marker
                    for marker in markers
                    if marker not in self.normalized_documents[name]
                ]
                self.assertEqual(missing, [])


if __name__ == "__main__":
    unittest.main()
