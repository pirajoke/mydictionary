import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch


os.environ.setdefault("BOT_TOKEN", "123456:TESTTOKEN")
os.environ.setdefault("ALLOWED_USER_ID", "1")
os.environ.setdefault("ALLOW_SQLITE_DEV", "true")

import bot
from mydictionary.content import target_text
from mydictionary.storage import DatabaseStore


class CuratedLanguagePairTest(unittest.TestCase):
    def _runtime(self, meaning_language: str, target_language: str):
        pack = bot.CATALOG.pack_for_language(target_language, "learner")
        self.assertIsNotNone(pack)
        store = SimpleNamespace(load_word_progress=lambda *_args: {})
        runtime = bot.LearnerRuntime(
            user_id=42,
            store=store,
            progress={
                **bot.PROGRESS_DEFAULTS,
                "active_lang": target_language,
                "active_pack_id": pack.pack_id,
            },
            meaning_language=meaning_language,
        )
        return runtime

    def test_ac_lang_06_french_meaning_replaces_russian_on_english_card(self):
        runtime = self._runtime("fr", "en")
        token = bot._ACTIVE_RUNTIME.set(runtime)
        try:
            idx = next(
                index for index, word in enumerate(bot.W())
                if target_text(word) == "kitchen"
            )

            details = bot.format_word_details(idx)

            self.assertEqual(details.splitlines()[0], "🇫🇷 *cuisine*")
            self.assertNotIn("🇷🇺", details)
            self.assertNotIn("кухня", details)
        finally:
            bot._ACTIVE_RUNTIME.reset(token)

    def test_ac_lang_07_quiz_and_typed_answer_use_selected_pair(self):
        runtime = self._runtime("fr", "en")
        token = bot._ACTIVE_RUNTIME.set(runtime)
        try:
            idx = next(
                index for index, word in enumerate(bot.W())
                if target_text(word) == "kitchen"
            )
            indices = list(range(20))
            if idx not in indices:
                indices[-1] = idx

            options = bot.build_block_quiz_options(indices, idx)

            self.assertIn("cuisine", options)
            self.assertNotIn("кухня", options)
            self.assertTrue(bot.meaning_answer_matches(bot.W()[idx], "cuisine"))
            self.assertFalse(bot.meaning_answer_matches(bot.W()[idx], "кухня"))
        finally:
            bot._ACTIVE_RUNTIME.reset(token)

    def test_ec_lang_01_russian_keeps_legacy_targets_but_excludes_russian(self):
        pack_ids = {
            pack.pack_id for pack in bot.compatible_onboarding_packs("ru")
        }
        self.assertIn("ja-basics-100", pack_ids)
        self.assertIn("vi-basics-101", pack_ids)
        self.assertNotIn("ru-basics-100", pack_ids)

    def test_err_lang_02_non_russian_pair_never_offers_legacy_target(self):
        pack_ids = {
            pack.pack_id for pack in bot.compatible_onboarding_packs("fr")
        }
        self.assertIn("en-basics-100", pack_ids)
        self.assertNotIn("fr-basics-100", pack_ids)
        self.assertNotIn("ja-basics-100", pack_ids)
        self.assertNotIn("vi-basics-101", pack_ids)

    def test_ac_lang_04_switcher_keeps_only_compatible_targets(self):
        runtime = self._runtime("fr", "en")
        token = bot._ACTIVE_RUNTIME.set(runtime)
        try:
            pack_ids = {pack.pack_id for pack in bot.switchable_packs()}
        finally:
            bot._ACTIVE_RUNTIME.reset(token)

        self.assertIn("en-basics-100", pack_ids)
        self.assertNotIn("fr-basics-100", pack_ids)
        self.assertNotIn("ja-basics-100", pack_ids)


class LanguagePairOnboardingTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory(prefix="language-pair-")
        self.store = DatabaseStore(
            f"sqlite:///{Path(self.temp_dir.name) / 'pair.db'}"
        )

    def tearDown(self):
        self.store.close()
        self.temp_dir.cleanup()

    def _update(self, user_id: int = 9701, language_code: str = "fr-FR"):
        message = SimpleNamespace(
            chat_id=17,
            reply_text=AsyncMock(),
            reply_photo=AsyncMock(),
        )
        query = SimpleNamespace(
            data="onboarding:begin",
            answer=AsyncMock(),
            edit_message_text=AsyncMock(),
            message=message,
        )
        update = SimpleNamespace(
            callback_query=query,
            effective_message=message,
            effective_user=SimpleNamespace(
                id=user_id,
                first_name="Marc",
                language_code=language_code,
            ),
        )
        return update, query

    async def test_ac_lang_02_begin_asks_meaning_language_without_persisting_it(self):
        update, query = self._update()
        with (
            patch.object(bot, "_STORE", self.store),
            patch.object(bot, "BOT_ACCESS_MODE", "public"),
            patch.object(bot, "LEGACY_USER_ID", None),
            patch.object(bot, "ADMIN_USER_IDS", set()),
        ):
            await bot.onboarding_cb(update, SimpleNamespace(user_data={}))

        text = query.edit_message_text.await_args.args[0]
        keyboard = query.edit_message_text.await_args.kwargs["reply_markup"]
        callbacks = [row[0].callback_data for row in keyboard.inline_keyboard]
        self.assertIn("Étape 1 sur 3", text)
        self.assertEqual(callbacks[0], "onboarding:native:fr")
        self.assertTrue(
            all(value.startswith("onboarding:native:") for value in callbacks)
        )
        self.assertIsNone(self.store.product_profile(9701)["native_language"])

    async def test_ac_lang_03_native_choice_filters_learning_languages(self):
        update, query = self._update()
        query.data = "onboarding:native:fr"
        context = SimpleNamespace(user_data={})
        with (
            patch.object(bot, "_STORE", self.store),
            patch.object(bot, "BOT_ACCESS_MODE", "public"),
            patch.object(bot, "LEGACY_USER_ID", None),
            patch.object(bot, "ADMIN_USER_IDS", set()),
        ):
            await bot.onboarding_cb(update, context)

        text = query.edit_message_text.await_args.args[0]
        keyboard = query.edit_message_text.await_args.kwargs["reply_markup"]
        callbacks = {
            row[0].callback_data for row in keyboard.inline_keyboard
        }
        self.assertIn("Étape 2 sur 3", text)
        self.assertIn("onboarding:pack:en-basics-100", callbacks)
        self.assertNotIn("onboarding:pack:fr-basics-100", callbacks)
        self.assertNotIn("onboarding:pack:ja-basics-100", callbacks)
        self.assertEqual(
            self.store.product_profile(9701)["native_language"], "fr"
        )
        self.assertEqual(context.user_data["onboarding_native_language"], "fr")

    async def test_err_lang_01_forged_incompatible_pack_is_not_activated(self):
        update, query = self._update()
        context = SimpleNamespace(user_data={"onboarding_native_language": "fr"})
        self.store.ensure_user(update.effective_user)
        self.store.update_product_profile(9701, native_language="fr")
        query.data = "onboarding:pack:ja-basics-100"
        with (
            patch.object(bot, "_STORE", self.store),
            patch.object(bot, "BOT_ACCESS_MODE", "public"),
            patch.object(bot, "LEGACY_USER_ID", None),
            patch.object(bot, "ADMIN_USER_IDS", set()),
        ):
            await bot.onboarding_cb(update, context)

        self.assertIn("disponible", query.edit_message_text.await_args.args[0])
        profile = self.store.product_profile(9701)
        self.assertIsNone(profile["active_pack_id"])
        self.assertIsNone(profile["onboarding_completed_at"])

    async def test_ac_lang_05_complete_onboarding_persists_french_to_english(self):
        update, query = self._update(user_id=9702)
        context = SimpleNamespace(user_data={})
        with (
            patch.object(bot, "_STORE", self.store),
            patch.object(bot, "BOT_ACCESS_MODE", "public"),
            patch.object(bot, "LEGACY_USER_ID", None),
            patch.object(bot, "ADMIN_USER_IDS", set()),
        ):
            for callback in (
                "onboarding:begin",
                "onboarding:native:fr",
                "onboarding:pack:en-basics-100",
                "onboarding:pace:5",
            ):
                query.data = callback
                await bot.onboarding_cb(update, context)

        profile = self.store.product_profile(9702)
        self.assertEqual(profile["native_language"], "fr")
        self.assertEqual(profile["active_lang"], "en")
        self.assertEqual(profile["active_pack_id"], "en-basics-100")
        self.assertEqual(profile["daily_word_goal"], 5)
        self.assertIsNotNone(profile["onboarding_completed_at"])


if __name__ == "__main__":
    unittest.main()
