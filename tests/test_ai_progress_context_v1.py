import os
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock, patch


os.environ.setdefault("BOT_TOKEN", "123456:TESTTOKEN")
os.environ.setdefault("ALLOWED_USER_ID", "1")
os.environ.setdefault("ALLOW_SQLITE_DEV", "true")

import bot
from mydictionary import mirror_assistant as companion
from mydictionary.localization import INTERFACE_LOCALES
from tests import test_zerkalo_communication_v1 as zerkalo


class AIProgressContextRoutingTest(unittest.TestCase):
    NATURAL_PROGRESS = {
        "en": "hello, what is my progress?",
        "fr": "bonjour, comment sont mes progrès ?",
        "de": "hallo, wie ist mein Fortschritt?",
        "ja": "こんにちは、私の進捗はどうですか？",
        "ar": "مرحبا، كيف هو تقدمي؟",
        "zh": "你好，我的学习进度怎么样？",
        "ru": "привет, какой сейчас прогресс?",
        "es": "hola, ¿cómo va mi progreso?",
    }
    NATURAL_FOLLOWUPS = {
        "en": "tell me more",
        "fr": "dis-m'en plus",
        "de": "erzähl mir mehr",
        "ja": "もっと詳しく教えて",
        "ar": "أخبرني المزيد",
        "zh": "再详细说说",
        "ru": "расскажи подробнее",
        "es": "cuéntame más",
    }

    def test_ac1_greeting_progress_is_a_direct_locale_aware_request(self):
        self.assertEqual(set(self.NATURAL_PROGRESS), set(INTERFACE_LOCALES))
        for locale, question in self.NATURAL_PROGRESS.items():
            with self.subTest(locale=locale):
                self.assertEqual(
                    companion.direct_mirror_progress_locale(question),
                    locale,
                )

    def test_ac1_progress_summary_is_two_short_grounded_lines(self):
        snapshot = {
            "has_progress": True,
            "accuracy_percent": 94,
            "lifetime_correct": 15,
            "lifetime_wrong": 1,
            "tracked_words": 15,
            "learned_words": 0,
            "due_count": 0,
            "streak": 1,
            "weak_terms": [],
        }
        for locale in INTERFACE_LOCALES:
            with self.subTest(locale=locale):
                rendered = companion.render_mirror_progress_focus(
                    snapshot,
                    locale=locale,
                )
                self.assertEqual(len(rendered.splitlines()), 2)
                self.assertTrue(rendered.splitlines()[0].startswith("📊 "))
                self.assertTrue(rendered.splitlines()[1].startswith("👉 "))
                self.assertLessEqual(len(rendered), 180)
                self.assertIn("94", rendered)
                self.assertIn("15", rendered)
                self.assertNotIn("historical_accuracy_series", rendered)
                self.assertNotIn("конкретно пройденных", rendered.casefold())
                self.assertNotIn("historical trend", rendered.casefold())

    def test_ac2_natural_followups_continue_only_with_recent_context(self):
        history = zerkalo.recent_turns(4)
        self.assertEqual(set(self.NATURAL_FOLLOWUPS), set(INTERFACE_LOCALES))
        for locale, question in self.NATURAL_FOLLOWUPS.items():
            with self.subTest(locale=locale, history=True):
                self.assertTrue(
                    companion.is_mirror_continuation(
                        question,
                        recent_dialogue=history,
                    )
                )
            with self.subTest(locale=locale, history=False):
                self.assertFalse(
                    companion.is_mirror_continuation(
                        question,
                        recent_dialogue=[],
                    )
                )


class AIProgressContextHandlerTest(unittest.IsolatedAsyncioTestCase):
    async def invoke(self, *, consented: bool, consent_error: Exception | None = None):
        question = "привет, какой сейчас прогресс?"
        update, context, message = zerkalo.text_surface(
            question,
            locale="ru",
            user_id=991,
        )
        store = zerkalo.HandlerStore()
        store.product_profile = Mock(return_value=zerkalo.admitted_profile())
        store.has_consent = Mock(
            return_value=consented,
            side_effect=consent_error,
        )
        store.append_mirror_exchange = Mock()
        store.ai_usage_summary = Mock(return_value={"available_credits": 3})
        store.reserve_ai_usage = Mock()
        snapshot = {
            "has_progress": True,
            "accuracy_percent": 94,
            "tracked_words": 15,
            "due_count": 0,
            "streak": 1,
            "weak_terms": [],
        }
        service = SimpleNamespace(ask=AsyncMock(return_value="WRONG PROVIDER"))
        settings = SimpleNamespace(
            enabled=True,
            initial_credits=40,
            consent_version="ai-memory-v1",
            processing_notice="history retained for 7 days",
        )
        with (
            patch.object(bot, "DatabaseStore", zerkalo.HandlerStore),
            patch.object(bot, "get_store", return_value=store),
            patch.object(bot, "get_bot_profile", return_value=zerkalo.mirror_profile()),
            patch.object(bot, "_mirror_preferences", return_value=zerkalo.mirror_preferences()),
            patch.object(bot, "_mirror_control_policy", return_value=zerkalo.mirror_policy()),
            patch.object(bot, "grounded_progress_snapshot", return_value=snapshot),
            patch.object(bot, "get_ai_tutor_service", return_value=service),
            patch.object(bot, "AI_SETTINGS", settings),
            patch.object(
                bot,
                "MIRROR_MEMORY_SETTINGS",
                SimpleNamespace(enabled=True, retention_days=7),
            ),
        ):
            await bot.handle_mirror_question(update, context, question=question)
        return context, message, store, service, snapshot

    async def test_ac1_ac2_progress_is_free_and_remembered_after_current_consent(self):
        _context, message, store, service, snapshot = await self.invoke(
            consented=True
        )
        rendered = companion.render_mirror_progress_focus(snapshot, locale="ru")
        message.reply_text.assert_awaited_once_with(rendered)
        service.ask.assert_not_awaited()
        store.ai_usage_summary.assert_not_called()
        store.reserve_ai_usage.assert_not_called()
        store.append_mirror_exchange.assert_called_once_with(
            991,
            question="привет, какой сейчас прогресс?",
            answer=rendered,
            retention_days=7,
        )

    async def test_ec1_progress_stays_free_without_persisting_before_consent(self):
        _context, message, store, service, snapshot = await self.invoke(
            consented=False
        )
        message.reply_text.assert_awaited_once_with(
            companion.render_mirror_progress_focus(snapshot, locale="ru")
        )
        service.ask.assert_not_awaited()
        store.ai_usage_summary.assert_not_called()
        store.reserve_ai_usage.assert_not_called()
        store.append_mirror_exchange.assert_not_called()

    async def test_err1_consent_read_failure_keeps_free_progress_available(self):
        _context, message, store, service, snapshot = await self.invoke(
            consented=False,
            consent_error=RuntimeError("database unavailable"),
        )
        message.reply_text.assert_awaited_once_with(
            companion.render_mirror_progress_focus(snapshot, locale="ru")
        )
        service.ask.assert_not_awaited()
        store.ai_usage_summary.assert_not_called()
        store.reserve_ai_usage.assert_not_called()
        store.append_mirror_exchange.assert_not_called()


if __name__ == "__main__":
    unittest.main()
