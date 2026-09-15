"""Synthetic SQLite verification of durable native/chat shared learning state."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch
from uuid import uuid4

from sqlalchemy import func, select

os.environ.setdefault("BOT_TOKEN", "123456:TESTTOKEN_ABCDEFGHIJKLMNOP")
os.environ.setdefault("ALLOWED_USER_ID", "1")
os.environ.setdefault("ALLOW_SQLITE_DEV", "true")

import bot
from mydictionary import bot_learning, swipe
from mydictionary.privacy import RetentionPolicy, apply_retention, erase_user_learning_data
from mydictionary.storage import BotLearningSession, DatabaseStore, User, UserProgress, WordProgress, vocabulary_id_for

USER_ID, OTHER_ID = 749001, 749002


class BotLearningSessionsTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="native-chat-learning-")
        self.url = f"sqlite:///{Path(self.temp.name) / 'learning.sqlite3'}"
        self.store = DatabaseStore(self.url)
        self.catalog = bot.CATALOG
        self.pack = self.catalog.require("en-basics-100")
        self.words = self.catalog.words(self.pack)
        for user_id in (USER_ID, OTHER_ID):
            self.store.ensure_user_id(user_id)
            with self.store.Session.begin() as session:
                user = session.get(User, user_id)
                user.access_status = user.privacy_status = "active"
                user.native_language = "ru"
                user.interface_locale = "en"
            self.store.activate_pack(user_id, pack_id=self.pack.pack_id, language="en", source="test")
            self.store.update_product_profile(user_id, native_language="ru", learning_goal="personal",
                                              daily_word_goal=5, complete_onboarding=True,
                                              onboarding_version=bot.CURRENT_ONBOARDING_VERSION)

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    def block(self, indices=(0, 1), *, pack=None, user_id=USER_ID, mode="flash"):
        pack = pack or self.pack
        state = {"interface_locale": "en"}
        bot.reset_block_state(state, list(indices), pack.target_language, None, pack.pack_id, lesson_kind="daily")
        bot.start_block_attempt(state, mode)
        bot_learning.save(self.store, user_id=user_id, catalog=self.catalog, state=state)
        return state

    def load(self, user_id=USER_ID):
        return bot_learning.load(self.store, user_id=user_id, catalog=self.catalog)

    def rate(self, state, index=None, knew=True):
        index = state["block_indices"][state["block_pos"]] if index is None else index
        return bot_learning.rate(self.store, user_id=USER_ID, catalog=self.catalog,
                                 state=state, word_index=index, knew=knew)

    def profile(self):
        with self.store.Session() as session:
            row = session.get(UserProgress, USER_ID)
            return {key: getattr(row, key) for key in ("xp", "today_xp", "sessions", "total_correct", "total_wrong", "streak")}

    def word(self, index=0):
        with self.store.Session() as session:
            row = session.get(WordProgress, (USER_ID, self.pack.storage_key, vocabulary_id_for(self.words[index])))
            return None if row is None else {key: getattr(row, key) for key in ("correct_count", "wrong_count", "interval", "next_review", "updated_at")}

    def swipe_rate(self, deck, *, knew=True, operation_id=None):
        oid = operation_id or str(uuid4())
        result = swipe.mutate(self.store, user_id=USER_ID, catalog=self.catalog, action="rate",
                              session_id=deck["session_id"], operation_id=oid,
                              word_index=deck["queue"][0], knew=knew)
        return result, oid

    def chat_fixture(self, *, state=None, text="", callback=None):
        user = SimpleNamespace(id=USER_ID, first_name="Synthetic", last_name=None,
                               username=None, language_code="en", is_bot=False)
        message = SimpleNamespace(chat_id=USER_ID, text=text, reply_text=AsyncMock())
        query = None if callback is None else SimpleNamespace(
            data=callback, answer=AsyncMock(), edit_message_text=AsyncMock(),
            edit_message_reply_markup=AsyncMock(), message=message)
        update = SimpleNamespace(effective_user=user, effective_message=message, message=message,
                                 callback_query=query, effective_chat=SimpleNamespace(type="private"))
        return update, SimpleNamespace(user_data=dict(state or {}))

    async def chat_call(self, handler, update, context):
        with (
            patch.object(bot, "get_store", return_value=self.store),
            patch.object(bot, "BOT_ACCESS_MODE", "pilot"),
            patch.object(bot, "send_pronunciation", new_callable=AsyncMock),
        ):
            return await handler(update, context)

    def test_progress_mode_position_and_card_token_survive_store_restart(self):
        issued = self.block(mode="type")
        rated = self.rate(issued)["state"]
        self.store.close()
        self.store = DatabaseStore(self.url, migrate=False)
        restored = self.load()
        for key in ("block_indices", "block_all_indices", "block_mode", "block_pos", "block_correct", "block_session"):
            self.assertEqual(restored[key], rated[key])
        self.assertEqual(restored["block_pos"], 1)
        self.assertEqual(self.word()["correct_count"], 1)

    def test_switching_packs_keeps_independent_resumable_native_blocks(self):
        english = self.block(mode="quiz")
        french = self.catalog.require("fr-basics-100")
        self.store.activate_pack(USER_ID, pack_id=french.pack_id, language="fr", source="test")
        self.assertIsNone(self.load())
        french_state = self.block((2, 3), pack=french, mode="type")
        self.assertEqual(self.load()["block_session"], french_state["block_session"])
        self.store.activate_pack(USER_ID, pack_id=self.pack.pack_id, language="en", source="test")
        self.assertEqual(self.load()["block_session"], english["block_session"])
        self.assertEqual(self.load()["block_mode"], "quiz")

    def test_final_rating_awards_one_completion_and_replay_cannot_award_again(self):
        issued = self.block((0,))
        result = self.rate(issued)
        self.assertEqual(result["state"]["block_pos"], 1)
        self.assertTrue(result["state"]["block_reward_granted"])
        before = self.profile()
        self.assertEqual(before["sessions"], 1)
        self.assertEqual(before["xp"], result["streak_bonus"] + 10 + 25)
        with self.assertRaises(bot_learning.BotLearningError):
            self.rate(issued, index=0)
        bot_learning.save(self.store, user_id=USER_ID, catalog=self.catalog, state=issued)
        self.assertEqual(self.profile(), before)
        self.assertEqual(self.load()["block_pos"], 1)

    def test_accepted_card_rotates_token_and_stale_position_cannot_rewind(self):
        issued = self.block()
        result = self.rate(issued)
        self.assertNotEqual(result["state"]["block_session"], issued["block_session"],
                            "Accepted cards invalidate delivered callback tokens")
        before = self.profile()
        with self.assertRaises(bot_learning.BotLearningError):
            self.rate(issued, index=0)
        bot_learning.save(self.store, user_id=USER_ID, catalog=self.catalog, state=issued)
        self.assertEqual(self.load()["block_pos"], 1)
        self.assertEqual(self.profile(), before)

    def test_rating_merges_existing_shared_xp_instead_of_overwriting_stale_profile(self):
        issued = self.block()
        with self.store.Session.begin() as session:
            session.get(UserProgress, USER_ID).xp += 100
        result = self.rate(issued)
        self.assertEqual(self.profile()["xp"], 100 + result["streak_bonus"] + 10)

    def test_swipe_mutation_invalidates_issued_native_card_without_extra_awards(self):
        issued = self.block()
        deck = swipe.deck(self.store, user_id=USER_ID, catalog=self.catalog, mode="new")
        self.assertEqual(deck["queue"][0], 0)
        self.swipe_rate(deck)
        before = self.profile(), self.word()
        with self.assertRaises(bot_learning.BotLearningError) as caught:
            self.rate(issued)
        self.assertEqual(caught.exception.code, "progress_changed")
        self.assertEqual((self.profile(), self.word()), before)

    def test_swipe_undo_refuses_to_overwrite_later_native_rating(self):
        deck = swipe.deck(self.store, user_id=USER_ID, catalog=self.catalog, mode="new")
        _, oid = self.swipe_rate(deck)
        issued = self.block((0, 1))
        self.rate(issued)
        before = self.profile(), self.word()
        with self.assertRaises(swipe.SwipeError) as caught:
            swipe.mutate(self.store, user_id=USER_ID, catalog=self.catalog, action="undo",
                         session_id=deck["session_id"], operation_id=oid)
        self.assertEqual(caught.exception.error, "progress_changed")
        self.assertEqual((self.profile(), self.word()), before)

    def test_hidden_changed_expired_content_does_not_mutate_learning(self):
        issued = self.block()
        before = self.profile()
        with patch("mydictionary.catalog.ContentPack.visible_to", return_value=False):
            self.assertIsNone(self.load())
            with self.assertRaises(bot_learning.BotLearningError):
                self.rate(issued)
        edited = deepcopy(self.words)
        edited[0]["target"] = "synthetic editorial replacement"
        with patch.object(self.catalog, "words", return_value=edited):
            self.assertIsNone(self.load())
            with self.assertRaises(bot_learning.BotLearningError):
                self.rate(issued)
        with self.store.Session.begin() as session:
            session.get(BotLearningSession, (USER_ID, self.pack.pack_id)).created_at = datetime.now(timezone.utc) - timedelta(days=8)
        self.assertIsNone(self.load())
        with self.assertRaises(bot_learning.BotLearningError):
            self.rate(issued)
        self.assertEqual(self.profile(), before)
        self.assertIsNone(self.word())

    def test_blocked_and_erased_access_cannot_use_native_saved_cards(self):
        issued = self.block()
        before = self.profile()
        for field, value in (("access_status", "blocked"), ("privacy_status", "erased")):
            with self.store.Session.begin() as session:
                user = session.get(User, USER_ID)
                user.access_status = user.privacy_status = "active"
                setattr(user, field, value)
            with self.assertRaises(bot_learning.BotLearningError) as caught:
                self.rate(issued)
            self.assertEqual(caught.exception.code, "access_denied")
        self.assertEqual(self.profile(), before)

    def test_sessions_store_no_vocabulary_text_and_erasure_retention_isolate_owners(self):
        self.block()
        self.block(user_id=OTHER_ID)
        with self.store.Session() as session:
            rows = session.scalars(select(BotLearningSession)).all()
            payload = json.dumps([json.loads(row.state_json) for row in rows])
            for key in ("target", "meaning", "term", "prompt", "answer", "username"):
                self.assertNotIn(f'"{key}":', payload)
        erase_user_learning_data(self.store, USER_ID, actor="test")
        with self.store.Session() as session:
            self.assertEqual(session.scalar(select(func.count()).select_from(BotLearningSession)), 1)
        self.assertIsNotNone(self.load(OTHER_ID))
        with self.store.Session.begin() as session:
            session.get(BotLearningSession, (OTHER_ID, self.pack.pack_id)).created_at = datetime.now(timezone.utc) - timedelta(days=8)
        apply_retention(self.store, RetentionPolicy.from_env({}))
        with self.store.Session() as session:
            self.assertEqual(session.scalar(select(func.count()).select_from(BotLearningSession)), 0)

    async def test_actual_auth_restores_a_saved_block_into_empty_chat_context(self):
        state = self.block(mode="quiz")
        telegram_user = SimpleNamespace(id=USER_ID, first_name="Synthetic", last_name=None,
                                        username=None, language_code="en", is_bot=False)
        message = SimpleNamespace(chat_id=USER_ID, reply_text=AsyncMock())
        update = SimpleNamespace(effective_user=telegram_user, effective_message=message,
                                 message=message, callback_query=None)
        context = SimpleNamespace(user_data={})
        observed = {}

        @bot.auth
        async def probe(update, context):
            observed.update(context.user_data)

        with (
            patch.object(bot, "get_store", return_value=self.store),
            patch.object(bot, "BOT_ACCESS_MODE", "pilot"),
        ):
            await probe(update, context)
        self.assertEqual(observed.get("block_session"), state["block_session"],
                         "Actual authenticated chat updates restore durable native state")
        self.assertEqual(observed.get("block_mode"), "quiz")

    async def test_actual_auth_persists_a_new_block_after_handler_returns(self):
        telegram_user = SimpleNamespace(id=USER_ID, first_name="Synthetic", last_name=None,
                                        username=None, language_code="en", is_bot=False)
        message = SimpleNamespace(chat_id=USER_ID, reply_text=AsyncMock())
        update = SimpleNamespace(effective_user=telegram_user, effective_message=message,
                                 message=message, callback_query=None)
        context = SimpleNamespace(user_data={})

        @bot.auth
        async def probe(update, context):
            bot.reset_block_state(context.user_data, [0, 1], "en", None, self.pack.pack_id,
                                  lesson_kind="daily")
            bot.start_block_attempt(context.user_data, "flash")

        with patch.object(bot, "get_store", return_value=self.store), patch.object(bot, "BOT_ACCESS_MODE", "pilot"):
            await probe(update, context)
        restored = self.load()
        self.assertIsNotNone(restored, "Authenticated learning updates persist after handler returns")
        self.assertEqual(restored["block_session"], context.user_data["block_session"])
        self.assertEqual(restored["block_mode"], "flash")

    async def test_standalone_type_pending_survives_auth_and_typed_answer(self):
        issued = self.block()
        update, context = self.chat_fixture(state=issued, text="/type")
        with patch.object(bot, "pick_word", return_value=3):
            await self.chat_call(bot.cmd_type, update, context)
        self.assertEqual(context.user_data.get("type_idx"), 3)
        self.assertIsNone(context.user_data.get("block_session"))
        before = self.profile()
        update.message.text = "synthetic incorrect translation"
        await self.chat_call(bot.handle_type_answer, update, context)
        after = self.profile()
        self.assertEqual(after["total_correct"] + after["total_wrong"],
                         before["total_correct"] + before["total_wrong"] + 1,
                         "Auth restoration must not swallow a standalone /type answer")
        self.assertIsNone(context.user_data.get("type_idx"))
        self.assertIsNone(context.user_data.get("block_session"))
        self.assertEqual(self.load()["block_session"], issued["block_session"],
                         "Standalone practice leaves the durable native block resumable")

    async def test_expired_same_pack_ram_is_cleared_before_authenticated_handler(self):
        issued = self.block()
        with self.store.Session.begin() as session:
            session.get(BotLearningSession, (USER_ID, self.pack.pack_id)).created_at = datetime.now(timezone.utc) - timedelta(days=8)
        update, context = self.chat_fixture(state=issued)
        observed = {}

        @bot.auth
        async def probe(update, context):
            observed.update(context.user_data)

        await self.chat_call(probe, update, context)
        self.assertIsNone(observed.get("block_session"), "Expired RAM cannot remain an actionable Continue session")
        self.assertIsNone(observed.get("type_idx"))
        self.assertIsNone(self.load())

    async def test_explicit_different_pack_topic_replaces_cached_session_marker(self):
        english = self.block()
        french = self.catalog.require("fr-basics-100")
        self.store.activate_pack(USER_ID, pack_id=french.pack_id, language="fr", source="test")
        self.block((2, 3), pack=french)
        self.store.activate_pack(USER_ID, pack_id=self.pack.pack_id, language="en", source="test")
        update, context = self.chat_fixture(state=english, callback=f"learn_topic:{french.pack_id}:all")
        with patch.object(bot, "pick_block", return_value=[6, 7]):
            await self.chat_call(bot.learn_topic_cb, update, context)
        restored = self.load()
        self.assertEqual(restored["block_pack_id"], french.pack_id)
        self.assertEqual(restored["block_all_indices"], [6, 7],
                         "Explicit topic choice persists its new queue, not cached target-pack state")
        self.assertEqual(restored["block_session"], context.user_data["block_session"])

    async def test_actual_mode_change_after_rating_keeps_position_and_correct_count(self):
        issued = self.block()
        rated = self.rate(issued)["state"]
        update, context = self.chat_fixture(state=rated, callback=f"bmode:{rated['block_session']}:quiz")
        await self.chat_call(bot.block_mode_cb, update, context)
        restored = self.load()
        self.assertEqual(restored["block_mode"], "quiz")
        self.assertEqual((restored["block_pos"], restored["block_correct"]), (1, 1))
        before = self.profile()
        with self.assertRaises(bot_learning.BotLearningError):
            self.rate(restored, index=0)
        self.assertEqual(self.profile(), before)

    async def test_swipe_conflict_then_explicit_continue_reissues_and_accepts_remaining_card(self):
        issued = self.rate(self.block((0, 1, 2)))["state"]
        deck = swipe.deck(self.store, user_id=USER_ID, catalog=self.catalog, mode="new")
        self.assertEqual(deck["queue"][0], 1)
        self.swipe_rate(deck)
        update, context = self.chat_fixture(state=issued, callback=f"bflash_knew:{issued['block_session']}:1")
        before = self.profile()
        await self.chat_call(bot.block_flash_rate_cb, update, context)
        self.assertEqual(self.profile(), before)
        self.assertTrue(context.user_data.get("native_reissue_required"))
        continued, _ = self.chat_fixture(text=bot.quick_action_label("continue", "en"))
        await self.chat_call(bot.handle_quick_action, continued, context)
        refreshed = self.load()
        self.assertNotEqual(refreshed["block_session"], issued["block_session"])
        self.assertEqual(refreshed["block_indices"], [1, 2], "Continue reissues only the remaining queue")
        answered, _ = self.chat_fixture(callback=f"bflash_knew:{refreshed['block_session']}:1")
        await self.chat_call(bot.block_flash_rate_cb, answered, context)
        self.assertEqual(self.load()["block_pos"], 1)
        self.assertEqual(self.word(1)["correct_count"], 2,
                         "Explicit Continue refreshes the issued SRS snapshot after a conflict")
        self.assertEqual(self.word(0)["correct_count"], 1, "Already accepted words are not regraded")
        self.assertEqual(self.profile()["total_correct"], before["total_correct"] + 1)

    async def test_duplicate_written_telegram_update_cannot_grade_the_next_card(self):
        issued = self.block((0, 1, 2), mode="type")
        issued.update(type_idx=0, block_typing=True)
        bot_learning.save(self.store, user_id=USER_ID, catalog=self.catalog, state=issued)
        update, context = self.chat_fixture(state=issued, text="synthetic incorrect written answer")
        update.update_id = 810001
        await self.chat_call(bot.handle_type_answer, update, context)
        self.assertEqual(self.load()["block_pos"], 1)
        before = self.profile()
        first_word, next_word = self.word(0), self.word(1)
        await self.chat_call(bot.handle_type_answer, update, context)
        self.assertEqual(self.profile(), before,
                         "Duplicate Telegram delivery must not award another answer or XP")
        self.assertEqual(self.load()["block_pos"], 1,
                         "Replayed written text must not advance the next restored card")
        self.assertEqual((self.word(0), self.word(1)), (first_word, next_word))

    async def test_distinct_written_telegram_updates_can_answer_consecutive_cards(self):
        issued = self.block((0, 1, 2), mode="type")
        issued.update(type_idx=0, block_typing=True)
        bot_learning.save(self.store, user_id=USER_ID, catalog=self.catalog, state=issued)
        update, context = self.chat_fixture(state=issued, text="synthetic incorrect written answer")
        update.update_id = 820001
        await self.chat_call(bot.handle_type_answer, update, context)
        before = self.profile()
        update.update_id = 820002
        await self.chat_call(bot.handle_type_answer, update, context)
        self.assertEqual(self.load()["block_pos"], 2)
        self.assertEqual(self.profile()["total_wrong"], before["total_wrong"] + 1,
                         "Deduplication does not suppress a genuine next Telegram update")

    async def test_pack_switch_does_not_reinterpret_native_written_answer_as_standalone(self):
        issued = self.block((0, 1), mode="type")
        issued.update(type_idx=0, block_typing=True)
        bot_learning.save(self.store, user_id=USER_ID, catalog=self.catalog, state=issued)
        french = self.catalog.require("fr-basics-100")
        self.store.activate_pack(USER_ID, pack_id=french.pack_id, language="fr", source="test")
        update, context = self.chat_fixture(state=issued, text="synthetic incorrect answer for old English card")
        update.update_id = 830001
        before = self.profile()
        french_word = self.catalog.words(french)[0]
        key = (USER_ID, french.storage_key, vocabulary_id_for(french_word))
        with self.store.Session() as session:
            self.assertIsNone(session.get(WordProgress, key))
        await self.chat_call(bot.handle_type_answer, update, context)
        self.assertEqual(self.profile(), before,
                         "An old native written answer cannot grade a different newly active pack")
        with self.store.Session() as session:
            self.assertIsNone(session.get(WordProgress, key))
        self.assertIsNone(context.user_data.get("type_idx"), "Pack changes clear old pending native typing")
        self.assertFalse(context.user_data.get("block_typing", False))


if __name__ == "__main__":
    unittest.main()
