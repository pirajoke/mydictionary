import ast
from contextlib import nullcontext
import os
from pathlib import Path
import re
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, call, patch


os.environ.setdefault("BOT_TOKEN", "123456:TESTTOKEN")
os.environ.setdefault("ALLOWED_USER_ID", "1")
os.environ.setdefault("ALLOW_SQLITE_DEV", "true")

import bot
from mydictionary.admin_store import AdminStore
from mydictionary.bot_profile import BOT_PROFILE_DEFAULTS
from mydictionary.localization import (
    INTERFACE_LOCALES,
    catalog_is_complete,
    translate,
)
from mydictionary.storage import DatabaseStore
from mydictionary.voice_tutor import VoiceWord


class FrenchUserSurfaceLocalizationTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        bot.PROGRESS["active_lang"] = "ja"
        bot.PROGRESS["active_pack_id"] = "ja-basics-100"
        self.pack = bot.CATALOG.require("ja-basics-100")

    def test_french_command_menu_has_no_russian_chrome(self):
        commands = {
            command.command: command.description
            for command in bot.build_bot_commands(
                ai_enabled=True,
                locale="fr",
            )
        }

        self.assertEqual(
            commands,
            {
                "start": "Leçon du jour",
                "learn": "Choisir un thème",
                "lang": "Changer de langue",
                "stats": "Ma progression",
                "ai": "Tuteur IA",
                "privacy": "Données et confidentialité",
                "help": "Aide",
            },
        )
        for russian_ui in (
            "Урок",
            "Выбрать",
            "Сменить",
            "прогресс",
            "репетитор",
            "приватность",
            "Помощь",
        ):
            self.assertNotIn(russian_ui, " ".join(commands.values()))

    def test_french_voice_prompt_localizes_chrome_but_keeps_learning_content(self):
        word = VoiceWord(
            vocabulary_id="word-1",
            target="私",
            speech="わたし",
            transcription="watashi",
            meaning_ru="я",
        )

        text = bot.voice_prompt_text(
            self.pack,
            word,
            position=1,
            total=5,
            mode="pronunciation",
            locale="fr",
        )

        self.assertIn("🎤 Prononciation · 1/5", text)
        self.assertIn("Prononcez uniquement ce mot dans un message vocal.", text)
        self.assertIn("🇷🇺 я", text)
        for russian_ui in (
            "Произношение",
            "Скажи только это слово",
            "Я распознаю речь",
            "Проверяется распознанный текст",
        ):
            self.assertNotIn(russian_ui, text)

    async def test_french_privacy_command_localizes_copy_and_actions(self):
        message = SimpleNamespace(reply_text=AsyncMock())
        update = SimpleNamespace(
            effective_message=message,
            effective_user=SimpleNamespace(id=11, language_code="fr"),
        )
        context = SimpleNamespace(user_data={"interface_locale": "fr"})
        store = SimpleNamespace(has_consent=lambda *_args, **_kwargs: False)

        with (
            patch.object(bot, "get_store", return_value=store),
            patch.object(
                bot,
                "VOICE_SETTINGS",
                SimpleNamespace(consent_version="voice-v1"),
            ),
            patch.object(
                bot,
                "AI_SETTINGS",
                SimpleNamespace(consent_version="ai-v1"),
            ),
            patch.object(
                bot,
                "MIRROR_MEMORY_SETTINGS",
                SimpleNamespace(enabled=False, retention_days=7),
            ),
        ):
            await bot.cmd_privacy.__wrapped__(update, context)

        payload = message.reply_text.await_args
        text = payload.args[0]
        self.assertIn("Confidentialité MY DICTIONARY", text)
        button_texts = [
            button.text
            for row in payload.kwargs["reply_markup"].inline_keyboard
            for button in row
        ]
        self.assertIn("Supprimer mes données d’apprentissage", button_texts)
        for russian_ui in (
            "Приватность",
            "Учебная история",
            "AI-согласие",
            "Удалить мои учебные данные",
            "Согласие на обработку голоса",
        ):
            self.assertNotIn(russian_ui, f"{text} {' '.join(button_texts)}")

    async def test_french_disabled_buy_command_localizes_fail_closed_message(self):
        message = SimpleNamespace(reply_text=AsyncMock())
        update = SimpleNamespace(
            message=message,
            effective_user=SimpleNamespace(id=12, language_code="fr"),
        )
        context = SimpleNamespace(user_data={"interface_locale": "fr"})

        with patch.object(
            bot,
            "BILLING_SETTINGS",
            SimpleNamespace(enabled=False),
        ):
            await bot.cmd_buy.__wrapped__(update, context)

        text = message.reply_text.await_args.args[0]
        self.assertEqual(
            text,
            "L’achat de crédits IA n’est pas disponible pour le moment.",
        )
        self.assertNotIn("Покупка AI-кредитов", text)

    async def test_french_legacy_flash_command_localizes_reveal_action(self):
        message = SimpleNamespace(chat_id=123, reply_text=AsyncMock())
        update = SimpleNamespace(
            message=message,
            effective_user=SimpleNamespace(id=13, language_code="fr"),
        )
        context = SimpleNamespace(user_data={"interface_locale": "fr"})

        with (
            patch.object(bot, "pick_word", return_value=10),
            patch.object(bot, "active_content_pack", return_value=self.pack),
            patch.object(bot, "send_pronunciation", new=AsyncMock()),
        ):
            await bot.cmd_flash.__wrapped__(update, context)

        payload = message.reply_text.await_args
        button = payload.kwargs["reply_markup"].inline_keyboard[0][0]
        self.assertEqual(button.text, "👁 Afficher le sens")
        self.assertNotIn("Показать значение", button.text)
        self.assertIn("watashi", payload.args[0])

    async def test_french_ai_consent_and_usage_stats_localize_only_chrome(self):
        processing_notice = "NOTICE-CONFIGURÉE À CONSERVER MOT POUR MOT"
        settings = SimpleNamespace(
            enabled=True,
            processing_notice=processing_notice,
            consent_version="ai-v1",
            initial_credits=0,
        )
        context = SimpleNamespace(user_data={"interface_locale": "fr"})
        store = SimpleNamespace(
            ai_usage_summary=lambda *_args, **_kwargs: {
                "available_credits": 7,
                "reserved_credits": 1,
                "spent_credits": 2,
                "completed_requests": 3,
                "failed_requests": 1,
            }
        )

        with (
            patch.object(bot, "AI_SETTINGS", settings),
            patch.object(bot, "get_store", return_value=store),
        ):
            with self.subTest(surface="consent_request"):
                consent_message = SimpleNamespace(reply_text=AsyncMock())
                await bot.request_ai_processing_consent(
                    consent_message,
                    context,
                    request_kind="command",
                    locale="fr",
                )
                payload = consent_message.reply_text.await_args
                self.assertIn("Consentement au traitement par l’IA", payload.args[0])
                self.assertIn(processing_notice, payload.args[0])
                buttons = [
                    button.text
                    for row in payload.kwargs["reply_markup"].inline_keyboard
                    for button in row
                ]
                self.assertEqual(buttons, ["Accepter et continuer", "Annuler"])
                self.assertNotIn("Согласие", payload.args[0])

            with self.subTest(surface="usage_stats"):
                stats_message = SimpleNamespace(reply_text=AsyncMock())
                update = SimpleNamespace(
                    message=stats_message,
                    effective_user=SimpleNamespace(id=21, language_code="fr"),
                )
                await bot.cmd_ai_stats.__wrapped__(update, context)
                text = stats_message.reply_text.await_args.args[0]
                for expected in (
                    "Utilisation de l’IA",
                    "Crédits disponibles : 7",
                    "Réservés : 1",
                    "Utilisés : 2",
                    "Requêtes : 3 réussies, 1 remboursée",
                ):
                    self.assertIn(expected, text)
                self.assertNotIn("AI-использование", text)

    async def test_french_mirror_feedback_and_response_format_localize_chrome(self):
        store = SimpleNamespace(
            rate_mirror_response=lambda *_args, **_kwargs: True,
            set_mirror_response_mode=lambda *_args, **_kwargs: "both",
        )
        context = SimpleNamespace(
            user_data={"interface_locale": "fr"},
            args=["both"],
        )

        with patch.object(bot, "get_store", return_value=store):
            with self.subTest(surface="feedback_buttons"):
                keyboard = bot.mirror_feedback_keyboard("request-1", locale="fr")
                self.assertEqual(
                    [button.text for button in keyboard.inline_keyboard[0]],
                    ["Utile", "Pas utile"],
                )

            with self.subTest(surface="feedback_status"):
                query = SimpleNamespace(
                    data="mirrorfb:request-1:helpful",
                    answer=AsyncMock(),
                    edit_message_reply_markup=AsyncMock(),
                )
                update = SimpleNamespace(
                    callback_query=query,
                    effective_user=SimpleNamespace(id=22, language_code="fr"),
                )
                await bot.mirror_feedback_cb.__wrapped__(update, context)
                query.answer.assert_awaited_once_with("Merci")

            with self.subTest(surface="response_format"):
                message = SimpleNamespace(reply_text=AsyncMock())
                update = SimpleNamespace(
                    message=message,
                    effective_user=SimpleNamespace(id=22, language_code="fr"),
                )
                await bot.cmd_mirror_response.__wrapped__(update, context)
                text = message.reply_text.await_args.args[0]
                self.assertEqual(text, "Format des réponses Mirror : both.")
                self.assertNotIn("Формат ответов", text)

    async def test_french_voice_entry_consent_and_feedback_preserve_content(self):
        processing_notice = "VOICE-NOTICE-CONFIGURÉE-INCHANGÉE"
        voice_settings = SimpleNamespace(
            enabled=True,
            processing_notice=processing_notice,
            consent_version="voice-v1",
        )
        translation_settings = SimpleNamespace(enabled=False)
        context = SimpleNamespace(user_data={"interface_locale": "fr"})

        with (
            patch.object(bot, "VOICE_SETTINGS", voice_settings),
            patch.object(bot, "VOICE_TRANSLATION_SETTINGS", translation_settings),
        ):
            with self.subTest(surface="entry"):
                message = SimpleNamespace(reply_text=AsyncMock())
                update = SimpleNamespace(
                    effective_message=message,
                    effective_user=SimpleNamespace(id=23, language_code="fr"),
                )
                await bot.cmd_voice.__wrapped__(update, context)
                payload = message.reply_text.await_args
                self.assertIn("🎙 Messages vocaux", payload.args[0])
                buttons = [
                    button.text
                    for row in payload.kwargs["reply_markup"].inline_keyboard
                    for button in row
                ]
                self.assertEqual(
                    buttons,
                    ["🎤 Prononcer 10 mots", "💬 Phrases du bloc"],
                )
                self.assertNotIn("Голосовые сообщения", payload.args[0])

            with self.subTest(surface="consent"):
                consent_message = SimpleNamespace(reply_text=AsyncMock())
                await bot.request_voice_processing_consent(
                    consent_message,
                    context,
                    mode="pronunciation",
                    locale="fr",
                )
                payload = consent_message.reply_text.await_args
                self.assertIn("Consentement au traitement vocal", payload.args[0])
                self.assertIn(processing_notice, payload.args[0])
                buttons = [
                    button.text
                    for row in payload.kwargs["reply_markup"].inline_keyboard
                    for button in row
                ]
                self.assertEqual(buttons, ["Accepter et commencer", "Annuler"])

            with self.subTest(surface="feedback"):
                feedback = SimpleNamespace(
                    transcript="bonjour privé",
                    expected=VoiceWord(
                        vocabulary_id="word-2",
                        target="私",
                        speech="わたし",
                        transcription="watashi",
                        meaning_ru="я",
                    ),
                    code="exact",
                    matched=None,
                )
                result = SimpleNamespace(feedback=feedback, available_credits=3)
                text = bot.voice_feedback_text(result, locale="fr")
                self.assertIn("Reconnu : bonjour privé", text)
                self.assertIn("Sens : я", text)
                self.assertIn("Mot : 私", text)
                self.assertIn("Transcription : watashi", text)
                self.assertIn("✅ Correct. Passage au mot suivant.", text)
                self.assertNotIn("Распознано", text)

    async def test_french_privacy_callbacks_localize_request_cancel_and_revoke(self):
        store = SimpleNamespace(revoke_consent=lambda *_args, **_kwargs: 1)

        def callback(action: str):
            query = SimpleNamespace(
                data=f"privacy:{action}",
                answer=AsyncMock(),
                edit_message_text=AsyncMock(),
            )
            update = SimpleNamespace(
                callback_query=query,
                effective_user=SimpleNamespace(id=24, language_code="fr"),
            )
            context = SimpleNamespace(
                user_data={
                    "interface_locale": "fr",
                    "pending_ai_consent": {"request_kind": "command"},
                }
            )
            return update, context, query

        with (
            patch.object(bot, "get_store", return_value=store),
            patch.object(bot, "record_product_event"),
        ):
            with self.subTest(action="request"):
                update, context, query = callback("request")
                await bot.privacy_cb.__wrapped__(update, context)
                text = query.edit_message_text.await_args.args[0]
                self.assertIn("Supprimer le profil d’apprentissage", text)
                buttons = [
                    button.text
                    for row in query.edit_message_text.await_args.kwargs[
                        "reply_markup"
                    ].inline_keyboard
                    for button in row
                ]
                self.assertEqual(buttons, ["Confirmer la suppression", "Annuler"])
                self.assertNotIn("Удалить учебный профиль", text)

            with self.subTest(action="cancel"):
                update, context, query = callback("cancel")
                await bot.privacy_cb.__wrapped__(update, context)
                query.answer.assert_awaited_once_with("Suppression annulée.")
                query.edit_message_text.assert_awaited_once_with(
                    "Les données d’apprentissage n’ont pas été modifiées."
                )

            with self.subTest(action="ai_revoke"):
                update, context, query = callback("ai_revoke")
                await bot.privacy_cb.__wrapped__(update, context)
                query.answer.assert_awaited_once_with("Consentement révoqué.")
                text = query.edit_message_text.await_args.args[0]
                self.assertIn("traitement par l’IA a été révoqué", text)
                self.assertIn("Enregistrements modifiés : 1", text)
                self.assertNotIn("Согласие на обработку AI", text)

    async def test_ac1_ec1_ec2_profile_sync_installs_all_localized_command_menus(self):
        telegram_bot = SimpleNamespace(
            set_my_commands=AsyncMock(),
            set_my_name=AsyncMock(),
            set_my_short_description=AsyncMock(),
            set_my_description=AsyncMock(),
        )
        profile = {
            "bot_name": "MY DICTIONARY",
            "bot_short_description": "Configured short description",
            "bot_description": "Configured description",
        }

        with patch.object(bot, "get_bot_profile", return_value=profile):
            await bot.sync_telegram_profile(telegram_bot)

        command_calls = telegram_bot.set_my_commands.await_args_list
        self.assertEqual(len(command_calls), 1 + len(INTERFACE_LOCALES))

        def command_map(commands):
            return {
                command.command: command.description
                for command in commands
            }

        expected_english = command_map(
            bot.build_bot_commands(
                ai_enabled=bot.AI_SETTINGS.enabled,
                locale="en",
            )
        )
        self.assertEqual(command_calls[0].kwargs, {})
        self.assertEqual(command_map(command_calls[0].args[0]), expected_english)

        scoped = {
            call.kwargs.get("language_code"): command_map(call.args[0])
            for call in command_calls[1:]
        }
        self.assertEqual(set(scoped), set(INTERFACE_LOCALES))
        for locale in INTERFACE_LOCALES:
            with self.subTest(locale=locale):
                self.assertEqual(
                    scoped[locale],
                    command_map(
                        bot.build_bot_commands(
                            ai_enabled=bot.AI_SETTINGS.enabled,
                            locale=locale,
                        )
                    ),
                )

        for unsupported in (None, "", "pt-BR"):
            with self.subTest(fallback=unsupported):
                self.assertEqual(
                    command_map(
                        bot.build_bot_commands(
                            ai_enabled=bot.AI_SETTINGS.enabled,
                            locale=unsupported,
                        )
                    ),
                    expected_english,
                )
        self.assertEqual(
            command_map(
                bot.build_bot_commands(ai_enabled=bot.AI_SETTINGS.enabled)
            ),
            expected_english,
        )
        russian = command_map(
            bot.build_bot_commands(
                ai_enabled=bot.AI_SETTINGS.enabled,
                locale="ru",
            )
        )
        self.assertEqual(russian["start"], "Урок на сегодня")
        self.assertNotEqual(russian, expected_english)
        self.assertTrue(catalog_is_complete())

    async def test_ac2_french_help_localizes_chrome(self):
        message = SimpleNamespace(reply_text=AsyncMock())
        update = SimpleNamespace(
            message=message,
            effective_user=SimpleNamespace(id=31, language_code="fr"),
        )
        context = SimpleNamespace(user_data={"interface_locale": "fr"})

        with patch.object(
            bot,
            "get_bot_profile",
            return_value=dict(BOT_PROFILE_DEFAULTS),
        ):
            await bot.cmd_help.__wrapped__(update, context)

        text = message.reply_text.await_args.args[0]
        for expected in (
            "/start — leçon du jour",
            "/privacy — données et confidentialité",
            "Afficher le sens",
        ):
            self.assertIn(expected, text)
        for russian_ui in (
            "урок на сегодня",
            "данные и приватность",
            "Показать значение",
            "помощь",
        ):
            self.assertNotIn(russian_ui, text)

    async def test_ac5_french_stars_surfaces_preserve_configured_commercial_content(self):
        terms_document = "TERMS-v9 — DOCUMENT CONFIGURÉ À CONSERVER"
        seller_name = "Example Seller SAS"
        seller_address = "10 rue Exemple, Paris"
        seller_email = "billing@example.test"
        seller_phone = "+33 1 00 00 00 00"
        support_contact = "@example_support"
        settings = SimpleNamespace(
            enabled=True,
            terms_text=terms_document,
            terms_version="terms-v9",
            seller_legal_name=seller_name,
            seller_address=seller_address,
            seller_email=seller_email,
            seller_phone=seller_phone,
            support_contact=support_contact,
        )
        product = {
            "product_id": "credits-small",
            "title": "Pack Débutant 25",
            "price_xtr": 25,
        }
        service = SimpleNamespace(
            active_products=lambda: [product],
            subscriptions_for_user=lambda _user_id: [],
        )
        context = SimpleNamespace(user_data={"interface_locale": "fr"})

        with (
            patch.object(bot, "BILLING_SETTINGS", settings),
            patch.object(bot, "get_billing_service", return_value=service),
            patch.object(bot, "TELEGRAM_RUNTIME", SimpleNamespace(is_test=False)),
        ):
            with self.subTest(surface="terms"):
                message = SimpleNamespace(reply_text=AsyncMock())
                await bot.send_billing_terms(message, locale="fr")
                payload = message.reply_text.await_args
                text = payload.args[0]
                self.assertIn("Conditions d’achat des crédits IA", text)
                for configured_content in (
                    terms_document,
                    seller_name,
                    seller_address,
                    seller_email,
                    seller_phone,
                    support_contact,
                    "terms-v9",
                ):
                    self.assertIn(configured_content, text)
                button = payload.kwargs["reply_markup"].inline_keyboard[0][0]
                self.assertEqual(
                    button.text,
                    "J’accepte et je souhaite commencer immédiatement",
                )
                for russian_ui in (
                    "Условия покупки",
                    "Продавец:",
                    "Версия:",
                    "принимаю условия",
                ):
                    self.assertNotIn(russian_ui, text)

            with self.subTest(surface="catalog"):
                message = SimpleNamespace(reply_text=AsyncMock())
                await bot.send_billing_products(message, locale="fr")
                payload = message.reply_text.await_args
                self.assertEqual(
                    payload.args[0],
                    "Choisissez un pack de crédits IA :",
                )
                button = payload.kwargs["reply_markup"].inline_keyboard[0][0]
                self.assertIn(product["title"], button.text)
                self.assertNotIn("Выбери пакет", payload.args[0])

            with self.subTest(surface="support"):
                message = SimpleNamespace(reply_text=AsyncMock())
                update = SimpleNamespace(
                    message=message,
                    effective_user=SimpleNamespace(id=32, language_code="fr"),
                )
                handler = getattr(bot.cmd_paysupport, "__wrapped__", bot.cmd_paysupport)
                await handler(update, context)
                text = message.reply_text.await_args.args[0]
                self.assertIn("Assistance pour les paiements", text)
                for configured_content in (
                    support_contact,
                    seller_name,
                    seller_email,
                    seller_phone,
                ):
                    self.assertIn(configured_content, text)
                self.assertNotIn("Поддержка по платежам", text)
                self.assertNotIn("Продавец:", text)

            with self.subTest(surface="subscriptions"):
                message = SimpleNamespace(reply_text=AsyncMock())
                update = SimpleNamespace(
                    message=message,
                    effective_user=SimpleNamespace(id=32, language_code="fr"),
                )
                await bot.cmd_subscriptions.__wrapped__(update, context)
                self.assertEqual(
                    message.reply_text.await_args.args[0],
                    "Aucun abonnement Stars actif.",
                )

            with self.subTest(surface="callback"):
                query = SimpleNamespace(
                    data="billing:unknown",
                    answer=AsyncMock(),
                )
                update = SimpleNamespace(
                    callback_query=query,
                    effective_user=SimpleNamespace(id=32, language_code="fr"),
                )
                await bot.billing_consent_cb.__wrapped__(update, context)
                query.answer.assert_awaited_once_with(
                    "Action inconnue.",
                    show_alert=True,
                )

    async def test_ac6_french_legacy_exercises_localize_chrome_and_keep_content(self):
        idx = 10
        word = bot.W()[idx]
        meaning = bot.primary_meaning_for_word(word)

        with (
            patch.object(bot, "active_content_pack", return_value=self.pack),
            patch.object(bot, "pick_word", return_value=idx),
            patch.object(bot, "send_pronunciation", new=AsyncMock()),
        ):
            with self.subTest(surface="lang"):
                message = SimpleNamespace(reply_text=AsyncMock())
                update = SimpleNamespace(
                    message=message,
                    effective_user=SimpleNamespace(id=33, language_code="fr"),
                )
                context = SimpleNamespace(user_data={"interface_locale": "fr"})
                await bot.cmd_lang.__wrapped__(update, context)
                text = message.reply_text.await_args.args[0]
                self.assertIn(f"Pack actuel : *{self.pack.label}*", text)
                self.assertIn("Choisissez une langue :", text)
                self.assertNotIn(self.pack.title, text)

            with self.subTest(surface="quiz_prompt"):
                message = SimpleNamespace(chat_id=303, reply_text=AsyncMock())
                update = SimpleNamespace(
                    message=message,
                    effective_user=SimpleNamespace(id=33, language_code="fr"),
                )
                context = SimpleNamespace(user_data={"interface_locale": "fr"})
                await bot.cmd_quiz.__wrapped__(update, context)
                payload = message.reply_text.await_args
                self.assertIn("Choisissez la bonne traduction :", payload.args[0])
                options = [
                    button.text
                    for row in payload.kwargs["reply_markup"].inline_keyboard
                    for button in row
                ]
                self.assertIn(meaning, options)

            with self.subTest(surface="quiz_result"):
                query = SimpleNamespace(
                    data=f"quiz:{idx}:1:{meaning}",
                    message=SimpleNamespace(chat_id=303),
                    answer=AsyncMock(),
                    edit_message_text=AsyncMock(),
                )
                update = SimpleNamespace(
                    callback_query=query,
                    effective_user=SimpleNamespace(id=33, language_code="fr"),
                )
                context = SimpleNamespace(user_data={"interface_locale": "fr"})
                with patch.object(bot, "mark_correct", return_value=(5, 0)):
                    await bot.quiz_callback.__wrapped__(update, context)
                payload = query.edit_message_text.await_args
                self.assertIn("✅ Correct !", payload.args[0])
                self.assertIn(meaning, payload.args[0])
                for russian_ui in ("Правильно", "Ошибка", "Уровень", "Новичок"):
                    self.assertNotIn(russian_ui, payload.args[0])
                buttons = [
                    button.text
                    for row in payload.kwargs["reply_markup"].inline_keyboard
                    for button in row
                ]
                self.assertIn("Suivant ➡️", buttons)

            with self.subTest(surface="type_prompt_and_result"):
                message = SimpleNamespace(chat_id=303, reply_text=AsyncMock())
                update = SimpleNamespace(
                    message=message,
                    effective_user=SimpleNamespace(id=33, language_code="fr"),
                )
                context = SimpleNamespace(user_data={"interface_locale": "fr"})
                await bot.cmd_type.__wrapped__(update, context)
                self.assertIn(
                    "Écrivez la traduction :",
                    message.reply_text.await_args.args[0],
                )

                answer_message = SimpleNamespace(
                    text="mauvaise réponse",
                    chat_id=303,
                    reply_text=AsyncMock(),
                )
                answer_update = SimpleNamespace(
                    message=answer_message,
                    effective_user=SimpleNamespace(id=33, language_code="fr"),
                )
                with (
                    patch.object(bot, "meaning_answer_matches", return_value=False),
                    patch.object(bot, "mark_wrong", return_value=(0, 0)),
                ):
                    await bot.handle_type_answer.__wrapped__(answer_update, context)
                payload = answer_message.reply_text.await_args
                self.assertIn("❌ Erreur !", payload.args[0])
                self.assertIn("Votre réponse : _mauvaise réponse_", payload.args[0])
                self.assertIn(meaning, payload.args[0])
                for russian_ui in ("Ошибка", "Твой ответ", "Уровень", "Новичок"):
                    self.assertNotIn(russian_ui, payload.args[0])
                buttons = [
                    button.text
                    for row in payload.kwargs["reply_markup"].inline_keyboard
                    for button in row
                ]
                self.assertIn("Suivant ➡️", buttons)

            with self.subTest(surface="flash_follow_up"):
                query = SimpleNamespace(
                    data=f"flash_show:{idx}",
                    message=SimpleNamespace(chat_id=303),
                    answer=AsyncMock(),
                    edit_message_text=AsyncMock(),
                )
                update = SimpleNamespace(
                    callback_query=query,
                    effective_user=SimpleNamespace(id=33, language_code="fr"),
                )
                context = SimpleNamespace(user_data={"interface_locale": "fr"})
                await bot.flash_show.__wrapped__(update, context)
                payload = query.edit_message_text.await_args
                self.assertIn(meaning, payload.args[0])
                self.assertNotIn("Уровень", payload.args[0])
                buttons = [
                    button.text
                    for row in payload.kwargs["reply_markup"].inline_keyboard
                    for button in row
                ]
                self.assertIn("😵 Je ne sais pas", buttons)
                self.assertIn("✅ Je sais", buttons)

            with self.subTest(surface="smart_prompt_and_result"):
                message = SimpleNamespace(chat_id=303, reply_text=AsyncMock())
                update = SimpleNamespace(
                    message=message,
                    effective_user=SimpleNamespace(id=33, language_code="fr"),
                )
                context = SimpleNamespace(user_data={"interface_locale": "fr"})
                with (
                    patch.object(bot, "adaptive_mode", return_value="quiz"),
                    patch.object(
                        bot,
                        "build_quiz_options",
                        return_value=([meaning, "option 2", "option 3", "option 4"], 0),
                    ),
                ):
                    await bot.cmd_smart.__wrapped__(update, context)
                self.assertIn(
                    "Choisissez la traduction :",
                    message.reply_text.await_args.args[0],
                )

                query = SimpleNamespace(
                    data=f"smart:{idx}:1",
                    message=SimpleNamespace(chat_id=303),
                    answer=AsyncMock(),
                    edit_message_text=AsyncMock(),
                )
                update = SimpleNamespace(
                    callback_query=query,
                    effective_user=SimpleNamespace(id=33, language_code="fr"),
                )
                with patch.object(bot, "mark_correct", return_value=(5, 0)):
                    await bot.smart_quiz_cb.__wrapped__(update, context)
                payload = query.edit_message_text.await_args
                self.assertIn(meaning, payload.args[0])
                buttons = [
                    button.text
                    for row in payload.kwargs["reply_markup"].inline_keyboard
                    for button in row
                ]
                self.assertIn("Suivant ➡️", buttons)

            with self.subTest(surface="poll_prompt"):
                poll_message = SimpleNamespace(
                    reply_poll=AsyncMock(
                        return_value=SimpleNamespace(poll=SimpleNamespace(id="poll-1"))
                    )
                )
                update = SimpleNamespace(
                    message=poll_message,
                    effective_user=SimpleNamespace(id=33, language_code="fr"),
                )
                context = SimpleNamespace(
                    user_data={"interface_locale": "fr"},
                    bot_data={},
                )
                with patch.object(
                    bot,
                    "build_quiz_options",
                    return_value=([meaning, "option 2", "option 3", "option 4"], 0),
                ):
                    await bot.cmd_poll.__wrapped__(update, context)
                payload = poll_message.reply_poll.await_args
                self.assertTrue(payload.kwargs["question"].endswith("— traduction ?"))
                self.assertNotIn("перевод?", payload.kwargs["question"])
                self.assertIn(meaning, payload.kwargs["options"])

    async def test_ac7_pilot_notification_uses_persisted_french_without_identifier(self):
        recipient_id = 987654321
        notification_id = 42
        telegram_bot = SimpleNamespace(send_message=AsyncMock())
        store = SimpleNamespace(
            claim_telegram_notifications=lambda **_kwargs: [
                {
                    "notification_id": notification_id,
                    "telegram_user_id": recipient_id,
                    "kind": "pilot_access_approved",
                    "attempts": 1,
                }
            ],
            access_profile=lambda _user_id: {
                "access_status": "active",
                "language_code": "fr",
            },
            cancel_telegram_notification=unittest.mock.Mock(),
            retry_telegram_notification=unittest.mock.Mock(),
            complete_telegram_notification=unittest.mock.Mock(return_value=True),
        )

        with (
            patch.object(bot.logger, "info") as info_log,
            patch.object(bot.logger, "warning") as warning_log,
        ):
            delivered = await bot.deliver_telegram_notifications(
                telegram_bot,
                store,
            )

        self.assertEqual(delivered, 1)
        payload = telegram_bot.send_message.await_args
        text = payload.kwargs["text"]
        self.assertIn("Votre accès au pilote gratuit MY DICTIONARY est ouvert.", text)
        self.assertIn("Envoyez /start", text)
        self.assertNotIn(str(recipient_id), text)
        log_payload = " ".join(
            repr(call)
            for call in (
                *info_log.call_args_list,
                *warning_log.call_args_list,
            )
        )
        self.assertNotIn(str(recipient_id), log_payload)

    def test_ac1_ac2_ac3_ac4_ac5_ac6_active_surfaces_have_no_cyrillic_literals(self):
        learner_surface_functions = {
            "start_menu_cb",
            "settings_cb",
            "start_voice_mode",
            "launch_voice_mode",
            "voice_consent_cb",
            "voice_mode_cb",
            "voice_translation_consent_cb",
            "cmd_voice_stop",
            "cmd_voice_transcript",
            "voice_translation_result_text",
            "process_voice_practice_turn",
            "voice_message_handler",
            "send_ai_tutor_answer",
            "request_ai_tutor_answer",
            "send_mirror_response",
            "handle_mirror_question",
            "ai_consent_cb",
            "cmd_ai",
            "billing_open_cb",
            "billing_consent_cb",
            "buy_product_cb",
            "pre_checkout_handler",
            "successful_payment_handler",
            "cmd_subscriptions",
            "subscription_cb",
            "lang_switch_cb",
            "handle_lang_switch",
            "poll_answer_handler",
            "start_home_lesson",
            "cmd_learn",
            "learn_topic_cb",
            "block_topics_cb",
            "block_ai_cb",
            "_authorized_block_ai_cb",
            "block_voice_cb",
        }
        tree = ast.parse(Path(bot.__file__).read_text(encoding="utf-8"))
        function_nodes = {
            node.name: node
            for node in tree.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name in learner_surface_functions
        }
        self.assertEqual(set(function_nodes), learner_surface_functions)

        # Intentionally zero allowlist: learning, transcript, seller and legal
        # content must enter these functions as runtime values, not UI literals.
        cyrillic_literals = []
        for function_name in sorted(function_nodes):
            for node in ast.walk(function_nodes[function_name]):
                if (
                    isinstance(node, ast.Constant)
                    and isinstance(node.value, str)
                    and re.search(r"[А-Яа-яЁё]", node.value)
                ):
                    cyrillic_literals.append(
                        (function_name, node.lineno, node.value)
                    )
        if cyrillic_literals:
            rendered = "\n".join(
                f"{function}:{line}: {literal!r}"
                for function, line, literal in cyrillic_literals
            )
            self.fail(
                f"Found {len(cyrillic_literals)} Cyrillic UI literals in "
                f"{len({item[0] for item in cyrillic_literals})} active "
                f"learner-surface functions:\n{rendered}"
            )

    async def test_ac4_french_voice_stop_transcript_and_error_chrome(self):
        voice_word = VoiceWord(
            vocabulary_id="word-voice",
            target="私",
            speech="わたし",
            transcription="watashi",
            meaning_ru="я",
        )
        state = SimpleNamespace(session_id="voice-session", status="completed")
        service = SimpleNamespace(
            stop_session=Mock(side_effect=[True, False]),
            latest_session=Mock(return_value=state),
            turns=Mock(
                return_value=[
                    {
                        "expected_vocabulary_id": voice_word.vocabulary_id,
                        "transcript": "bonjour privé",
                        "feedback_code": "exact",
                    }
                ]
            ),
        )
        context = SimpleNamespace(user_data={"interface_locale": "fr"})

        with patch.object(bot, "get_voice_tutor_service", return_value=service):
            with self.subTest(surface="stop_active"):
                message = SimpleNamespace(reply_text=AsyncMock())
                update = SimpleNamespace(
                    message=message,
                    effective_user=SimpleNamespace(id=41, language_code="fr"),
                )
                await bot.cmd_voice_stop.__wrapped__(update, context)
                self.assertEqual(
                    message.reply_text.await_args.args[0],
                    "Session vocale arrêtée. Transcription : /voice_transcript.",
                )

            with self.subTest(surface="stop_inactive"):
                message = SimpleNamespace(reply_text=AsyncMock())
                update = SimpleNamespace(
                    message=message,
                    effective_user=SimpleNamespace(id=41, language_code="fr"),
                )
                await bot.cmd_voice_stop.__wrapped__(update, context)
                self.assertEqual(
                    message.reply_text.await_args.args[0],
                    "Aucune session vocale active.",
                )

            with self.subTest(surface="transcript"):
                message = SimpleNamespace(reply_text=AsyncMock())
                update = SimpleNamespace(
                    message=message,
                    effective_user=SimpleNamespace(id=41, language_code="fr"),
                )
                with patch.object(
                    bot,
                    "restore_voice_block",
                    return_value=(self.pack, [(10, voice_word)]),
                ):
                    await bot.cmd_voice_transcript.__wrapped__(update, context)
                text = message.reply_text.await_args.args[0]
                for expected in (
                    f"Transcription de la session vocale · {self.pack.label}",
                    "Statut : completed",
                    "Reconnu : bonjour privé",
                    "Résultat : exact",
                    "🇷🇺 я",
                    "🇯🇵 私",
                ):
                    self.assertIn(expected, text)
                for russian_ui in (
                    "Транскрипт",
                    "Статус:",
                    "Распознано:",
                    "Результат:",
                ):
                    self.assertNotIn(russian_ui, text)

        with self.subTest(surface="invalid_voice_error"):
            message = SimpleNamespace(
                voice=SimpleNamespace(duration=0, file_size=0),
                reply_text=AsyncMock(),
            )
            update = SimpleNamespace(
                message=message,
                effective_user=SimpleNamespace(id=41, language_code="fr"),
            )
            context = SimpleNamespace(user_data={"interface_locale": "fr"})
            store = SimpleNamespace(
                product_profile=lambda _user_id: {"access_status": "active"},
            )
            voice_settings = SimpleNamespace(
                enabled=True,
                max_duration_seconds=30,
                max_audio_bytes=1024,
                consent_version="voice-v1",
            )
            with (
                patch.object(bot, "get_store", return_value=store),
                patch.object(bot, "VOICE_SETTINGS", voice_settings),
            ):
                await bot.voice_message_handler.__wrapped__(update, context)
            self.assertEqual(
                message.reply_text.await_args.args[0],
                "Message vocal refusé : durée ou taille hors limites.",
            )

    async def test_ac3_french_ai_disabled_consent_default_and_error_chrome(self):
        context = SimpleNamespace(user_data={"interface_locale": "fr"}, args=[])

        with self.subTest(surface="disabled"):
            message = SimpleNamespace(reply_text=AsyncMock())
            with patch.object(bot, "AI_SETTINGS", SimpleNamespace(enabled=False)):
                await bot.request_ai_tutor_answer(
                    message,
                    context,
                    "QUESTION-CONTENT",
                    user_id=42,
                    request_kind="command",
                    locale="fr",
                )
            self.assertEqual(
                message.reply_text.await_args.args[0],
                "Le tuteur IA est désactivé pour le moment.",
            )

        enabled_settings = SimpleNamespace(
            enabled=True,
            consent_version="ai-v1",
            processing_notice="NOTICE-CONFIGURÉE-INCHANGÉE",
        )
        with patch.object(bot, "AI_SETTINGS", enabled_settings):
            with self.subTest(surface="consent_cancel"):
                query = SimpleNamespace(
                    data="aiconsent:cancel",
                    answer=AsyncMock(),
                    edit_message_reply_markup=AsyncMock(),
                )
                update = SimpleNamespace(
                    callback_query=query,
                    effective_user=SimpleNamespace(id=42, language_code="fr"),
                )
                context.user_data["pending_ai_consent"] = {
                    "request_kind": "command"
                }
                await bot.ai_consent_cb.__wrapped__(update, context)
                query.answer.assert_awaited_once_with("Demande IA annulée.")

            with self.subTest(surface="safe_error"):
                message = SimpleNamespace(reply_text=AsyncMock())
                service = SimpleNamespace(
                    ask=AsyncMock(side_effect=ValueError("unsafe response"))
                )
                with (
                    patch.object(bot, "active_tutor_context", return_value=object()),
                    patch.object(bot, "get_ai_tutor_service", return_value=service),
                ):
                    await bot.send_ai_tutor_answer(
                        message,
                        context,
                        "QUESTION-CONTENT",
                        user_id=42,
                        locale="fr",
                    )
                self.assertEqual(
                    message.reply_text.await_args.args[0],
                    "Impossible de préparer une réponse sûre. "
                    "Aucun crédit IA n’a été débité.",
                )
                self.assertEqual(service.ask.await_args.kwargs["question"], "QUESTION-CONTENT")

            with self.subTest(surface="free_action_menu"):
                message = SimpleNamespace(reply_text=AsyncMock())
                update = SimpleNamespace(
                    message=message,
                    effective_user=SimpleNamespace(id=42, language_code="fr"),
                )
                context.user_data["block_session"] = "bloc-francais"
                requester = AsyncMock()
                with patch.object(bot, "request_ai_tutor_answer", new=requester):
                    await bot.cmd_ai.__wrapped__(update, context)
                requester.assert_not_awaited()
                payload = message.reply_text.await_args
                self.assertEqual(
                    payload.args[0],
                    translate("ai_tutor_menu_intro", "fr"),
                )
                buttons = [
                    button
                    for row in payload.kwargs["reply_markup"].inline_keyboard
                    for button in row
                ]
                self.assertEqual(
                    [button.text for button in buttons],
                    [
                        "📚 Vocabulaire",
                        "🎯 Erreurs",
                        "📊 Progrès",
                        "💬 Poser une question",
                    ],
                )
                self.assertNotIn("Объясни", payload.args[0])

    async def test_ac5_french_stars_payment_and_subscription_callbacks(self):
        validation = Mock(side_effect=ValueError("invalid invoice"))
        fulfillment = Mock(
            return_value=SimpleNamespace(
                created=True,
                credits=25,
                available_credits=40,
            )
        )
        subscription_update = AsyncMock()
        service = SimpleNamespace(
            validate_pre_checkout=validation,
            fulfill_successful_payment=fulfillment,
            set_subscription_autorenew=subscription_update,
        )

        with (
            patch.object(bot, "get_billing_service", return_value=service),
            patch.object(bot, "record_product_event"),
            patch.object(bot, "TELEGRAM_RUNTIME", SimpleNamespace(is_test=False)),
        ):
            with self.subTest(surface="pre_checkout_error"):
                query = SimpleNamespace(
                    from_user=SimpleNamespace(id=43, language_code="fr"),
                    invoice_payload="payload-test",
                    currency="XTR",
                    total_amount=25,
                    answer=AsyncMock(),
                )
                update = SimpleNamespace(pre_checkout_query=query)
                await bot.pre_checkout_handler(update, SimpleNamespace())
                query.answer.assert_awaited_once_with(
                    ok=False,
                    error_message=(
                        "Impossible de confirmer le prix. "
                        "Créez une nouvelle facture avec /buy."
                    ),
                )

            with self.subTest(surface="successful_payment"):
                payment = SimpleNamespace(
                    invoice_payload="payload-test",
                    currency="XTR",
                    total_amount=25,
                    telegram_payment_charge_id="telegram-charge-test",
                    provider_payment_charge_id="provider-charge-test",
                    is_recurring=False,
                    is_first_recurring=False,
                    subscription_expiration_date=None,
                )
                message = SimpleNamespace(
                    successful_payment=payment,
                    reply_text=AsyncMock(),
                )
                update = SimpleNamespace(
                    message=message,
                    effective_user=SimpleNamespace(id=43, language_code="fr"),
                )
                context = SimpleNamespace(user_data={"interface_locale": "fr"})
                await bot.successful_payment_handler(update, context)
                self.assertEqual(
                    message.reply_text.await_args.args[0],
                    "Paiement confirmé. 25 crédits IA ajoutés.\nDisponibles : 40.",
                )

            with self.subTest(surface="subscription_callback"):
                query = SimpleNamespace(
                    data="sub:cancel:subscription-test",
                    answer=AsyncMock(),
                    message=SimpleNamespace(reply_text=AsyncMock()),
                )
                update = SimpleNamespace(
                    callback_query=query,
                    effective_user=SimpleNamespace(id=43, language_code="fr"),
                )
                context = SimpleNamespace(
                    user_data={"interface_locale": "fr"},
                    bot=SimpleNamespace(),
                )
                with patch.object(
                    bot,
                    "TelegramStarsGateway",
                    return_value="mock-gateway",
                ):
                    await bot.subscription_cb.__wrapped__(update, context)
                query.answer.assert_awaited_once_with(
                    "Paramètre d’abonnement mis à jour."
                )
                query.message.reply_text.assert_awaited_once_with(
                    "Le renouvellement automatique est désactivé jusqu’à la "
                    "fin de la période payée."
                )
                self.assertEqual(
                    subscription_update.await_args.kwargs["subscription_id"],
                    "subscription-test",
                )

    async def test_ac1_ac2_ac6_ec1_french_callbacks_and_auth_runtime_locale(self):
        context = SimpleNamespace(
            user_data={"interface_locale": "fr"},
            bot=SimpleNamespace(send_message=AsyncMock()),
        )

        with self.subTest(surface="help_callback"):
            query = SimpleNamespace(
                data="start:about",
                message=SimpleNamespace(chat_id=404),
                answer=AsyncMock(),
            )
            update = SimpleNamespace(
                callback_query=query,
                effective_user=SimpleNamespace(id=44, language_code="fr"),
            )
            await bot.start_menu_cb.__wrapped__(update, context)
            payload = context.bot.send_message.await_args
            self.assertIn("Comment se déroule l’apprentissage", payload.kwargs["text"])
            button = payload.kwargs["reply_markup"].inline_keyboard[0][0]
            self.assertEqual(button.text, "▶️ Commencer la leçon")
            self.assertNotIn("Как проходит обучение", payload.kwargs["text"])

        with self.subTest(surface="stale_settings_callback"):
            query = SimpleNamespace(
                data="settings:stale",
                answer=AsyncMock(),
            )
            update = SimpleNamespace(
                callback_query=query,
                effective_user=SimpleNamespace(id=44, language_code="fr"),
            )
            await bot.settings_cb.__wrapped__(update, context)
            query.answer.assert_awaited_once_with(
                "Ce réglage a expiré.",
                show_alert=True,
            )

        with self.subTest(surface="language_switch"):
            query = SimpleNamespace(
                data=f"lang:{self.pack.pack_id}",
                message=SimpleNamespace(chat_id=404),
                answer=AsyncMock(),
                edit_message_text=AsyncMock(),
            )
            update = SimpleNamespace(
                callback_query=query,
                effective_user=SimpleNamespace(id=44, language_code="fr"),
            )
            with (
                patch.object(bot, "switchable_packs", return_value=[self.pack]),
                patch.object(bot, "activate_content_pack"),
                patch.object(bot, "record_product_event"),
            ):
                await bot.lang_switch_cb.__wrapped__(update, context)
            text = query.edit_message_text.await_args.args[0]
            self.assertEqual(
                text,
                f"Pack *{self.pack.label}* activé ({self.pack.entry_count} mots)",
            )
            self.assertNotIn(self.pack.title, text)

        observed_locales = []

        @bot.auth
        async def locale_probe(update, context):
            observed_locales.append(bot.interface_locale_for_update(update))

        store = SimpleNamespace(
            access_profile=lambda _user_id: {
                "role": "learner",
                "access_status": "active",
            },
            activate_user_access=Mock(),
        )
        runtime = SimpleNamespace(
            access_status="active",
            role="learner",
            onboarding_completed=True,
            store=store,
            user_id=44,
        )
        with (
            patch.object(bot, "get_store", return_value=store),
            patch.object(bot, "ALLOWED_USER_IDS", {44}),
            patch.object(bot, "learner_scope", side_effect=lambda _user: nullcontext(runtime)),
            patch.object(bot, "SAFETY_SETTINGS", SimpleNamespace(enabled=False)),
        ):
            for language_code, expected in (
                (None, "en"),
                ("", "en"),
                ("pt-BR", "en"),
                ("ru", "ru"),
            ):
                with self.subTest(runtime_language_code=language_code):
                    update = SimpleNamespace(
                        effective_user=SimpleNamespace(
                            id=44,
                            language_code=language_code,
                        )
                    )
                    runtime_context = SimpleNamespace(user_data={})
                    await locale_probe(update, runtime_context)
                    self.assertEqual(observed_locales[-1], expected)
                    self.assertEqual(
                        runtime_context.user_data.get("interface_locale"),
                        expected,
                    )

    async def test_ac7_real_store_notification_reads_persisted_french_locale(self):
        recipient_id = 7654321
        with tempfile.TemporaryDirectory(
            prefix="mydictionary-locale-notification-"
        ) as directory:
            store = DatabaseStore(f"sqlite:///{Path(directory) / 'test.db'}")
            try:
                store.ensure_user(
                    SimpleNamespace(
                        id=recipient_id,
                        username=None,
                        first_name=None,
                        last_name=None,
                        language_code="fr",
                    )
                )
                AdminStore(store).set_user_access_status(
                    recipient_id,
                    status="active",
                    actor="test",
                )

                with self.subTest(surface="access_profile"):
                    profile = store.access_profile(recipient_id)
                    self.assertEqual(profile.get("language_code"), "fr")

                telegram_bot = SimpleNamespace(send_message=AsyncMock())
                with (
                    patch.object(bot.logger, "info") as info_log,
                    patch.object(bot.logger, "warning") as warning_log,
                ):
                    delivered = await bot.deliver_telegram_notifications(
                        telegram_bot,
                        store,
                    )

                self.assertEqual(delivered, 1)
                text = telegram_bot.send_message.await_args.kwargs["text"]
                self.assertIn(
                    "Votre accès au pilote gratuit MY DICTIONARY est ouvert.",
                    text,
                )
                self.assertNotIn(str(recipient_id), text)
                log_payload = " ".join(
                    repr(call)
                    for call in (
                        *info_log.call_args_list,
                        *warning_log.call_args_list,
                    )
                )
                self.assertNotIn(str(recipient_id), log_payload)
            finally:
                store.close()

    def test_ec2_cycle4_chrome_is_not_silently_english_for_supported_locales(self):
        representative_messages = {
            "start_about_text": {},
            "settings_stale": {},
            "voice_stop_active": {},
            "ai_disabled": {},
            "billing_payment_success": {
                "credits": 17,
                "available": 23,
            },
            "legacy_pack_activated": {
                "pack": "PACK-SENTINEL",
                "count": 41,
            },
        }
        english = {
            key: translate(key, "en", **placeholders)
            for key, placeholders in representative_messages.items()
        }
        localized = {}

        for locale in ("de", "ja", "ar", "zh", "es", "ru", "fr"):
            localized[locale] = {}
            for key, placeholders in representative_messages.items():
                with self.subTest(locale=locale, key=key):
                    rendered = translate(key, locale, **placeholders)
                    localized[locale][key] = rendered
                    self.assertTrue(rendered.strip())
                    self.assertNotRegex(rendered, r"\{[^{}]+\}")
                    for value in placeholders.values():
                        self.assertIn(str(value), rendered)
                    self.assertNotEqual(rendered, english[key])

        locale_markers = {
            "de": r"\b(?:Einstellung|Sprachsitzung|Zahlung)\b",
            "ja": r"[\u3040-\u30ff\u4e00-\u9fff]",
            "ar": r"[\u0600-\u06ff]",
            "zh": r"[\u4e00-\u9fff]",
            "es": r"\b(?:Ajuste|Sesión|Pago)\b",
            "ru": r"[А-Яа-яЁё]",
            "fr": r"\b(?:Réglage|Session|Paiement)\b",
        }
        for locale, marker in locale_markers.items():
            with self.subTest(locale=locale, expected_language_marker=marker):
                self.assertRegex("\n".join(localized[locale].values()), marker)


class BillingProductLocalizationContractTest(unittest.IsolatedAsyncioTestCase):
    PRODUCTS = (
        {
            "product_id": "ai-mini",
            "title": "Мини",
            "description": "20 AI-кредитов для знакомства с репетитором",
            "credits": 20,
            "price_xtr": 69,
        },
        {
            "product_id": "ai-starter",
            "title": "Старт",
            "description": "50 AI-кредитов для запросов к репетитору",
            "credits": 50,
            "price_xtr": 129,
        },
        {
            "product_id": "ai-value",
            "title": "Выгодно",
            "description": "150 AI-кредитов для регулярной практики",
            "credits": 150,
            "price_xtr": 319,
        },
        {
            "product_id": "ai-monthly",
            "title": "Месяц",
            "description": "100 AI-кредитов каждые 30 дней",
            "credits": 100,
            "price_xtr": 229,
        },
    )
    COPY_MARKERS = {
        "en": {
            "ai-mini": ("Mini", "try the tutor", "AI credits"),
            "ai-starter": ("Starter", "tutor requests", "AI credits"),
            "ai-value": ("Value", "regular practice", "AI credits"),
            "ai-monthly": ("Monthly", "every 30 days", "AI credits"),
        },
        "fr": {
            "ai-mini": ("Mini", "découvrir le tuteur", "crédits IA"),
            "ai-starter": ("Découverte", "demandes au tuteur", "crédits IA"),
            "ai-value": ("Avantage", "pratique régulière", "crédits IA"),
            "ai-monthly": ("Mensuel", "tous les 30 jours", "crédits IA"),
        },
        "de": {
            "ai-mini": ("Mini", "Tutor kennenzulernen", "KI-Credits"),
            "ai-starter": ("Einstieg", "Anfragen an den Tutor", "KI-Credits"),
            "ai-value": ("Vorteil", "regelmäßiges Üben", "KI-Credits"),
            "ai-monthly": ("Monatlich", "alle 30 Tage", "KI-Credits"),
        },
        "es": {
            "ai-mini": ("Mini", "probar el tutor", "créditos de IA"),
            "ai-starter": ("Inicio", "consultas al tutor", "créditos de IA"),
            "ai-value": ("Ahorro", "práctica habitual", "créditos de IA"),
            "ai-monthly": ("Mensual", "cada 30 días", "créditos de IA"),
        },
        "ja": {
            "ai-mini": ("ミニ", "チューターを試す", "AIクレジット"),
            "ai-starter": ("スターター", "チューターへの質問", "AIクレジット"),
            "ai-value": ("お得", "定期的な練習", "AIクレジット"),
            "ai-monthly": ("月額", "30日ごと", "AIクレジット"),
        },
        "zh": {
            "ai-mini": ("迷你", "体验导师", "AI 点数"),
            "ai-starter": ("入门", "向导师提问", "AI 点数"),
            "ai-value": ("超值", "定期练习", "AI 点数"),
            "ai-monthly": ("每月", "每 30 天", "AI 点数"),
        },
        "ar": {
            "ai-mini": ("مصغّرة", "لتجربة المدرّس", "رصيد AI"),
            "ai-starter": ("بداية", "لطلبات المدرّس", "رصيد AI"),
            "ai-value": ("موفّرة", "للتدريب المنتظم", "رصيد AI"),
            "ai-monthly": ("شهرية", "كل 30 يومًا", "رصيد AI"),
        },
        "ru": {
            product["product_id"]: (
                product["title"],
                product["description"],
                "AI-кредитов",
            )
            for product in PRODUCTS
        },
    }

    async def _catalog_payload(self, products, *, locale):
        service = SimpleNamespace(active_products=lambda: products)
        message = SimpleNamespace(chat_id=7001, reply_text=AsyncMock())
        with (
            patch.object(bot, "get_billing_service", return_value=service),
            patch.object(
                bot,
                "STARS_PRODUCTION_CANARY_SETTINGS",
                SimpleNamespace(enabled=False),
            ),
            patch.object(bot, "TELEGRAM_RUNTIME", SimpleNamespace(is_test=False)),
        ):
            await bot.send_billing_products(message, locale=locale)
        return message.reply_text.await_args

    async def _invoice_payload(self, product, *, locale, amount_xtr=None):
        service = Mock()
        service.create_order.return_value = SimpleNamespace(
            order_id="order-localized",
            product_id=product["product_id"],
            title=product["title"],
            description=product["description"],
            credits=product["credits"],
            amount_xtr=(
                product["price_xtr"] if amount_xtr is None else amount_xtr
            ),
            payload="md1.localized.payload",
            subscription_period_seconds=None,
        )
        store = Mock()
        store.has_consent.return_value = True
        query = SimpleNamespace(
            data=f"buy:{product['product_id']}",
            answer=AsyncMock(),
            message=SimpleNamespace(chat_id=7001, reply_text=AsyncMock()),
        )
        update = SimpleNamespace(
            callback_query=query,
            effective_user=SimpleNamespace(id=7001, language_code=locale),
        )
        context = SimpleNamespace(
            user_data={"interface_locale": locale},
            bot=SimpleNamespace(send_invoice=AsyncMock()),
        )
        with (
            patch.object(bot, "get_billing_service", return_value=service),
            patch.object(bot, "get_store", return_value=store),
            patch.object(
                bot,
                "BILLING_SETTINGS",
                SimpleNamespace(enabled=True, terms_version="terms-v1"),
            ),
            patch.object(
                bot,
                "STARS_PRODUCTION_CANARY_SETTINGS",
                SimpleNamespace(enabled=False),
            ),
            patch.object(bot, "TELEGRAM_RUNTIME", SimpleNamespace(is_test=False)),
            patch.object(bot, "record_product_event") as event,
        ):
            await bot.buy_product_cb.__wrapped__(update, context)
        return service, context.bot.send_invoice.await_args, event

    async def test_french_ai_mini_catalog_and_invoice_localize_canonical_russian_copy(self):
        product = self.PRODUCTS[0]

        catalog = await self._catalog_payload([product], locale="fr")
        button = catalog.kwargs["reply_markup"].inline_keyboard[0][0]
        self.assertEqual(button.text, "Mini · 69 ⭐")
        self.assertEqual(button.callback_data, "buy:ai-mini")

        service, invoice_call, event = await self._invoice_payload(
            product,
            locale="fr",
            amount_xtr=10,
        )
        invoice = invoice_call.kwargs
        self.assertEqual(invoice["title"], "Mini")
        self.assertIn("20 crédits IA", invoice["description"])
        self.assertIn("découvrir le tuteur", invoice["description"])
        self.assertNotRegex(
            f"{button.text}\n{invoice['title']}\n{invoice['description']}",
            r"[А-Яа-яЁё]",
        )
        self.assertEqual(invoice["payload"], "md1.localized.payload")
        self.assertEqual(invoice["prices"][0].amount, 10)
        self.assertEqual(invoice["prices"][0].label, "20 crédits IA")
        service.create_order.assert_called_once_with(
            user_id=7001,
            product_id="ai-mini",
        )
        self.assertEqual(
            [call.args[0] for call in event.call_args_list],
            ["billing_package_selected", "billing_invoice_created"],
        )

    async def test_all_known_products_localize_for_all_interface_locales(self):
        self.assertEqual(set(self.COPY_MARKERS), set(INTERFACE_LOCALES))
        known_ids = {product["product_id"] for product in self.PRODUCTS}
        for locale in sorted(INTERFACE_LOCALES):
            self.assertEqual(set(self.COPY_MARKERS[locale]), known_ids)
            catalog = await self._catalog_payload(self.PRODUCTS, locale=locale)
            buttons = catalog.kwargs["reply_markup"].inline_keyboard
            self.assertEqual(len(buttons), len(self.PRODUCTS))
            for row, product in zip(buttons, self.PRODUCTS, strict=True):
                title_marker, purpose_marker, credit_marker = self.COPY_MARKERS[
                    locale
                ][product["product_id"]]
                with self.subTest(
                    locale=locale,
                    product_id=product["product_id"],
                    surface="catalog",
                ):
                    button = row[0]
                    self.assertIn(title_marker, button.text)
                    self.assertIn(f"· {product['price_xtr']} ⭐", button.text)
                    self.assertEqual(
                        button.callback_data,
                        f"buy:{product['product_id']}",
                    )

                service, invoice_call, _event = await self._invoice_payload(
                    product,
                    locale=locale,
                )
                invoice = invoice_call.kwargs
                with self.subTest(
                    locale=locale,
                    product_id=product["product_id"],
                    surface="invoice",
                ):
                    self.assertIn(title_marker, invoice["title"])
                    self.assertIn(str(product["credits"]), invoice["description"])
                    self.assertIn(credit_marker, invoice["description"])
                    self.assertIn(purpose_marker, invoice["description"])
                    self.assertLessEqual(len(invoice["title"]), 32)
                    self.assertLessEqual(len(invoice["description"]), 255)
                    self.assertEqual(invoice["payload"], "md1.localized.payload")
                    self.assertEqual(
                        invoice["prices"][0].amount,
                        product["price_xtr"],
                    )
                    service.create_order.assert_called_once_with(
                        user_id=7001,
                        product_id=product["product_id"],
                    )
                    rendered = f"{invoice['title']}\n{invoice['description']}"
                    if locale == "ru":
                        self.assertEqual(invoice["title"], product["title"])
                        self.assertEqual(
                            invoice["description"],
                            product["description"],
                        )
                    else:
                        self.assertNotRegex(rendered, r"[А-Яа-яЁё]")

    async def test_unknown_product_id_keeps_canonical_catalog_and_invoice_copy(self):
        product = {
            "product_id": "custom-research-pack",
            "title": "Research Pack Original",
            "description": "Custom database description — keep verbatim",
            "credits": 77,
            "price_xtr": 88,
        }

        catalog = await self._catalog_payload([product], locale="fr")
        button = catalog.kwargs["reply_markup"].inline_keyboard[0][0]
        self.assertEqual(button.text, "Research Pack Original · 88 ⭐")
        self.assertEqual(button.callback_data, "buy:custom-research-pack")

        service, invoice_call, _event = await self._invoice_payload(
            product,
            locale="fr",
        )
        invoice = invoice_call.kwargs
        self.assertEqual(invoice["title"], product["title"])
        self.assertEqual(invoice["description"], product["description"])
        self.assertEqual(invoice["payload"], "md1.localized.payload")
        self.assertEqual(invoice["prices"][0].amount, product["price_xtr"])
        service.create_order.assert_called_once_with(
            user_id=7001,
            product_id=product["product_id"],
        )


if __name__ == "__main__":
    unittest.main()
