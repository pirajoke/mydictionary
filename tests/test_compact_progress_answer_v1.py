import json
import re
import unittest

from mydictionary import ai_tutor, mirror_assistant
from tests.test_ai_learning_companion import (
    LearningCompanionServiceHardeningTest,
)


class CompactProgressAnswerContractTest(unittest.IsolatedAsyncioTestCase):
    maxDiff = None

    async def test_compact_progress_review_is_brief_and_does_not_repeat_facts(self):
        provider_result = ai_tutor.ProviderResult(
            answer=None,
            response_id="compact-progress-response",
            model="test-model",
            usage=ai_tutor.ProviderUsage(),
            service_tier="default",
            status="completed",
            output_text=json.dumps(
                {
                    "answer_ru": (
                        "Je ne peux pas déterminer précisément ce que tu as "
                        "travaillé ni ce qui s'est amélioré aujourd'hui, car les "
                        "données détaillées de la journée ne sont pas disponibles. "
                        "Les données générales indiquent une précision de 95 %, "
                        "avec 18 réponses correctes et 1 incorrecte, ainsi que "
                        "16 révisions dues."
                    ),
                    "evidence_ru": [
                        "Précision actuelle : 95 %. Bilan enregistré : "
                        "18 réponses correctes et 1 incorrecte. La tendance "
                        "historique n'est pas disponible, et les activités des "
                        "7 derniers jours ne sont pas enregistrées."
                    ],
                    "interpretation_ru": (
                        "Il n'est donc pas possible d'identifier une amélioration "
                        "précise aujourd'hui. La prochaine étape la plus pertinente "
                        "est de faire les 16 révisions dues."
                    ),
                    "language_items": [],
                    "examples": [],
                    "next_step_ru": (
                        "Fais d'abord les 16 révisions dues, puis consulte le bilan "
                        "de la session."
                    ),
                },
                ensure_ascii=False,
            ),
        )
        payload = mirror_assistant.build_mirror_provider_payload(
            question="Qu'est-ce que j'ai amélioré aujourd'hui ?",
            admin_guidance=(
                "Réponds directement comme un coach linguistique attentif."
            ),
            grounded_snapshot={
                "has_progress": True,
                "lifetime_accuracy_percent": 95,
                "correct_answers": 18,
                "wrong_answers": 1,
                "due_reviews": 16,
                "trend": {"status": "unavailable"},
            },
            recent_dialogue=[],
            task_kind="progress_review",
            communication_mode="brief",
            answer_depth="compact",
            learner_level="a2",
            interface_locale="fr",
        )
        service, _store, _provider, _settings = (
            LearningCompanionServiceHardeningTest.service_fixture(
                max_provider_input_chars=12000,
                provider_result=provider_result,
            )
        )

        rendered = await service.ask_mirror(user_id=607, payload=payload)
        paragraphs = str(rendered).split("\n\n")
        uncertainty_mentions = len(
            re.findall(
                r"pas déterminer|pas disponible|pas possible|"
                r"ne sont pas disponibles",
                str(rendered).casefold(),
            )
        )
        violations = {
            "over_500_chars": len(rendered) > 500,
            "not_two_paragraphs": len(paragraphs) != 2,
            "accuracy_repeated": str(rendered).count("95 %") > 1,
            "answer_count_repeated": (
                str(rendered).count("18 réponses correctes") > 1
            ),
            "uncertainty_repeated": uncertainty_mentions > 1,
            "summary_missing_strongest_facts": not (
                paragraphs
                and "95 %" in paragraphs[0]
                and "18 réponses correctes" in paragraphs[0]
            ),
            "action_missing": not (
                paragraphs
                and paragraphs[-1].startswith("👉 ")
                and "16 révisions" in paragraphs[-1]
            ),
        }

        self.assertEqual(
            violations,
            {
                "over_500_chars": False,
                "not_two_paragraphs": False,
                "accuracy_repeated": False,
                "answer_count_repeated": False,
                "uncertainty_repeated": False,
                "summary_missing_strongest_facts": False,
                "action_missing": False,
            },
            str(rendered),
        )


if __name__ == "__main__":
    unittest.main()
