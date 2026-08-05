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
from mydictionary.catalog import load_catalog
from mydictionary.content import meaning_text, speech_text, target_text
from mydictionary.voice_tutor import VoiceWord, evaluate_transcript
from vocabulary_topics import transcription_for


LAUNCH_LANGUAGES = {"en", "fr", "de", "ja", "ar", "zh", "ru", "es"}


class AITutorEvaluationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixture = Path(__file__).parent / "fixtures" / "ai_tutor_eval.json"
        cls.cases = json.loads(fixture.read_text(encoding="utf-8"))

    def test_contract_cases_are_grounded_and_russian_first(self):
        self.assertEqual(
            {case["language"] for case in self.cases}, LAUNCH_LANGUAGES
        )
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

    def test_eval_terms_match_canonical_public_pack_content(self):
        catalog = load_catalog(Path(__file__).resolve().parents[1])
        fixtures = {case["language"]: case for case in self.cases}
        for language in sorted(LAUNCH_LANGUAGES):
            with self.subTest(language=language):
                pack = catalog.pack_for_language(language, "learner")
                word = catalog.words(pack)[0]
                case = fixtures[language]
                self.assertEqual(case["term"], target_text(word))
                self.assertEqual(case["meaning_ru"], meaning_text(word))
                self.assertEqual(
                    case["transcription"], transcription_for(word, language)
                )

    def test_voice_text_matching_is_exercised_for_all_launch_languages(self):
        catalog = load_catalog(Path(__file__).resolve().parents[1])
        for language in sorted(LAUNCH_LANGUAGES):
            with self.subTest(language=language):
                pack = catalog.pack_for_language(language, "learner")
                raw = catalog.words(pack)[0]
                word = VoiceWord(
                    vocabulary_id=raw["progress_id"],
                    target=target_text(raw),
                    speech=speech_text(raw),
                    transcription=transcription_for(raw, language),
                    meaning_ru=meaning_text(raw),
                )
                feedback = evaluate_transcript(
                    word.speech, expected=word, words=(word,)
                )
                self.assertEqual(feedback.code, "exact")
                self.assertTrue(word.transcription)
                self.assertTrue(word.meaning_ru)


if __name__ == "__main__":
    unittest.main()
