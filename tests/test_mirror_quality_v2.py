import json
from pathlib import Path
import unittest
from types import SimpleNamespace

import bot
from mydictionary import ai_tutor, mirror_assistant


class CaptureResponses:
    def __init__(self):
        self.kwargs = None

    async def create(self, **kwargs):
        self.kwargs = kwargs
        return SimpleNamespace(
            id="mirror-v2-response",
            model="gpt-test",
            service_tier="default",
            status="completed",
            output_text=json.dumps(
                {
                    "answer_ru": "Bonjour означает здравствуйте или добрый день.",
                    "language_items": [
                        {
                            "target": "bonjour",
                            "transcription": "/bɔ̃.ʒuʁ/",
                            "meaning_ru": "здравствуйте; добрый день",
                            "note_ru": "Нейтральное дневное приветствие.",
                        }
                    ],
                    "examples": [],
                    "next_step_ru": "",
                },
                ensure_ascii=False,
            ),
            usage=SimpleNamespace(
                input_tokens=20,
                input_tokens_details=SimpleNamespace(
                    cached_tokens=0, cache_write_tokens=0
                ),
                output_tokens=20,
                output_tokens_details=SimpleNamespace(reasoning_tokens=2),
                total_tokens=40,
            ),
        )


class MirrorQualityV2ContractTest(unittest.IsolatedAsyncioTestCase):
    def test_ac_03_active_pack_context_prefers_weak_word_and_all_meanings(self):
        context = bot.build_mirror_learning_context(
            {
                "role": "learner",
                "active_lang": "fr",
                "active_pack_id": "fr-basics-100",
            },
            {},
            {"language": "fr", "weak_terms": ["bonjour"]},
        )
        self.assertEqual(context["source"], "active_pack")
        self.assertEqual(context["language"], "fr")
        self.assertEqual(context["words"][0]["target"], "bonjour")
        self.assertIn("здравствуйте", context["words"][0]["meaning_ru"])
        self.assertIn("добрый день", context["words"][0]["meaning_ru"])
        self.assertTrue(context["words"][0]["transcription"])

    def test_ac_07_eight_language_matrix_has_transcription_and_russian_first(self):
        fixture = Path(__file__).parent / "fixtures" / "mirror_quality_v2.json"
        cases = json.loads(fixture.read_text(encoding="utf-8"))
        self.assertEqual(
            {case["language"] for case in cases},
            {"en", "fr", "de", "ja", "ar", "zh", "ru", "es"},
        )
        for case in cases:
            with self.subTest(language=case["language"]):
                answer = ai_tutor.parse_mirror_answer(
                    {
                        key: case[key]
                        for key in (
                            "answer_ru",
                            "language_items",
                            "examples",
                            "next_step_ru",
                        )
                    }
                )
                self.assertTrue(answer.language_items[0].transcription)
                rendered = ai_tutor.render_mirror_answer(
                    answer, available_credits=40
                )
                self.assertTrue(rendered.startswith(f"💡 {answer.answer_ru}"))
                self.assertIn("\n\n📌 ", rendered)
                self.assertIn(answer.language_items[0].transcription, rendered)

    def test_ac_01_russian_first_response_supports_translation_variants(self):
        parse = getattr(ai_tutor, "parse_mirror_answer", None)
        render = getattr(ai_tutor, "render_mirror_answer", None)
        self.assertTrue(callable(parse), "Mirror v2 parser is required")
        self.assertTrue(callable(render), "Mirror v2 renderer is required")
        answer = parse(
            {
                "answer_ru": "Bonjour означает здравствуйте или добрый день.",
                "language_items": [
                    {
                        "target": "bonjour",
                        "transcription": "/bɔ̃.ʒuʁ/",
                        "meaning_ru": "здравствуйте; добрый день",
                        "note_ru": "Выбор зависит от ситуации.",
                    }
                ],
                "examples": [
                    {
                        "target": "Bonjour, madame !",
                        "transcription": "/bɔ̃.ʒuʁ ma.dam/",
                        "russian": "Здравствуйте, мадам!",
                    }
                ],
                "next_step_ru": "Сравни bonjour и salut.",
            }
        )
        rendered = render(answer, available_credits=39)
        self.assertTrue(rendered.startswith(f"💡 {answer.answer_ru}"))
        self.assertIn("\n\n📌 ", rendered)
        self.assertIn("\n\n👉 ", rendered)
        self.assertIn("bonjour", rendered)
        self.assertIn("bonjour /bɔ̃.ʒuʁ/ — здравствуйте; добрый день", rendered)
        self.assertNotIn("AI-кредиты", rendered)

    def test_ac_02_ec_01_recent_dialogue_is_ephemeral_trimmed_and_bounded(self):
        append = getattr(mirror_assistant, "append_mirror_turn", None)
        recent = getattr(mirror_assistant, "recent_mirror_dialogue", None)
        self.assertTrue(callable(append), "Mirror history append helper is required")
        self.assertTrue(callable(recent), "Mirror history reader is required")
        user_data = {}
        for index in range(22):
            append(user_data, role="user", text=f"  вопрос {index}  ")
        turns = recent(user_data)
        self.assertEqual(len(turns), 20)
        self.assertEqual(turns[0], {"role": "user", "text": "вопрос 2"})
        self.assertEqual(turns[-1], {"role": "user", "text": "вопрос 21"})
        with self.assertRaises(ValueError):
            append(user_data, role="system", text="hidden")
        with self.assertRaises(ValueError):
            append(user_data, role="assistant", text="   ")

    async def test_ac_04_provider_uses_mirror_schema_and_quality_settings(self):
        responses = CaptureResponses()
        provider = ai_tutor.OpenAIResponsesProvider(
            api_key="test-key",
            model="gpt-test",
            service_tier="default",
            safety_salt="mirror-quality-test-salt",
            client=SimpleNamespace(responses=responses),
        )
        payload = bot.build_mirror_provider_payload(
            question="Как правильно перевести bonjour?",
            admin_guidance="Объясняй живо и точно как преподаватель языка.",
            grounded_snapshot={"language": "fr", "has_progress": True},
            learning_context={
                "language": "fr",
                "words": [
                    {
                        "target": "bonjour",
                        "transcription": "/bɔ̃.ʒuʁ/",
                        "meaning_ru": "здравствуйте; добрый день",
                    }
                ],
            },
            recent_dialogue=[
                {"role": "user", "text": "Учу приветствия."},
                {"role": "assistant", "text": "Начнём с дневных приветствий."},
            ],
        )
        await provider.generate_mirror(request_id="mirror-v2", user_id=7, payload=payload)
        self.assertEqual(payload["complexity_route"], "fast")
        self.assertEqual(responses.kwargs["reasoning"], {"effort": "none"})
        self.assertEqual(responses.kwargs["text"]["verbosity"], "low")
        self.assertEqual(responses.kwargs["max_output_tokens"], 220)
        self.assertEqual(
            responses.kwargs["text"]["format"]["name"],
            "my_dictionary_mirror_v2_answer",
        )
        sent = json.loads(responses.kwargs["input"])
        self.assertEqual(len(sent["recent_dialogue"]), 2)
        self.assertEqual(sent["learning_context"]["words"][0]["target"], "bonjour")
