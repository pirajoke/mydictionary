"""Behavior contract for adaptive due-word review in Telegram chat."""

from copy import deepcopy
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

os.environ.setdefault("BOT_TOKEN", "123456:TESTTOKEN_ABCDEFGHIJKLMNOP")
os.environ.setdefault("ALLOWED_USER_ID", "1")
os.environ.setdefault("ALLOW_SQLITE_DEV", "true")

import bot
from mydictionary import bot_learning
from mydictionary.storage import DatabaseStore, User


USER_ID = 759101


def inline_buttons(markup):
    return [button for row in getattr(markup, "inline_keyboard", ()) for button in row]


class AdaptiveReviewBehaviorTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.pack = bot.CATALOG.require("en-basics-100")
        self.words = deepcopy(bot.CATALOG.words(self.pack))
        self.indices = list(range(4))

    def state(self, *, correct_counts=(0, 0, 0, 0)):
        words = deepcopy(self.words)
        for index, count in zip(self.indices, correct_counts):
            words[index]["correct_count"] = count
        state = {"interface_locale": "en"}
        bot.reset_block_state(
            state,
            self.indices,
            self.pack.target_language,
            None,
            self.pack.pack_id,
            lesson_kind="review",
        )
        bot.start_block_attempt(state, "adaptive")
        return state, words

    async def test_ac1_ac5_nonempty_review_starts_one_due_only_adaptive_attempt_and_event(self):
        message = SimpleNamespace(chat_id=123, reply_text=AsyncMock())
        context = SimpleNamespace(
            user_data={"interface_locale": "en"},
            bot=SimpleNamespace(send_message=AsyncMock()),
        )
        due = [1, 3]
        with (
            patch.object(bot, "active_content_pack", return_value=self.pack),
            patch.object(bot, "daily_lesson_size", return_value=5),
            patch.object(bot, "due_word_indices", return_value=due),
            patch.object(bot, "pick_block") as pick,
            patch.object(bot, "record_product_event") as record,
            patch.object(bot, "block_send_question_msg", new=AsyncMock()) as send,
        ):
            await bot.start_home_lesson(
                SimpleNamespace(message=message),
                context,
                lesson_kind="review",
                source="reply_keyboard",
            )

        pick.assert_not_called()
        self.assertEqual(context.user_data["block_indices"], due)
        self.assertEqual(context.user_data["block_all_indices"], due)
        self.assertEqual(context.user_data["block_mode"], "adaptive")
        self.assertEqual(context.user_data["lesson_kind"], "review")
        self.assertRegex(context.user_data["block_session"], r"^[0-9a-f]{8}$")
        send.assert_awaited_once_with(message, context)
        starts = {
            call.args[0]: call.kwargs.get("properties", {})
            for call in record.call_args_list
            if call.args[0] in {"lesson_started", "block_started", "block_mode_started"}
        }
        self.assertEqual(set(starts), {"lesson_started", "block_started", "block_mode_started"})
        self.assertEqual(starts["block_mode_started"]["mode"], "adaptive")
        self.assertTrue(all(payload["lesson_kind"] == "review" for payload in starts.values()))

    async def test_ac2_two_prior_correct_answers_render_four_choice_quiz(self):
        state, words = self.state(correct_counts=(2, 0, 0, 0))
        message = SimpleNamespace(chat_id=123, reply_text=AsyncMock())
        context = SimpleNamespace(user_data=state)
        with (
            patch.object(bot, "W", return_value=words),
            patch.object(bot, "active_content_pack", return_value=self.pack),
            patch.object(bot, "persist_native_block", return_value=True),
            patch.object(bot, "record_product_event"),
            patch.object(bot, "send_pronunciation", new=AsyncMock()),
        ):
            await bot.block_send_question_msg(message, context)

        message.reply_text.assert_awaited_once()
        payload = message.reply_text.await_args
        callbacks = [
            button.callback_data
            for button in inline_buttons(payload.kwargs["reply_markup"])
            if str(button.callback_data or "").startswith("bquiz:")
        ]
        self.assertEqual(len(callbacks), 4)
        self.assertTrue(all(f":{self.indices[0]}:" in callback for callback in callbacks))
        self.assertFalse(state["block_typing"])
        self.assertIsNone(state["type_idx"])

    async def test_ac2_three_prior_correct_answers_render_written_recall(self):
        state, words = self.state(correct_counts=(3, 0, 0, 0))
        message = SimpleNamespace(chat_id=123, reply_text=AsyncMock())
        context = SimpleNamespace(user_data=state)
        with (
            patch.object(bot, "W", return_value=words),
            patch.object(bot, "active_content_pack", return_value=self.pack),
            patch.object(bot, "persist_native_block", return_value=True),
            patch.object(bot, "record_product_event"),
            patch.object(bot, "send_pronunciation", new=AsyncMock()),
        ):
            await bot.block_send_question_msg(message, context)

        message.reply_text.assert_awaited_once()
        payload = message.reply_text.await_args
        self.assertIn(bot.translate("block_written_prompt", "en"), payload.args[0])
        callbacks = [button.callback_data for button in inline_buttons(payload.kwargs["reply_markup"])]
        self.assertFalse(any(str(callback or "").startswith("bquiz:") for callback in callbacks))
        self.assertTrue(state["block_typing"])
        self.assertEqual(state["type_idx"], self.indices[0])

    async def test_ac3_valid_adaptive_quiz_callback_scores_and_continues(self):
        state, words = self.state(correct_counts=(2, 0, 0, 0))
        session_id = state["block_session"]
        idx = self.indices[0]
        query = SimpleNamespace(
            data=f"bquiz:{session_id}:{idx}:1",
            answer=AsyncMock(),
            edit_message_text=AsyncMock(),
            message=SimpleNamespace(chat_id=123, reply_text=AsyncMock()),
        )
        update = SimpleNamespace(callback_query=query, effective_user=SimpleNamespace(id=USER_ID))
        context = SimpleNamespace(user_data=state)

        async def advance(_query, _context, accepted_idx, correct):
            self.assertEqual((accepted_idx, correct), (idx, True))
            state["block_pos"] += 1
            return True

        with (
            patch.object(bot, "W", return_value=words),
            patch.object(bot, "block_advance", new=AsyncMock(side_effect=advance)) as score,
        ):
            await bot.block_quiz_cb.__wrapped__(update, context)

        query.answer.assert_awaited_once_with()
        score.assert_awaited_once_with(query, context, idx, True)
        self.assertEqual(state["block_pos"], 1)

    async def test_ac3_valid_adaptive_written_answer_scores_and_continues(self):
        state, words = self.state(correct_counts=(3, 0, 0, 0))
        state["block_typing"] = True
        state["type_idx"] = self.indices[0]
        idx = self.indices[0]
        answer = str(words[idx]["meaning"])
        message = SimpleNamespace(chat_id=123, text=answer, reply_text=AsyncMock())
        update = SimpleNamespace(
            update_id=910001,
            message=message,
            effective_user=SimpleNamespace(id=USER_ID, language_code="en"),
        )
        context = SimpleNamespace(user_data=state)

        async def advance(_message, _context, accepted_idx, correct, *, on_accepted):
            self.assertEqual((accepted_idx, correct), (idx, True))
            self.assertEqual(state.get("native_answer_update_id"), update.update_id)
            state["block_pos"] += 1
            state["block_typing"] = False
            state["type_idx"] = None
            await on_accepted()
            await bot.block_send_question_msg(_message, _context)
            return True

        with (
            patch.object(bot, "W", return_value=words),
            patch.object(bot, "active_content_pack", return_value=self.pack),
            patch.object(bot, "block_advance", new=AsyncMock(side_effect=advance)) as score,
            patch.object(bot, "send_pronunciation", new_callable=AsyncMock),
        ):
            await bot.handle_type_answer.__wrapped__(update, context)

        score.assert_awaited_once()
        self.assertEqual(state["block_pos"], 1)
        self.assertFalse(state["block_typing"])
        self.assertIsNone(state["type_idx"])
        self.assertEqual(
            message.reply_text.await_count,
            2,
            "Accepted written recall must render the next adaptive question",
        )

    async def test_ac3_adaptive_written_free_text_dispatches_to_answer_not_mirror(self):
        state, _words = self.state(correct_counts=(3, 0, 0, 0))
        state["block_typing"] = True
        state["type_idx"] = self.indices[0]
        message = SimpleNamespace(chat_id=123, text="synthetic written answer", reply_text=AsyncMock())
        update = SimpleNamespace(
            message=message,
            effective_message=message,
            effective_chat=SimpleNamespace(id=123, type="private"),
            effective_user=SimpleNamespace(id=USER_ID, language_code="en"),
        )
        context = SimpleNamespace(user_data=state)
        written_answer = AsyncMock()
        mirror = AsyncMock()

        with (
            patch.object(bot, "handle_type_answer", new=written_answer),
            patch.object(bot, "handle_mirror_question", new=mirror),
        ):
            await bot.mirror_text_handler.__wrapped__(update, context)

        self.assertEqual(
            (written_answer.await_count, mirror.await_count),
            (1, 0),
            "Adaptive written recall must outrank the Mirror fallback",
        )
        written_answer.assert_awaited_once_with(update, context)

    def test_ac3_adaptive_attempt_reuses_atomic_srs_and_xp_advancement(self):
        temp = tempfile.TemporaryDirectory(prefix="adaptive-review-rate-")
        store = DatabaseStore(f"sqlite:///{Path(temp.name) / 'learning.sqlite3'}")
        try:
            store.ensure_user_id(USER_ID)
            with store.Session.begin() as session:
                user = session.get(User, USER_ID)
                user.access_status = user.privacy_status = "active"
                user.native_language = "ru"
                user.interface_locale = "en"
            store.activate_pack(
                USER_ID,
                pack_id=self.pack.pack_id,
                language=self.pack.target_language,
                source="test",
            )
            state, _words = self.state(correct_counts=(2, 3, 0, 0))
            bot_learning.save(store, user_id=USER_ID, catalog=bot.CATALOG, state=state)

            first = bot_learning.rate(
                store,
                user_id=USER_ID,
                catalog=bot.CATALOG,
                state=state,
                word_index=self.indices[0],
                knew=True,
            )
            second = bot_learning.rate(
                store,
                user_id=USER_ID,
                catalog=bot.CATALOG,
                state=first["state"],
                word_index=self.indices[1],
                knew=False,
            )

            self.assertEqual(second["state"]["block_mode"], "adaptive")
            self.assertEqual(second["state"]["block_pos"], 2)
            self.assertEqual(second["state"]["block_correct"], 1)
            self.assertEqual(second["state"]["block_wrong"], [self.indices[1]])
            self.assertEqual(second["profile"]["total_correct"], 1)
            self.assertEqual(second["profile"]["total_wrong"], 1)
            self.assertGreaterEqual(second["profile"]["xp"], 12)
        finally:
            store.close()
            temp.cleanup()

    async def test_ac4_adaptive_state_survives_restore_and_retry_preserves_mode(self):
        temp = tempfile.TemporaryDirectory(prefix="adaptive-review-")
        store = DatabaseStore(f"sqlite:///{Path(temp.name) / 'learning.sqlite3'}")
        try:
            store.ensure_user_id(USER_ID)
            with store.Session.begin() as session:
                user = session.get(User, USER_ID)
                user.access_status = user.privacy_status = "active"
                user.native_language = "ru"
                user.interface_locale = "en"
            store.activate_pack(
                USER_ID,
                pack_id=self.pack.pack_id,
                language=self.pack.target_language,
                source="test",
            )
            state, _words = self.state(correct_counts=(2, 3, 0, 0))
            bot_learning.save(store, user_id=USER_ID, catalog=bot.CATALOG, state=state)
            store.close()
            store = DatabaseStore(f"sqlite:///{Path(temp.name) / 'learning.sqlite3'}", migrate=False)
            restored = bot_learning.load(store, user_id=USER_ID, catalog=bot.CATALOG)
            self.assertIsNotNone(restored)
            self.assertEqual(restored["block_mode"], "adaptive")

            restored["block_pos"] = len(restored["block_indices"])
            restored["block_correct"] = len(restored["block_indices"]) - 2
            restored["block_wrong"] = restored["block_indices"][:2]
            previous_session = restored["block_session"]
            query = SimpleNamespace(
                data=f"bretry:{previous_session}",
                answer=AsyncMock(),
                message=SimpleNamespace(chat_id=123, reply_text=AsyncMock()),
                edit_message_text=AsyncMock(),
            )
            update = SimpleNamespace(callback_query=query, effective_user=SimpleNamespace(id=USER_ID))
            context = SimpleNamespace(user_data=restored)
            with (
                patch.object(bot, "active_content_pack", return_value=self.pack),
                patch.object(bot, "record_product_event"),
                patch.object(bot, "block_send_question", new=AsyncMock()) as send,
            ):
                await bot.block_retry_cb.__wrapped__(update, context)

            self.assertEqual(restored["block_mode"], "adaptive")
            self.assertEqual(restored["block_indices"], self.indices[:2])
            self.assertNotEqual(restored["block_session"], previous_session)
            send.assert_awaited_once_with(query, context)
        finally:
            store.close()
            temp.cleanup()

    async def test_ec1_empty_due_queue_keeps_localized_response_without_block(self):
        message = SimpleNamespace(chat_id=123, reply_text=AsyncMock())
        context = SimpleNamespace(
            user_data={"interface_locale": "en"},
            bot=SimpleNamespace(send_message=AsyncMock()),
        )
        with (
            patch.object(bot, "active_content_pack", return_value=self.pack),
            patch.object(bot, "daily_lesson_size", return_value=5),
            patch.object(bot, "due_word_indices", return_value=[]),
            patch.object(bot, "record_product_event") as record,
        ):
            await bot.start_home_lesson(
                SimpleNamespace(message=message), context, lesson_kind="review"
            )

        payload = context.bot.send_message.await_args.kwargs
        self.assertEqual(payload["text"], bot.translate("review_empty", "en"))
        self.assertEqual(
            payload["reply_markup"].inline_keyboard[0][0].callback_data,
            "start:daily",
        )
        self.assertFalse(context.user_data.get("block_session"))
        record.assert_called_once_with(
            "review_empty",
            properties={"pack_id": self.pack.pack_id, "language": self.pack.target_language},
        )

    async def test_ec2_daily_continue_and_manual_modes_keep_existing_behavior(self):
        message = SimpleNamespace(chat_id=123, reply_text=AsyncMock())
        context = SimpleNamespace(
            user_data={"interface_locale": "en"},
            bot=SimpleNamespace(send_message=AsyncMock()),
        )
        with (
            patch.object(bot, "active_content_pack", return_value=self.pack),
            patch.object(bot, "daily_lesson_size", return_value=4),
            patch.object(bot, "pick_block", return_value=self.indices),
            patch.object(bot, "record_product_event"),
            patch.object(bot, "block_send_question_msg", new=AsyncMock()) as send,
        ):
            await bot.start_home_lesson(
                SimpleNamespace(message=message), context, lesson_kind="daily"
            )
        self.assertEqual(context.user_data["block_mode"], "flash")
        send.assert_awaited_once_with(message, context)

        with patch.object(bot, "block_send_question_msg", new=AsyncMock()) as resume:
            await bot.continue_or_start_lesson(message, context)
        self.assertEqual(context.user_data["block_mode"], "flash")
        resume.assert_awaited_once_with(message, context)

        for mode in ("flash", "quiz", "type"):
            with self.subTest(mode=mode):
                state = {"interface_locale": "en"}
                bot.reset_block_state(
                    state,
                    self.indices,
                    self.pack.target_language,
                    None,
                    self.pack.pack_id,
                    lesson_kind="practice",
                )
                old_session = state["block_session"]
                query = SimpleNamespace(
                    data=f"bmode:{old_session}:{mode}",
                    answer=AsyncMock(),
                    message=SimpleNamespace(chat_id=123, reply_text=AsyncMock()),
                    edit_message_text=AsyncMock(),
                )
                update = SimpleNamespace(callback_query=query, effective_user=SimpleNamespace(id=USER_ID))
                mode_context = SimpleNamespace(user_data=state)
                with (
                    patch.object(bot, "active_content_pack", return_value=self.pack),
                    patch.object(bot, "record_product_event"),
                    patch.object(bot, "block_send_question", new=AsyncMock()) as render,
                ):
                    await bot.block_mode_cb.__wrapped__(update, mode_context)
                self.assertEqual(state["block_mode"], mode)
                render.assert_awaited_once_with(query, mode_context)

    async def test_err1_invalid_adaptive_quiz_callbacks_do_not_score_or_advance(self):
        cases = (
            ("stale", "deadbeef", self.indices[0], (2, 0, 0, 0)),
            ("wrong-word", None, self.indices[1], (2, 0, 0, 0)),
            ("wrong-effective-mode", None, self.indices[0], (3, 0, 0, 0)),
        )
        for label, supplied_session, callback_idx, counts in cases:
            with self.subTest(case=label):
                state, words = self.state(correct_counts=counts)
                before = deepcopy(state)
                session_id = supplied_session or state["block_session"]
                query = SimpleNamespace(
                    data=f"bquiz:{session_id}:{callback_idx}:1",
                    answer=AsyncMock(),
                    edit_message_text=AsyncMock(),
                    message=SimpleNamespace(chat_id=123, reply_text=AsyncMock()),
                )
                update = SimpleNamespace(callback_query=query, effective_user=SimpleNamespace(id=USER_ID))
                context = SimpleNamespace(user_data=state)
                with (
                    patch.object(bot, "W", return_value=words),
                    patch.object(bot, "block_advance", new_callable=AsyncMock) as score,
                ):
                    await bot.block_quiz_cb.__wrapped__(update, context)
                score.assert_not_awaited()
                self.assertEqual(state, before)
                query.answer.assert_awaited_once_with(bot.BLOCK_STALE_TEXT, show_alert=True)

    async def test_err1_forged_adaptive_mode_selection_is_rejected_without_mutation(self):
        state = {"interface_locale": "en"}
        bot.reset_block_state(
            state,
            self.indices,
            self.pack.target_language,
            None,
            self.pack.pack_id,
            lesson_kind="practice",
        )
        before = deepcopy(state)
        query = SimpleNamespace(
            data=f"bmode:{state['block_session']}:adaptive",
            answer=AsyncMock(),
            message=SimpleNamespace(chat_id=123, reply_text=AsyncMock()),
            edit_message_text=AsyncMock(),
        )
        update = SimpleNamespace(
            callback_query=query,
            effective_user=SimpleNamespace(id=USER_ID, language_code="en"),
        )
        context = SimpleNamespace(user_data=state)

        with patch.object(bot, "block_send_question", new_callable=AsyncMock) as render:
            await bot.block_mode_cb.__wrapped__(update, context)

        query.answer.assert_awaited_once_with(bot.BLOCK_STALE_TEXT, show_alert=True)
        render.assert_not_awaited()
        self.assertEqual(state, before)


if __name__ == "__main__":
    unittest.main()
