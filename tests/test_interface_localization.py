import os
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch


os.environ.setdefault("BOT_TOKEN", "123456:TESTTOKEN")
os.environ.setdefault("ALLOWED_USER_ID", "1")

import bot
from mydictionary.bot_profile import BOT_PROFILE_DEFAULTS, render_start_text
from mydictionary.localization import (
    INTERFACE_LOCALES,
    catalog_is_complete,
    normalize_locale,
    translate,
)
from mydictionary.mirror_assistant import (
    build_mirror_provider_payload,
    render_mirror_capabilities,
    render_mirror_greeting,
)


class LocaleContractTest(unittest.TestCase):
    def test_eight_interface_locales_are_complete(self):
        self.assertEqual(
            INTERFACE_LOCALES,
            frozenset({"en", "fr", "de", "ja", "ar", "zh", "ru", "es"}),
        )
        self.assertTrue(catalog_is_complete())

    def test_telegram_locale_normalization_handles_regional_variants(self):
        self.assertEqual(normalize_locale("fr-FR"), "fr")
        self.assertEqual(normalize_locale("pt-BR"), "en")
        self.assertEqual(normalize_locale("zh-hant"), "zh")
        self.assertEqual(normalize_locale("JA_jp"), "ja")

    def test_start_text_and_primary_keyboard_follow_interface_locale(self):
        french = render_start_text(BOT_PROFILE_DEFAULTS, "Marc", locale="fr")
        self.assertTrue(french.startswith("Bonjour, Marc"))
        self.assertEqual(
            bot.start_keyboard("fr").inline_keyboard[0][0].text,
            "▶️ Leçon du jour",
        )

        japanese = render_start_text(BOT_PROFILE_DEFAULTS, "Aki", locale="ja")
        self.assertTrue(japanese.startswith("Akiさん、こんにちは"))
        self.assertEqual(
            bot.start_keyboard("ja").inline_keyboard[0][0].text,
            "▶️ 今日のレッスン",
        )

    def test_topic_start_lesson_action_is_localized_in_every_interface_locale(self):
        for locale in INTERFACE_LOCALES:
            with self.subTest(locale=locale):
                button = bot.build_topic_keyboard("ja", locale=locale).inline_keyboard[0][0]
                self.assertEqual(button.text, translate("start_lesson", locale))
                self.assertEqual(button.callback_data, "start:daily")

    def test_onboarding_copy_is_available_in_every_locale(self):
        russian = translate("onboarding_intro", "ru")
        for locale in INTERFACE_LOCALES:
            with self.subTest(locale=locale):
                if locale != "ru":
                    self.assertNotEqual(translate("onboarding_intro", locale), russian)
                self.assertTrue(translate("onboarding_choose_native", locale))
                self.assertTrue(translate("onboarding_choose_pack", locale))
                self.assertTrue(translate("onboarding_choose_pace", locale))


class HomeSurfaceLocaleTest(unittest.IsolatedAsyncioTestCase):
    async def test_french_topics_home_action_localizes_prompt_and_topics(self):
        pack = bot.CATALOG.require("ja-basics-100")
        query = SimpleNamespace(
            data="start:topics",
            answer=AsyncMock(),
            message=SimpleNamespace(chat_id=123),
        )
        update = SimpleNamespace(
            callback_query=query,
            effective_user=SimpleNamespace(id=1, language_code="fr"),
        )
        context = SimpleNamespace(
            user_data={},
            bot=SimpleNamespace(send_message=AsyncMock()),
        )

        with patch.object(bot, "active_content_pack", return_value=pack):
            await bot.start_menu_cb.__wrapped__(update, context)

        payload = context.bot.send_message.await_args.kwargs
        self.assertIn("Choisissez un thème :", payload["text"])
        button_texts = [
            button.text
            for row in payload["reply_markup"].inline_keyboard
            for button in row
        ]
        self.assertIn("🌐 Tous les mots (100)", button_texts)
        self.assertIn("👋 Salutations (10)", button_texts)
        self.assertNotRegex(" ".join(button_texts), r"[А-Яа-яЁё]")
        self.assertNotIn("Выбери тему", payload["text"])

    async def test_french_empty_review_localizes_message_and_cta(self):
        pack = bot.CATALOG.require("ja-basics-100")
        context = SimpleNamespace(
            user_data={"interface_locale": "fr"},
            bot=SimpleNamespace(send_message=AsyncMock()),
        )
        query = SimpleNamespace(message=SimpleNamespace(chat_id=123))

        with (
            patch.object(bot, "active_content_pack", return_value=pack),
            patch.object(bot, "daily_lesson_size", return_value=5),
            patch.object(bot, "due_word_indices", return_value=[]),
            patch.object(bot, "record_product_event"),
        ):
            await bot.start_home_lesson(query, context, lesson_kind="review")

        payload = context.bot.send_message.await_args.kwargs
        self.assertIn("Tout est révisé pour aujourd’hui", payload["text"])
        self.assertIn("commencer une nouvelle leçon", payload["text"])
        button = payload["reply_markup"].inline_keyboard[0][0]
        self.assertEqual(button.text, "▶️ Commencer une nouvelle leçon")
        self.assertNotIn("всё повторено", payload["text"])
        self.assertNotIn("Начать новый урок", button.text)

    def test_french_settings_localize_labels_styles_and_depth(self):
        pack = bot.CATALOG.require("ja-basics-100")
        product = {
            "daily_word_goal": 10,
            "mirror_mode": "teacher",
            "mirror_depth": "balanced",
            "mirror_level": "adaptive",
        }
        mirror_policy = {
            "enabled_modes": ["teacher", "conversation", "brief", "practice"]
        }

        text = bot.settings_text(pack, product, locale="fr")
        keyboard = bot.settings_keyboard(
            product,
            mirror_policy=mirror_policy,
            locale="fr",
        )

        self.assertIn("⚙️ *Réglages*", text)
        self.assertIn(f"Langue : *{pack.label}*", text)
        self.assertNotIn(pack.title, text)
        self.assertIn("Cartes par leçon", text)
        self.assertIn("Style IA : *Professeur*", text)
        self.assertIn("Profondeur", text)
        self.assertIn("niveau : *Auto*", text)
        button_texts = [
            button.text
            for row in keyboard.inline_keyboard
            for button in row
        ]
        for expected in (
            "Professeur ✓",
            "Conversation",
            "Concis",
            "Pratique",
            "Court",
            "Équilibré ✓",
            "Approfondi",
            "Auto ✓",
        ):
            self.assertIn(expected, button_texts)
        combined = f"{text} {' '.join(button_texts)}"
        for russian_ui in (
            "Настройки",
            "Карточек в уроке",
            "Преподаватель",
            "Собеседник",
            "Кратко",
            "Практика",
            "Баланс",
            "Глубоко",
            "Авто",
            "Выбери язык",
        ):
            self.assertNotIn(russian_ui, combined)

    def test_french_stats_localize_metrics_and_empty_weak_words(self):
        pack = bot.CATALOG.require("ja-basics-100")
        words = [{
            "correct_count": 0,
            "wrong_count": 0,
            "last_seen": None,
            "next_review": None,
        }]
        progress = {
            "xp": 0,
            "streak": 0,
            "streak_best": 0,
            "today_xp": 0,
            "total_correct": 0,
            "total_wrong": 0,
        }

        with (
            patch.object(bot, "W", return_value=words),
            patch.object(bot, "active_content_pack", return_value=pack),
            patch.dict(bot.PROGRESS, progress, clear=False),
        ):
            text = bot.format_stats_text(locale="fr")

        for expected in (
            "📊 *Statistiques*",
            "Niveau 1 · Débutant",
            "Série",
            "Aujourd’hui",
            "Mots",
            "Étudiés",
            "Maîtrisés",
            "À réviser",
            "Bonnes réponses",
            "Erreurs",
            "Précision",
            "*Mots à renforcer:*",
            "Aucun pour le moment",
        ):
            self.assertIn(expected, text)
        for russian_ui in (
            "Статистика",
            "Новичок",
            "Серия",
            "Сегодня",
            "Изучено",
            "Выучено",
            "На повторение",
            "Правильных",
            "Ошибок",
            "Точность",
            "Слабые слова",
            "Пока нет",
            "до уровня",
        ):
            self.assertNotIn(russian_ui, text)


class MirrorLocaleContractTest(unittest.TestCase):
    def test_free_mirror_responses_follow_locale(self):
        greeting = render_mirror_greeting(
            locale="es", first_name="Ana", target_language="fr"
        )
        self.assertIn("Hola, Ana", greeting)
        self.assertIn("francés", greeting.lower())
        self.assertIn("puedo", render_mirror_capabilities("", locale="es").lower())
        self.assertTrue(
            render_mirror_greeting(locale="ja", target_language="en").startswith(
                "こんにちは"
            )
        )

    def test_billable_payload_has_immutable_response_language_instruction(self):
        payload = build_mirror_provider_payload(
            question="Explique bonjour",
            admin_guidance="Answer as a careful language teacher.",
            grounded_snapshot={"has_progress": False},
            interface_locale="fr-FR",
        )
        self.assertEqual(payload["interface_locale"], "fr")
        self.assertIn("French", payload["response_language_instruction"])

        with self.assertRaisesRegex(ValueError, "Unsupported interface locale"):
            build_mirror_provider_payload(
                question="Explain bonjour",
                admin_guidance="Answer as a careful language teacher.",
                grounded_snapshot={"has_progress": False},
                interface_locale="pt-BR",
            )

    def test_legacy_direct_calls_keep_russian_default(self):
        self.assertTrue(
            render_start_text(BOT_PROFILE_DEFAULTS, "Макс").startswith(
                "Привет, Макс!"
            )
        )
        self.assertEqual(
            bot.start_keyboard().inline_keyboard[0][0].text,
            "▶️ Урок на сегодня",
        )


if __name__ == "__main__":
    unittest.main()
