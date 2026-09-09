import re
import unittest
from pathlib import Path

from mydictionary import ai_tutor


ROOT = Path(__file__).resolve().parents[1]
DECORATIVE_EMOJI = r"[\U0001F300-\U0001FAFF\u2600-\u27BF]"
LEGACY_MARKERS = ("💡", "📌", "👉")


def mirror_answer(
    *,
    answer_ru: str = "Короткий прямой ответ.",
    evidence_ru: tuple[str, ...] = ("Один полезный факт.",),
    interpretation_ru: str = "Короткое объяснение.",
    next_step_ru: str = "Сделай один следующий шаг.",
    language_items: tuple[dict[str, str], ...] = (),
) -> ai_tutor.MirrorAnswer:
    return ai_tutor.parse_mirror_answer(
        {
            "answer_ru": answer_ru,
            "evidence_ru": list(evidence_ru),
            "interpretation_ru": interpretation_ru,
            "language_items": list(language_items),
            "examples": [],
            "next_step_ru": next_step_ru,
        }
    )


def section_markers(rendered: str) -> tuple[str, ...]:
    return tuple(
        paragraph.split(maxsplit=1)[0]
        for paragraph in rendered.split("\n\n")
        if re.match(DECORATIVE_EMOJI, paragraph)
    )


class MirrorResponseFormatsV1Test(unittest.TestCase):
    def test_ac_01_general_conversation_is_natural_prose_without_mandatory_emoji(self):
        answer = mirror_answer(
            answer_ru="Да, в разговоре это звучит естественно.",
            evidence_ru=(),
            interpretation_ru="",
            next_step_ru="",
        )

        rendered = ai_tutor.render_mirror_answer(
            answer,
            available_credits=39,
            task_kind="general_conversation",
        )

        self.assertEqual(rendered, answer.answer_ru)
        self.assertNotRegex(rendered, rf"^{DECORATIVE_EMOJI}")

    def test_ac_02_translation_uses_language_card_and_distinct_action_marker(self):
        answer = mirror_answer(
            answer_ru="Bonjour значит «здравствуйте» или «добрый день».",
            evidence_ru=(),
            interpretation_ru="",
            next_step_ru="Сравни bonjour с разговорным salut.",
            language_items=(
                {
                    "target": "bonjour",
                    "transcription": "/bɔ̃.ʒuʁ/",
                    "meaning_ru": "здравствуйте; добрый день",
                    "note_ru": "Нейтральное дневное приветствие.",
                },
            ),
        )

        rendered = ai_tutor.render_mirror_answer(
            answer,
            available_credits=39,
            task_kind="translation_nuance",
        )
        markers = section_markers(rendered)

        self.assertEqual(markers[:2], ("🌍", "🗣️"))
        self.assertEqual(len(markers), 3)
        self.assertNotIn(markers[-1], markers[:2])
        self.assertIn("bonjour /bɔ̃.ʒuʁ/ — здравствуйте; добрый день", rendered)

    def test_ac_03_ac_04_ac_05_task_kinds_have_distinct_semantic_marker_sets(self):
        expected_leads = {
            "correction": "✏️",
            "grammar": "🧩",
            "pronunciation": "🎧",
            "practice": "🎯",
            "progress_review": "📈",
        }
        observed: dict[str, tuple[str, ...]] = {}

        for task_kind, expected_lead in expected_leads.items():
            with self.subTest(task_kind=task_kind):
                rendered = ai_tutor.render_mirror_answer(
                    mirror_answer(),
                    available_credits=39,
                    task_kind=task_kind,
                )
                markers = section_markers(rendered)
                observed[task_kind] = markers
                self.assertTrue(markers)
                self.assertEqual(markers[0], expected_lead)
                if task_kind == "progress_review":
                    self.assertIn("🎯", markers)

        self.assertEqual(len(set(observed.values())), len(observed))

    def test_ac_06_each_format_has_at_most_three_unique_unstacked_markers(self):
        task_kinds = (
            "translation_nuance",
            "correction",
            "grammar",
            "pronunciation",
            "practice",
            "progress_review",
        )

        for task_kind in task_kinds:
            with self.subTest(task_kind=task_kind):
                rendered = ai_tutor.render_mirror_answer(
                    mirror_answer(),
                    available_credits=39,
                    task_kind=task_kind,
                )
                markers = section_markers(rendered)
                self.assertLessEqual(len(markers), 3)
                self.assertEqual(len(markers), len(set(markers)))
                self.assertNotRegex(
                    rendered,
                    rf"(?m)^{DECORATIVE_EMOJI}\ufe0f?\s*{DECORATIVE_EMOJI}",
                )

    def test_ac_06_translation_does_not_duplicate_provider_owned_section_markers(self):
        answer = mirror_answer(
            answer_ru="🌍 Bonjour значит «здравствуйте».",
            evidence_ru=("🗣️ bonjour /bɔ̃.ʒuʁ/",),
            interpretation_ru="",
            next_step_ru="🔁 Повтори bonjour вслух.",
        )

        rendered = ai_tutor.render_mirror_answer(
            answer,
            available_credits=39,
            task_kind="translation_nuance",
        )

        self.assertEqual(
            {marker: rendered.count(marker) for marker in ("🌍", "🗣️", "🔁")},
            {"🌍": 1, "🗣️": 1, "🔁": 1},
        )
        self.assertNotRegex(
            rendered,
            rf"(?m)^{DECORATIVE_EMOJI}\ufe0f?\s*{DECORATIVE_EMOJI}",
        )

    def test_ec_01_omitted_and_unknown_task_fall_back_to_natural_conversation(self):
        answer = mirror_answer(
            answer_ru="Продолжим с того места, где остановились.",
            evidence_ru=(),
            interpretation_ru="",
            next_step_ru="",
        )

        omitted = ai_tutor.render_mirror_answer(answer, available_credits=39)
        unknown = ai_tutor.render_mirror_answer(
            answer,
            available_credits=39,
            task_kind="future_compatible_task",
        )

        self.assertEqual(omitted, answer.answer_ru)
        self.assertEqual(unknown, answer.answer_ru)

    def test_ec_02_ec_03_sparse_answer_strips_legacy_provider_decoration(self):
        answer = mirror_answer(
            answer_ru="💡 Полезный ответ без обязательной рамки. 📌",
            evidence_ru=(),
            interpretation_ru="",
            next_step_ru="👉",
        )

        rendered = ai_tutor.render_mirror_answer(
            answer,
            available_credits=39,
            task_kind="general_conversation",
        )

        self.assertTrue(rendered.strip())
        for marker in LEGACY_MARKERS:
            self.assertNotIn(marker, rendered)

    def test_ec_03_legacy_provider_markers_are_removed_before_translation_format(self):
        answer = mirror_answer(
            answer_ru="💡 Bonjour — нейтральное приветствие.",
            evidence_ru=("📌 Его используют днём.",),
            interpretation_ru="",
            next_step_ru="👉 Скажи bonjour вслух.",
        )

        rendered = ai_tutor.render_mirror_answer(
            answer,
            available_credits=39,
            task_kind="translation_nuance",
        )

        for marker in LEGACY_MARKERS:
            self.assertNotIn(marker, rendered)
        self.assertEqual(len(section_markers(rendered)), 3)

    def test_ec_04_ac_08_duplicate_support_and_response_ceiling_are_preserved(self):
        repeated = "Точность 75%."
        answer = mirror_answer(
            answer_ru=f"{repeated} " + ("Короткая мысль. " * 100),
            evidence_ru=(repeated,),
            interpretation_ru=repeated,
            next_step_ru="Повтори пять слов.",
        )

        rendered = ai_tutor.render_mirror_answer(
            answer,
            available_credits=39,
            task_kind="progress_review",
        )

        self.assertEqual(rendered.count(repeated), 1)
        self.assertLessEqual(len(rendered), 900)

    def test_err_01_invalid_provider_schema_is_still_rejected(self):
        with self.assertRaises(ai_tutor.AIProviderError):
            ai_tutor.parse_mirror_answer(
                {
                    "answer_ru": "Ответ.",
                    "language_items": [],
                    "examples": [],
                    "next_step_ru": "",
                    "unexpected_format": "🌍",
                }
            )

    def test_ac_07_prompt_v9_is_active_and_documents_task_specific_formats(self):
        active = ROOT / "prompts/mirror-v9.txt"
        historical = ROOT / "prompts/mirror-v8.txt"

        self.assertTrue(active.is_file(), "missing reviewed Lexi V9 prompt contract")
        self.assertTrue(historical.is_file(), "mirror-v8 must remain historical")
        reviewed = active.read_text(encoding="utf-8").removesuffix("\n")
        self.assertEqual(ai_tutor.MIRROR_INSTRUCTIONS, reviewed)

        normalized = " ".join(reviewed.casefold().split())
        for required in (
            "task-specific",
            "general_conversation",
            "translation_nuance",
            "correction",
            "grammar",
            "pronunciation",
            "practice",
            "progress_review",
            "🌍",
            "🗣️",
        ):
            with self.subTest(prompt_marker=required):
                self.assertIn(required, normalized)
        self.assertNotRegex(
            normalized,
            r"(?:application )?renderer (?:always )?adds.{0,100}💡.{0,30}📌.{0,30}👉",
        )


if __name__ == "__main__":
    unittest.main()
