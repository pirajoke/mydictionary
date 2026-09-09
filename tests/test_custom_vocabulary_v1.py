from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from sqlalchemy import func, inspect, select, text

import bot
from mydictionary import localization
from mydictionary import miniapp
from mydictionary.ai_tutor import OpenAIResponsesProvider
from mydictionary.custom_vocabulary import (
    CustomVocabularyCandidate,
    build_multimodal_input,
    parse_pasted_vocabulary,
    spoken_vocabulary_payload,
    validate_extracted_vocabulary,
)
from mydictionary.privacy import erase_user_learning_data
from mydictionary.storage import CustomVocabularyEntry, DatabaseStore, User


ROOT = Path(__file__).resolve().parents[1]
HTML = (ROOT / "mydictionary/templates/miniapp.html").read_text(encoding="utf-8")
CSS = (ROOT / "mydictionary/static/miniapp.css").read_text(encoding="utf-8")
JS = (ROOT / "mydictionary/static/miniapp.js").read_text(encoding="utf-8")
MINIAPP = (ROOT / "mydictionary/miniapp.py").read_text(encoding="utf-8")
BOT = (ROOT / "bot.py").read_text(encoding="utf-8")


class CustomVocabularyParsingTest(unittest.TestCase):
    def test_paste_accepts_common_separators_and_deduplicates(self):
        entries = parse_pasted_vocabulary(
            "1. hola — привет\n2) Casa: дом\n• viaje; поездка\nHOLA - здравствуй\n"
        )

        self.assertEqual(
            [(entry.target, entry.meaning) for entry in entries],
            [("hola", "привет"), ("Casa", "дом"), ("viaje", "поездка")],
        )
        self.assertTrue(all(entry.source_kind == "text" for entry in entries))

    def test_target_only_paste_is_preserved_for_enrichment(self):
        entries = parse_pasted_vocabulary("aeropuerto\nla estación")
        self.assertEqual([entry.meaning for entry in entries], ["", ""])

    def test_paste_rejects_empty_and_more_than_40_entries(self):
        with self.assertRaises(ValueError):
            parse_pasted_vocabulary(" \n")
        with self.assertRaises(ValueError):
            parse_pasted_vocabulary("\n".join(f"word-{index}" for index in range(41)))

    def test_provider_output_is_exact_bounded_and_deduplicated(self):
        parsed = validate_extracted_vocabulary(
            {
                "entries": [
                    {"target": "hola", "meaning": "привет", "transcription": "/ˈola/"},
                    {"target": " HOLA ", "meaning": "здравствуй", "transcription": "/ˈola/"},
                ]
            },
            source_kind="photo",
        )
        self.assertEqual(len(parsed), 1)
        self.assertEqual(parsed[0].source_kind, "photo")
        with self.assertRaises(ValueError):
            validate_extracted_vocabulary({"entries": [{"target": "x"}]}, source_kind="pdf")

    def test_multimodal_inputs_are_data_urls_and_do_not_use_hosted_storage(self):
        image = build_multimodal_input(
            source_kind="photo",
            content=b"jpeg",
            mime_type="image/jpeg",
            filename="photo.jpg",
            target_language="es",
            meaning_language="ru",
        )
        pdf = build_multimodal_input(
            source_kind="pdf",
            content=b"%PDF",
            mime_type="application/pdf",
            filename="words.pdf",
            target_language="es",
            meaning_language="ru",
        )
        self.assertEqual(image[0]["type"], "input_text")
        self.assertEqual(image[1]["type"], "input_image")
        self.assertTrue(image[1]["image_url"].startswith("data:image/jpeg;base64,"))
        self.assertEqual(pdf[1]["type"], "input_file")
        self.assertTrue(pdf[1]["file_data"].startswith("data:application/pdf;base64,"))
        self.assertEqual(pdf[1]["detail"], "low")
        self.assertNotIn("file_id", repr(image + pdf))

    def test_voice_transcript_is_preserved_for_spoken_list_extraction(self):
        payload = spoken_vocabulary_payload(
            "hola привет, casa дом, viaje",
            target_language="es",
            meaning_language="ru",
        )
        instruction = json.loads(payload[0]["text"])
        self.assertEqual(instruction["transcript"], "hola привет, casa дом, viaje")
        self.assertIn("Separate distinct spoken words", instruction["task"])


class CustomVocabularyStorageTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="custom-words-")
        self.store = DatabaseStore(f"sqlite:///{self.temp.name}/test.sqlite3")
        self.user_id = 90101
        self.store.ensure_user_id(self.user_id)
        with self.store.Session.begin() as session:
            learner = session.get(User, self.user_id)
            learner.access_status = "active"
            learner.privacy_status = "active"

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    def test_upsert_is_user_language_scoped_sorted_and_deduplicated(self):
        initial = self.store.upsert_custom_vocabulary(
            self.user_id,
            target_language="es",
            meaning_language="ru",
            entries=(
                CustomVocabularyCandidate("viaje", "поездка", "/ˈbjaxe/", "text"),
                CustomVocabularyCandidate("Casa", "дом", "/ˈkasa/", "text"),
            ),
        )
        result = self.store.upsert_custom_vocabulary(
            self.user_id,
            target_language="es",
            meaning_language="ru",
            entries=(
                CustomVocabularyCandidate(" CASA ", "жилище", "/ˈkasa/", "text"),
            ),
        )
        words = self.store.list_custom_vocabulary(
            self.user_id, target_language="es", meaning_language="ru"
        )

        self.assertEqual(initial, {"inserted": 2, "updated": 0, "total": 2})
        self.assertEqual(result, {"inserted": 0, "updated": 1, "total": 2})
        self.assertEqual([word["target"] for word in words], ["Casa", "viaje"])
        self.assertEqual(words[0]["meaning"], "жилище")
        self.assertEqual(
            self.store.list_custom_vocabulary(
                self.user_id, target_language="fr", meaning_language="ru"
            ),
            [],
        )

    def test_custom_practice_due_first_and_rating_updates_srs(self):
        self.store.upsert_custom_vocabulary(
            self.user_id,
            target_language="es",
            meaning_language="ru",
            entries=(
                CustomVocabularyCandidate("nuevo", "новый", "/ˈnweβo/", "text"),
                CustomVocabularyCandidate("viejo", "старый", "/ˈbjexo/", "text"),
            ),
        )
        words = self.store.list_custom_vocabulary(
            self.user_id, target_language="es", meaning_language="ru"
        )
        old_id = next(word["entry_id"] for word in words if word["target"] == "viejo")
        with self.store.Session.begin() as session:
            old = session.get(CustomVocabularyEntry, old_id)
            old.correct_count = 2
            old.next_review = "2020-01-01T00:00:00+00:00"
        practice = self.store.custom_vocabulary_practice(
            self.user_id,
            target_language="es",
            meaning_language="ru",
            limit=2,
            now=datetime(2026, 9, 9, tzinfo=timezone.utc),
        )
        self.assertEqual(practice[0]["target"], "viejo")

        rated = self.store.rate_custom_vocabulary(
            self.user_id,
            entry_id=old_id,
            knew=True,
            now=datetime(2026, 9, 9, tzinfo=timezone.utc),
        )
        self.assertEqual(rated["correct_count"], 3)
        self.assertEqual(rated["interval"], 4)
        self.assertFalse(rated["due"])

    def test_privacy_erasure_removes_custom_words(self):
        self.store.upsert_custom_vocabulary(
            self.user_id,
            target_language="es",
            meaning_language="ru",
            entries=(CustomVocabularyCandidate("hola", "привет", "/ˈola/", "text"),),
        )
        erase_user_learning_data(self.store, self.user_id)
        with self.store.Session() as session:
            count = session.scalar(select(func.count()).select_from(CustomVocabularyEntry))
        self.assertEqual(count, 0)

    def test_translation_language_preference_is_durable_and_separate(self):
        self.store.update_product_profile(self.user_id, native_language="fr")

        columns = {
            column["name"]
            for column in inspect(self.store.engine).get_columns("users")
        }
        self.assertIn("custom_vocabulary_meaning_language", columns)
        self.assertEqual(
            self.store.set_custom_vocabulary_meaning_language(self.user_id, "ru"),
            "ru",
        )

        profile = self.store.product_profile(self.user_id)
        self.assertEqual(profile["custom_vocabulary_meaning_language"], "ru")
        self.assertEqual(profile["native_language"], "fr")
        self.assertEqual(profile["active_lang"], "en")

        erase_user_learning_data(self.store, self.user_id)
        with self.store.engine.connect() as connection:
            preference = connection.execute(
                text(
                    "SELECT custom_vocabulary_meaning_language FROM users "
                    "WHERE telegram_user_id = :user_id"
                ),
                {"user_id": self.user_id},
            ).scalar_one()
        self.assertIsNone(preference)

    def test_miniapp_custom_word_list_uses_durable_translation_language(self):
        self.store.update_product_profile(self.user_id, native_language="fr")
        self.store.set_custom_vocabulary_meaning_language(self.user_id, "ru")
        self.store.upsert_custom_vocabulary(
            self.user_id,
            target_language="en",
            meaning_language="ru",
            entries=(
                CustomVocabularyCandidate(
                    "journey", "поездка", "/ˈdʒɜːni/", "text"
                ),
            ),
        )
        self.store.upsert_custom_vocabulary(
            self.user_id,
            target_language="en",
            meaning_language="fr",
            entries=(
                CustomVocabularyCandidate(
                    "journey", "voyage", "/ˈdʒɜːni/", "text"
                ),
            ),
        )

        payload = miniapp.build_bootstrap(
            self.store,
            user_id=self.user_id,
            display_name="Learner",
            locale="ru",
            catalog=bot.CATALOG,
            products=[],
            checkout_enabled=False,
            ai_enabled=True,
            voice_enabled=True,
        )

        self.assertEqual(len(payload["custom_words"]), 1)
        self.assertEqual(payload["custom_words"][0]["meaning"], "поездка")

    def test_miniapp_bootstrap_exposes_only_bounded_custom_word_fields(self):
        self.store.upsert_custom_vocabulary(
            self.user_id,
            target_language="en",
            meaning_language="ru",
            entries=(
                CustomVocabularyCandidate(
                    "journey", "поездка", "/ˈdʒɜːni/", "text"
                ),
            ),
        )

        payload = miniapp.build_bootstrap(
            self.store,
            user_id=self.user_id,
            display_name="Learner",
            locale="ru",
            catalog=bot.CATALOG,
            products=[],
            checkout_enabled=False,
            ai_enabled=True,
            voice_enabled=True,
        )

        self.assertEqual(len(payload["custom_words"]), 1)
        self.assertEqual(
            set(payload["custom_words"][0]),
            {"target", "meaning", "transcription", "learned", "due"},
        )
        self.assertEqual(payload["custom_words"][0]["target"], "journey")


class CustomVocabularySurfaceContractTest(unittest.TestCase):
    def test_miniapp_has_two_primary_custom_word_actions_and_rendering(self):
        self.assertIn('id="custom-vocabulary-actions"', HTML)
        self.assertIn('data-action="add_words"', HTML)
        self.assertIn('data-action="practice_custom"', HTML)
        self.assertIn('id="custom-word-list"', HTML)
        self.assertIn('customWords.forEach((word) => addCustomWord', JS)
        self.assertIn('"add_words": "miniapp_add_words"', MINIAPP)
        self.assertIn('"practice_custom": "miniapp_practice_custom"', MINIAPP)
        self.assertIn(".custom-vocabulary-actions", CSS)

    def test_bot_deep_links_routes_and_handlers_are_registered(self):
        self.assertIn('"add_words": cmd_add_words', BOT)
        self.assertIn('"practice_custom": cmd_custom_practice', BOT)
        self.assertIn('CallbackQueryHandler(custom_import_cb', BOT)
        self.assertIn('CallbackQueryHandler(custom_practice_cb', BOT)
        self.assertIn('MessageHandler(filters.PHOTO, custom_vocabulary_media_handler)', BOT)
        self.assertIn('filters.Document.PDF', BOT)
        self.assertIn('PENDING_CUSTOM_VOCABULARY_KEY', BOT)

    def test_custom_vocabulary_flow_is_localized_for_every_supported_locale(self):
        keys = {
            key
            for key in localization._CATALOG["en"]
            if key.startswith("custom_vocab_")
        }
        self.assertGreaterEqual(len(keys), 20)
        for locale in localization.INTERFACE_LOCALES:
            with self.subTest(locale=locale):
                self.assertTrue(keys.issubset(localization._CATALOG[locale]))
                self.assertTrue(
                    all(str(localization._CATALOG[locale][key]).strip() for key in keys)
                )


class _CustomVocabularyResponses:
    def __init__(self):
        self.kwargs = None

    async def create(self, **kwargs):
        self.kwargs = kwargs
        return SimpleNamespace(
            id="resp-custom",
            model="gpt-test",
            service_tier="default",
            status="completed",
            output_text=json.dumps(
                {
                    "entries": [
                        {
                            "target": "viaje",
                            "meaning": "поездка",
                            "transcription": "/ˈbjaxe/",
                        }
                    ]
                },
                ensure_ascii=False,
            ),
            usage=SimpleNamespace(
                input_tokens=12,
                input_tokens_details=SimpleNamespace(
                    cached_tokens=0, cache_write_tokens=0
                ),
                output_tokens=8,
                output_tokens_details=SimpleNamespace(reasoning_tokens=0),
                total_tokens=20,
            ),
        )


class CustomVocabularyProviderTest(unittest.IsolatedAsyncioTestCase):
    async def test_provider_uses_private_strict_structured_multimodal_request(self):
        responses = _CustomVocabularyResponses()
        provider = OpenAIResponsesProvider(
            api_key="test-key",
            model="gpt-test",
            service_tier="default",
            safety_salt="test-safety-salt-long",
            client=SimpleNamespace(responses=responses),
        )
        content = [{"type": "input_text", "text": "supplied words"}]

        result = await provider.generate_custom_vocabulary(
            request_id="request-custom",
            user_id=42,
            input_content=content,
        )

        self.assertEqual(result.output_text, _CustomVocabularyResponsesPayload)
        request = responses.kwargs
        self.assertFalse(request["store"])
        self.assertEqual(request["metadata"], {"request_id": "request-custom"})
        self.assertEqual(request["text"]["format"]["type"], "json_schema")
        self.assertTrue(request["text"]["format"]["strict"])
        self.assertEqual(request["input"][0]["content"], content)
        self.assertNotEqual(request["safety_identifier"], "42")

    async def test_miniapp_actions_route_to_custom_word_handlers(self):
        add_call = AsyncMock()
        practice_call = AsyncMock()
        update = SimpleNamespace(effective_message=SimpleNamespace(reply_text=AsyncMock()))
        context = SimpleNamespace(args=[], user_data={})
        runtime = SimpleNamespace(role="learner", user_id=42, store=object())
        token = bot._ACTIVE_RUNTIME.set(runtime)
        try:
            with (
                patch.object(bot, "cmd_add_words", SimpleNamespace(__wrapped__=add_call)),
                patch.object(
                    bot,
                    "cmd_custom_practice",
                    SimpleNamespace(__wrapped__=practice_call),
                ),
                patch.object(bot, "SAFETY_SETTINGS", SimpleNamespace(enabled=False)),
            ):
                await bot.route_miniapp_start_action("add_words", update, context)
                await bot.route_miniapp_start_action("practice_custom", update, context)
        finally:
            bot._ACTIVE_RUNTIME.reset(token)

        add_call.assert_awaited_once_with(update, context)
        practice_call.assert_awaited_once_with(update, context)

    async def test_add_words_first_asks_for_translation_language(self):
        runtime_store = SimpleNamespace(
            product_profile=lambda _user_id: {
                "active_lang": "fr",
                "native_language": "en",
                "custom_vocabulary_meaning_language": "ru",
            }
        )
        message = SimpleNamespace(reply_text=AsyncMock())
        update = SimpleNamespace(effective_message=message)
        context = SimpleNamespace(user_data={"interface_locale": "ru"})
        runtime = SimpleNamespace(role="learner", user_id=42, store=runtime_store)
        token = bot._ACTIVE_RUNTIME.set(runtime)
        try:
            with patch.object(bot, "record_product_event"):
                await bot.cmd_add_words.__wrapped__(update, context)
        finally:
            bot._ACTIVE_RUNTIME.reset(token)

        state = context.user_data[bot.PENDING_CUSTOM_VOCABULARY_KEY]
        self.assertEqual(state["target_language"], "fr")
        self.assertNotIn("meaning_language", state)
        callbacks = {
            button.callback_data
            for row in message.reply_text.await_args.kwargs[
                "reply_markup"
            ].inline_keyboard
            for button in row
        }
        expected = {
            f"custom-import:language:{language}"
            for language in localization.INTERFACE_LOCALES
            if language != "fr"
        }
        self.assertTrue(expected.issubset(callbacks))
        self.assertNotIn("custom-import:language:fr", callbacks)

        labels = {
            button.text
            for row in message.reply_text.await_args.kwargs[
                "reply_markup"
            ].inline_keyboard
            for button in row
        }
        self.assertIn(
            f"{bot.CATALOG.flag_for_language('ru', 'learner')} "
            f"{localization.language_name('ru', 'ru')}",
            labels,
        )

    async def test_translation_language_selection_is_persisted_without_changing_profile(self):
        store = SimpleNamespace(
            product_profile=MagicMock(
                return_value={
                    "active_lang": "fr",
                    "native_language": "en",
                    "custom_vocabulary_meaning_language": None,
                }
            ),
            set_custom_vocabulary_meaning_language=MagicMock(return_value="ru"),
            update_product_profile=MagicMock(),
        )
        context = SimpleNamespace(
            user_data={
                "interface_locale": "ru",
                bot.PENDING_CUSTOM_VOCABULARY_KEY: {
                    "target_language": "fr",
                    "expires_at": 4_000_000_000,
                },
            }
        )
        query = SimpleNamespace(
            data="custom-import:language:ru",
            answer=AsyncMock(),
            edit_message_reply_markup=AsyncMock(),
            edit_message_text=AsyncMock(),
            message=SimpleNamespace(reply_text=AsyncMock()),
        )
        update = SimpleNamespace(
            callback_query=query,
            effective_user=SimpleNamespace(id=42),
        )

        with patch.object(bot, "get_store", return_value=store):
            await bot.custom_import_cb.__wrapped__(update, context)

        store.set_custom_vocabulary_meaning_language.assert_called_once_with(42, "ru")
        store.update_product_profile.assert_not_called()
        state = context.user_data[bot.PENDING_CUSTOM_VOCABULARY_KEY]
        self.assertEqual(state["target_language"], "fr")
        self.assertEqual(state["meaning_language"], "ru")

    async def test_custom_vocabulary_input_is_rejected_until_language_is_chosen(self):
        context = SimpleNamespace(
            user_data={
                "interface_locale": "ru",
                bot.PENDING_CUSTOM_VOCABULARY_KEY: {
                    "target_language": "fr",
                    "expires_at": 4_000_000_000,
                },
            }
        )
        message = SimpleNamespace(
            text="bonjour — привет",
            reply_text=AsyncMock(),
        )
        update = SimpleNamespace(
            message=message,
            effective_user=SimpleNamespace(id=42),
        )

        await bot._handle_custom_vocabulary_text(update, context)

        state = context.user_data[bot.PENDING_CUSTOM_VOCABULARY_KEY]
        self.assertNotIn("pending_source", state)
        self.assertNotIn(bot.CUSTOM_VOCABULARY_PREVIEW_KEY, context.user_data)
        message.reply_text.assert_awaited_once()

    async def test_custom_practice_uses_durable_translation_language(self):
        store = SimpleNamespace(
            product_profile=lambda _user_id: {
                "active_lang": "fr",
                "native_language": "en",
                "custom_vocabulary_meaning_language": "ru",
                "daily_word_goal": 10,
            },
            custom_vocabulary_practice=MagicMock(return_value=[]),
        )
        message = SimpleNamespace(reply_text=AsyncMock())
        update = SimpleNamespace(effective_message=message)
        context = SimpleNamespace(user_data={"interface_locale": "ru"})
        runtime = SimpleNamespace(role="learner", user_id=42, store=store)
        token = bot._ACTIVE_RUNTIME.set(runtime)
        try:
            await bot.cmd_custom_practice.__wrapped__(update, context)
        finally:
            bot._ACTIVE_RUNTIME.reset(token)

        store.custom_vocabulary_practice.assert_called_once_with(
            42,
            target_language="fr",
            meaning_language="ru",
            limit=10,
        )

    async def test_custom_practice_cards_use_standard_visual_hierarchy_and_labels(self):
        entries = [
            {
                "entry_id": "custom-1",
                "target": "bonjour",
                "meaning": "привет",
                "transcription": "/bɔ̃.ʒuʁ/",
            },
            {
                "entry_id": "custom-2",
                "target": "merci",
                "meaning": "спасибо",
                "transcription": "/mɛʁ.si/",
            },
        ]
        state = {
            "entries": entries,
            "position": 0,
            "target_language": "fr",
            "meaning_language": "ru",
            "expires_at": 4_000_000_000,
        }
        message = SimpleNamespace(chat_id=123, reply_text=AsyncMock())
        context = SimpleNamespace(
            user_data={
                "interface_locale": "ru",
                bot.CUSTOM_VOCABULARY_PRACTICE_KEY: state,
            },
            bot=SimpleNamespace(send_voice=AsyncMock()),
        )

        await bot._send_custom_vocabulary_card(message, context, locale="ru")

        store = SimpleNamespace(
            product_profile=lambda _user_id: {
                "active_lang": "fr",
                "native_language": "en",
                "custom_vocabulary_meaning_language": "ru",
            }
        )
        query = SimpleNamespace(
            data="custom-practice:show:custom-1",
            answer=AsyncMock(),
            edit_message_text=AsyncMock(),
            message=message,
        )
        update = SimpleNamespace(
            callback_query=query,
            effective_user=SimpleNamespace(id=42),
        )
        with patch.object(bot, "get_store", return_value=store):
            await bot.custom_practice_cb.__wrapped__(update, context)

        front = message.reply_text.await_args.args[0]
        self.assertIn("*Карточка 1 из 2*", front)
        self.assertIn("▰▰▰▱▱", front)
        self.assertIn("🇫🇷 *bonjour /bɔ̃.ʒuʁ/*", front)
        self.assertIn(localization.translate("learning_card_hint", "ru"), front)
        self.assertNotIn("привет", front)
        self.assertEqual(
            message.reply_text.await_args.kwargs["parse_mode"],
            "Markdown",
        )
        front_button = message.reply_text.await_args.kwargs[
            "reply_markup"
        ].inline_keyboard[0][0]
        self.assertEqual(
            front_button.text,
            localization.translate("learning_show_meaning", "ru"),
        )

        back = query.edit_message_text.await_args.args[0]
        self.assertIn("*Карточка 1 из 2*", back)
        self.assertIn("▰▰▰▱▱", back)
        self.assertIn("🇷🇺 *привет*", back)
        self.assertIn("🇫🇷 *bonjour /bɔ̃.ʒuʁ/*", back)
        self.assertEqual(
            query.edit_message_text.await_args.kwargs["parse_mode"],
            "Markdown",
        )
        rating_labels = [
            button.text
            for button in query.edit_message_text.await_args.kwargs[
                "reply_markup"
            ].inline_keyboard[0]
        ]
        self.assertEqual(
            rating_labels,
            [
                localization.translate("learning_dont_know", "ru"),
                localization.translate("learning_know", "ru"),
            ],
        )

    async def test_custom_practice_automatically_pronounces_each_front_card(self):
        entries = [
            {
                "entry_id": "custom-1",
                "target": "bonjour",
                "meaning": "привет",
                "transcription": "/bɔ̃.ʒuʁ/",
            },
            {
                "entry_id": "custom-2",
                "target": "merci",
                "meaning": "спасибо",
                "transcription": "/mɛʁ.si/",
            },
        ]
        state = {
            "entries": entries,
            "position": 0,
            "target_language": "fr",
            "meaning_language": "ru",
            "expires_at": 4_000_000_000,
        }
        message = SimpleNamespace(chat_id=123, reply_text=AsyncMock())
        context = SimpleNamespace(
            user_data={
                "interface_locale": "ru",
                bot.CUSTOM_VOCABULARY_PRACTICE_KEY: state,
            },
            bot=SimpleNamespace(send_voice=AsyncMock()),
        )
        store = SimpleNamespace(
            product_profile=lambda _user_id: {
                "active_lang": "fr",
                "native_language": "en",
                "custom_vocabulary_meaning_language": "ru",
            },
            rate_custom_vocabulary=MagicMock(),
        )
        query = SimpleNamespace(
            data="custom-practice:known:custom-1",
            answer=AsyncMock(),
            edit_message_reply_markup=AsyncMock(),
            message=message,
        )
        update = SimpleNamespace(
            callback_query=query,
            effective_user=SimpleNamespace(id=42),
        )
        pack = bot.CATALOG.require("fr-basics-100")

        with (
            patch.object(
                bot,
                "get_audio",
                new=AsyncMock(side_effect=[b"bonjour-audio", b"merci-audio"]),
            ) as get_audio,
            patch.object(
                bot,
                "send_pronunciation_audio",
                new=AsyncMock(),
            ) as send_audio,
            patch.object(bot, "get_store", return_value=store),
        ):
            await bot._send_custom_vocabulary_card(message, context, locale="ru")
            await bot.custom_practice_cb.__wrapped__(update, context)

        self.assertEqual(
            [call.args[0] for call in get_audio.await_args_list],
            ["bonjour", "merci"],
        )
        for call in get_audio.await_args_list:
            self.assertEqual(call.kwargs["voice"], pack.pronunciation.tts_voice)
            self.assertEqual(call.kwargs["rate"], pack.pronunciation.tts_rate)
        self.assertEqual(send_audio.await_count, 2)
        self.assertEqual(
            [call.kwargs["chat_id"] for call in send_audio.await_args_list],
            [123, 123],
        )
        self.assertEqual(
            [call.kwargs["title"] for call in send_audio.await_args_list],
            ["bonjour", "merci"],
        )

    async def test_custom_practice_rating_edits_the_same_card_for_next_word(self):
        state = {
            "entries": [
                {
                    "entry_id": "custom-1",
                    "target": "bonjour",
                    "meaning": "привет",
                    "transcription": "/bɔ̃.ʒuʁ/",
                },
                {
                    "entry_id": "custom-2",
                    "target": "merci",
                    "meaning": "спасибо",
                    "transcription": "/mɛʁ.si/",
                },
            ],
            "position": 0,
            "target_language": "fr",
            "meaning_language": "ru",
            "expires_at": 4_000_000_000,
        }
        message = SimpleNamespace(chat_id=123, reply_text=AsyncMock())
        context = SimpleNamespace(
            user_data={
                "interface_locale": "ru",
                bot.CUSTOM_VOCABULARY_PRACTICE_KEY: state,
            },
            bot=SimpleNamespace(send_voice=AsyncMock()),
        )
        store = SimpleNamespace(
            product_profile=lambda _user_id: {
                "active_lang": "fr",
                "native_language": "en",
                "custom_vocabulary_meaning_language": "ru",
            },
            rate_custom_vocabulary=MagicMock(),
        )
        query = SimpleNamespace(
            data="custom-practice:known:custom-1",
            answer=AsyncMock(),
            edit_message_reply_markup=AsyncMock(),
            edit_message_text=AsyncMock(),
            message=message,
        )
        update = SimpleNamespace(
            callback_query=query,
            effective_user=SimpleNamespace(id=42),
        )

        with (
            patch.object(bot, "get_audio", new=AsyncMock(return_value=b"audio")),
            patch.object(bot, "send_pronunciation_audio", new=AsyncMock()),
            patch.object(bot, "get_store", return_value=store),
        ):
            await bot._send_custom_vocabulary_card(message, context, locale="ru")
            message.reply_text.reset_mock()
            await bot.custom_practice_cb.__wrapped__(update, context)

        message.reply_text.assert_not_awaited()
        query.edit_message_text.assert_awaited_once()
        next_front = query.edit_message_text.await_args.args[0]
        self.assertIn("*Карточка 2 из 2*", next_front)
        self.assertIn("▰▰▰▰▰", next_front)
        self.assertIn("🇫🇷 *merci /mɛʁ.si/*", next_front)

    async def test_complete_text_list_previews_then_saves_without_ai(self):
        runtime_store = SimpleNamespace(
            product_profile=lambda _user_id: {
                "active_lang": "es",
                "native_language": "ru",
            }
        )
        start_message = SimpleNamespace(reply_text=AsyncMock())
        start_update = SimpleNamespace(effective_message=start_message)
        context = SimpleNamespace(
            user_data={
                bot.PENDING_DICTIONARY_LOOKUP_KEY: {"old": True},
                bot.PENDING_AI_TUTOR_KEY: {"old": True},
            }
        )
        runtime = SimpleNamespace(role="learner", user_id=42, store=runtime_store)
        token = bot._ACTIVE_RUNTIME.set(runtime)
        try:
            with patch.object(bot, "record_product_event"):
                await bot.cmd_add_words.__wrapped__(start_update, context)
        finally:
            bot._ACTIVE_RUNTIME.reset(token)

        selection_store = SimpleNamespace(
            product_profile=lambda _user_id: {
                "active_lang": "es",
                "native_language": "ru",
                "custom_vocabulary_meaning_language": None,
            },
            set_custom_vocabulary_meaning_language=MagicMock(return_value="ru"),
            update_product_profile=MagicMock(),
        )
        selection_query = SimpleNamespace(
            data="custom-import:language:ru",
            answer=AsyncMock(),
            edit_message_reply_markup=AsyncMock(),
            edit_message_text=AsyncMock(),
            message=SimpleNamespace(reply_text=AsyncMock()),
        )
        selection_update = SimpleNamespace(
            callback_query=selection_query,
            effective_user=SimpleNamespace(id=42),
        )
        with patch.object(bot, "get_store", return_value=selection_store):
            await bot.custom_import_cb.__wrapped__(selection_update, context)

        self.assertNotIn(bot.PENDING_DICTIONARY_LOOKUP_KEY, context.user_data)
        self.assertNotIn(bot.PENDING_AI_TUTOR_KEY, context.user_data)
        incoming = SimpleNamespace(
            text="hola — привет\ncasa — дом",
            reply_text=AsyncMock(),
        )
        text_update = SimpleNamespace(
            message=incoming,
            effective_user=SimpleNamespace(id=42),
        )
        with patch.object(
            bot,
            "get_ai_tutor_service",
            side_effect=AssertionError("complete pasted list must not call AI"),
        ):
            await bot._handle_custom_vocabulary_text(text_update, context)

        preview = context.user_data[bot.CUSTOM_VOCABULARY_PREVIEW_KEY]
        self.assertEqual(
            [(entry["target"], entry["meaning"]) for entry in preview["entries"]],
            [("hola", "привет"), ("casa", "дом")],
        )
        persistence = SimpleNamespace(
            product_profile=lambda _user_id: {
                "active_lang": "es",
                "native_language": "ru",
            },
            upsert_custom_vocabulary=MagicMock(
                return_value={"inserted": 2, "updated": 0, "total": 2}
            ),
        )
        callback_message = SimpleNamespace(reply_text=AsyncMock())
        query = SimpleNamespace(
            data=f"custom-import:save:{preview['token']}",
            answer=AsyncMock(),
            edit_message_reply_markup=AsyncMock(),
            message=callback_message,
        )
        callback_update = SimpleNamespace(
            callback_query=query,
            effective_user=SimpleNamespace(id=42),
        )
        with (
            patch.object(bot, "get_store", return_value=persistence),
            patch.object(bot, "record_product_event"),
        ):
            await bot.custom_import_cb.__wrapped__(callback_update, context)

        persistence.upsert_custom_vocabulary.assert_called_once()
        self.assertNotIn(bot.PENDING_CUSTOM_VOCABULARY_KEY, context.user_data)
        self.assertNotIn(bot.CUSTOM_VOCABULARY_PREVIEW_KEY, context.user_data)


_CustomVocabularyResponsesPayload = json.dumps(
    {
        "entries": [
            {
                "target": "viaje",
                "meaning": "поездка",
                "transcription": "/ˈbjaxe/",
            }
        ]
    },
    ensure_ascii=False,
)


if __name__ == "__main__":
    unittest.main()
