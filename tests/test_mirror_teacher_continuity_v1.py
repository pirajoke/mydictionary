import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock

import bot
from mydictionary import ai_tutor, miniapp, mirror_assistant
from mydictionary.storage import DatabaseStore, User, UserProgress


ROOT = Path(__file__).resolve().parents[1]


class MirrorTeacherTurnContractTest(unittest.TestCase):
    def test_ac1_progress_phrase_and_recent_terms_are_structured(self):
        self.assertEqual(
            mirror_assistant.direct_mirror_progress_locale("что я проходил"),
            "ru",
        )
        rendered = mirror_assistant.render_mirror_progress_focus(
            {
                "has_progress": True,
                "accuracy_percent": 80,
                "tracked_words": 5,
                "due_count": 2,
                "streak": 3,
                "recent_terms": ["old", "book"],
                "weak_terms": [],
            },
            locale="ru",
        )
        self.assertEqual(rendered.count("\n"), 2)
        self.assertTrue(rendered.startswith("📊 "))
        self.assertIn("🧠 ", rendered)
        self.assertIn("old, book", rendered)
        self.assertIn("🎯 ", rendered)

    def test_ac2_short_answer_continues_the_previous_practice(self):
        recent = [
            {"role": "user", "text": "дай упражнение"},
            {
                "role": "assistant",
                "text": "▶️ Переведи на английский: «холодная книга».",
            },
        ]
        self.assertEqual(
            mirror_assistant.classify_mirror_turn_task(
                "a cold book", recent_dialogue=recent
            ),
            "practice",
        )
        self.assertEqual(
            mirror_assistant.classify_mirror_turn_task(
                "привет", recent_dialogue=recent
            ),
            "general_conversation",
        )

    def test_ac3_renderer_removes_raw_markdown_from_teacher_turn(self):
        answer = ai_tutor.parse_mirror_answer(
            {
                "answer_ru": "**Верно:** an old book.",
                "evidence_ru": ["Артикль **an** нужен перед гласным звуком."],
                "interpretation_ru": "",
                "language_items": [],
                "examples": [
                    {
                        "target": "an old house",
                        "transcription": "",
                        "russian": "старый дом",
                    }
                ],
                "next_step_ru": "Переведи: «новая книга».",
            }
        )
        rendered = ai_tutor.render_mirror_answer(
            answer,
            available_credits=3,
            task_kind="practice",
        )
        self.assertNotIn("**", rendered)
        self.assertLessEqual(len(rendered.split("\n\n")), 3)
        self.assertIn("🎯 ", rendered)
        self.assertIn("▶️ ", rendered)

    def test_ac6_prompt_advances_and_never_reuses_recent_examples(self):
        prompt = (ROOT / "prompts" / "mirror-v10.txt").read_text(encoding="utf-8")
        self.assertIn("Never reuse an example", prompt)
        self.assertIn("advance to one fresh task", prompt)
        self.assertIn("Do not output Markdown decoration", prompt)


class MirrorVocabularyExposureContractTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="mirror-continuity-")
        self.store = DatabaseStore(
            f"sqlite:///{Path(self.temporary.name) / 'continuity.sqlite3'}"
        )
        self.user_id = 91701
        self.store.ensure_user_id(self.user_id)

    def tearDown(self):
        self.store.close()
        self.temporary.cleanup()

    def test_ac4_catalog_mentions_are_bounded_unique_exposures_without_scoring(self):
        pack = bot.CATALOG.get("en-basics-100")
        words = bot.CATALOG.words(pack)
        selected = [word for word in words if word["target"] in {"old", "book", "cold"}]
        entries = mirror_assistant.catalog_word_exposures(
            selected,
            "old book",
            "Try a cold book, then repeat old book.",
        )
        observed_at = datetime(2026, 9, 17, 12, 0, tzinfo=timezone.utc)
        stored = self.store.record_word_exposures(
            self.user_id,
            language=pack.storage_key,
            entries=entries,
            now=observed_at,
        )

        self.assertEqual(stored, 3)
        progress = self.store.load_word_progress(self.user_id, pack.storage_key)
        self.assertEqual(len(progress), 3)
        self.assertTrue(all(row["last_seen"] == observed_at.isoformat() for row in progress.values()))
        self.assertTrue(all(row["correct_count"] == row["wrong_count"] == 0 for row in progress.values()))
        with self.store.Session() as session:
            aggregate = session.get(UserProgress, self.user_id)
            self.assertEqual((aggregate.total_correct, aggregate.total_wrong, aggregate.xp, aggregate.sessions), (0, 0, 0, 0))

    def test_ec1_duplicate_exposures_are_written_once_and_erased_user_is_rejected(self):
        pack = bot.CATALOG.get("en-basics-100")
        word = next(row for row in bot.CATALOG.words(pack) if row["target"] == "book")
        entries = [(4, word), (4, word)] * 8
        self.assertEqual(
            self.store.record_word_exposures(
                self.user_id, language=pack.storage_key, entries=entries
            ),
            1,
        )
        with self.store.Session.begin() as session:
            learner = session.get(User, self.user_id)
            learner.privacy_status = "erased"
        with self.assertRaises(ValueError):
            self.store.record_word_exposures(
                self.user_id, language=pack.storage_key, entries=[(4, word)]
            )


class MirrorHistoryProfileContractTest(unittest.TestCase):
    def test_ac5_bootstrap_exposes_three_consented_exchanges_only(self):
        store = MagicMock()
        store.access_profile.return_value = {
            "role": "learner",
            "access_status": "active",
            "privacy_status": "active",
        }
        store.product_profile.return_value = {
            "role": "learner",
            "native_language": "ru",
            "daily_word_goal": 5,
            "active_lang": "en",
            "active_pack_id": "en-basics-100",
        }
        store.load_profile.return_value = {"active_lang": "en", "active_pack_id": "en-basics-100"}
        store.load_word_progress.return_value = {}
        store.ai_usage_summary.return_value = {}
        store.has_consent.return_value = True
        store.peek_mirror_dialogue.return_value = [
            item
            for index in range(4)
            for item in (
                {"role": "user", "text": f"question {index}"},
                {"role": "assistant", "text": f"answer {index}"},
            )
        ]

        payload = miniapp.build_bootstrap(
            store,
            user_id=91702,
            display_name="Mila",
            locale="ru",
            catalog=bot.CATALOG,
            products=[],
            checkout_enabled=False,
            ai_enabled=True,
            voice_enabled=False,
            ai_consent_version="ai-v1",
            mirror_memory_enabled=True,
        )

        self.assertEqual(len(payload["tutor_history"]), 3)
        self.assertEqual(payload["tutor_history"][-1]["question"], "question 3")
        store.peek_mirror_dialogue.assert_called_once_with(91702, limit=6)

        store.has_consent.return_value = False
        payload = miniapp.build_bootstrap(
            store,
            user_id=91702,
            display_name="Mila",
            locale="ru",
            catalog=bot.CATALOG,
            products=[],
            checkout_enabled=False,
            ai_enabled=True,
            voice_enabled=False,
            ai_consent_version="ai-v1",
            mirror_memory_enabled=True,
        )
        self.assertEqual(payload["tutor_history"], [])

    def test_ec2_profile_history_is_collapsed_bounded_and_text_only(self):
        html = (ROOT / "mydictionary" / "templates" / "miniapp.html").read_text(encoding="utf-8")
        script = (ROOT / "mydictionary" / "static" / "miniapp.js").read_text(encoding="utf-8")
        self.assertIn('id="tutor-history"', html)
        self.assertIn('id="tutor-history-list"', html)
        self.assertIn('const tutorHistory = Array.isArray(data.tutor_history)', script)
        self.assertIn('text(historyQuestion', script)
        self.assertIn('text(historyAnswer', script)
        self.assertNotIn('tutor-history-list").innerHTML', script)


class MirrorReadOnlyHistoryContractTest(unittest.TestCase):
    def test_ac5_peek_history_does_not_delete_expired_rows(self):
        temporary = tempfile.TemporaryDirectory(prefix="mirror-peek-")
        self.addCleanup(temporary.cleanup)
        store = DatabaseStore(f"sqlite:///{Path(temporary.name) / 'peek.sqlite3'}")
        self.addCleanup(store.close)
        now = datetime(2026, 9, 17, 12, 0, tzinfo=timezone.utc)
        store.append_mirror_exchange(
            91703,
            question="expired",
            answer="expired answer",
            retention_days=1,
            now=now - timedelta(days=2),
        )
        store.append_mirror_exchange(
            91703,
            question="current",
            answer="current answer",
            retention_days=7,
            now=now,
        )

        self.assertEqual(
            store.peek_mirror_dialogue(91703, limit=6, now=now),
            [
                {"role": "user", "text": "current"},
                {"role": "assistant", "text": "current answer"},
            ],
        )
        with store.Session() as session:
            from mydictionary.storage import MirrorDialogueTurn

            self.assertEqual(session.query(MirrorDialogueTurn).count(), 4)
