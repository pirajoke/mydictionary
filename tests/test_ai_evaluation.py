import json
import unittest
from pathlib import Path
from types import SimpleNamespace

from mydictionary.ai_tutor import (
    TutorContext,
    TutorWord,
    parse_tutor_answer,
    render_tutor_answer,
    validate_tutor_answer,
)


class AITutorEvaluationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixture = Path(__file__).parent / "fixtures" / "ai_tutor_eval.json"
        cls.cases = json.loads(fixture.read_text(encoding="utf-8"))

    def test_contract_cases_are_grounded_and_russian_first(self):
        self.assertEqual({case["language"] for case in self.cases}, {"en", "vi", "ja"})
        for case in self.cases:
            with self.subTest(case=case["id"]):
                context = TutorContext(
                    language=case["language"],
                    topic="eval",
                    words=(
                        TutorWord(
                            term=case["term"],
                            transcription=case["transcription"],
                            meaning_ru=case["meaning_ru"],
                        ),
                    ),
                )
                answer = parse_tutor_answer(
                    {
                        "summary_ru": case["summary_ru"],
                        "entries": [
                            {
                                "term": case["term"],
                                "explanation_ru": case["explanation_ru"],
                                "examples": case["examples"],
                            }
                        ],
                    }
                )
                validate_tutor_answer(answer, context)
                rendered = render_tutor_answer(
                    SimpleNamespace(
                        answer=answer,
                        context=context,
                        allowance={"available_credits": 1},
                    )
                )
                self.assertTrue(rendered.startswith("🇷🇺 "))
                self.assertIn(case["term"], rendered)
                self.assertIn(
                    f"Транскрипция: {case['transcription']}", rendered
                )
                self.assertIn(f"Значение: {case['meaning_ru']}", rendered)


if __name__ == "__main__":
    unittest.main()
