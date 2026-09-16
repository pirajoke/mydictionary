"""Behavior contract for native Telegram quiz answer feedback."""

from copy import deepcopy
import os
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch


os.environ.setdefault("BOT_TOKEN", "123456:TESTTOKEN_ABCDEFGHIJKLMNOP")
os.environ.setdefault("ALLOWED_USER_ID", "1")
os.environ.setdefault("ALLOW_SQLITE_DEV", "true")

import bot
from mydictionary import bot_learning
from mydictionary.storage import DatabaseStore


USER_ID = 759102


class NativeQuizFeedbackBehaviorTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.pack = bot.CATALOG.require("en-basics-100")
        self.words = deepcopy(bot.CATALOG.words(self.pack))
        self.indices = [0, 1]

    def state(self, *, mode="quiz", indices=None, correct_count=0):
        selected = list(indices or self.indices)
        words = deepcopy(self.words)
        for word in words:
            word.setdefault("correct_count", 0)
        words[selected[0]]["correct_count"] = correct_count
        state = {"interface_locale": "en"}
        bot.reset_block_state(
            state,
            selected,
            self.pack.target_language,
            None,
            self.pack.pack_id,
            lesson_kind="review" if mode == "adaptive" else "practice",
        )
        bot.start_block_attempt(state, mode)
        return state, words

    def callback(self, state, *, idx=None, correct=True, data=None):
        current_idx = state["block_indices"][state["block_pos"]]
        idx = current_idx if idx is None else idx
        message = SimpleNamespace(chat_id=123, reply_text=AsyncMock())
        query = SimpleNamespace(
            data=data or (
                f"bquiz:{state['block_session']}:{idx}:{'1' if correct else '0'}"
            ),
            answer=AsyncMock(),
            edit_message_text=AsyncMock(),
            message=message,
        )
        update = SimpleNamespace(
            callback_query=query,
            effective_user=SimpleNamespace(id=USER_ID),
        )
        return update, SimpleNamespace(user_data=state), query, message

    async def run_accepted(self, *, mode, correct, final=False):
        indices = self.indices[:1] if final else self.indices
        state, words = self.state(
            mode=mode,
            indices=indices,
            correct_count=2 if mode == "adaptive" else 0,
        )
        idx = indices[0]
        update, context, query, message = self.callback(
            state, idx=idx, correct=correct,
        )
        expected_details = None
        with (
            patch.object(bot, "W", return_value=words),
            patch.object(bot, "active_content_pack", return_value=self.pack),
            patch.object(bot, "activate_block_language"),
            patch.object(bot, "persist_native_block", return_value=True),
            patch.object(bot, "record_product_event"),
            patch.object(bot, "send_pronunciation", new=AsyncMock()),
            patch.object(bot, "mark_correct", return_value=(10, 0)) as mark_correct,
            patch.object(bot, "mark_wrong", return_value=(2, 0)) as mark_wrong,
            patch.object(bot, "format_block_summary", return_value="SUMMARY"),
            patch.object(bot, "track_block_completion"),
            patch.object(bot, "track_lesson_completion"),
        ):
            expected_details = bot.format_word_details(idx, "en")
            expected_next_label = (
                bot.format_word_label(indices[1]) if len(indices) > 1 else None
            )
            await bot.block_quiz_cb.__wrapped__(update, context)

        return SimpleNamespace(
            state=state,
            idx=idx,
            query=query,
            message=message,
            expected_details=expected_details,
            expected_next_label=expected_next_label,
            mark_correct=mark_correct,
            mark_wrong=mark_wrong,
        )

    def assert_feedback(self, result, marker):
        result.query.edit_message_text.assert_awaited_once()
        payload = result.query.edit_message_text.await_args
        self.assertTrue(payload.args[0].startswith(marker))
        self.assertIn(result.expected_details, payload.args[0])
        self.assertIsNone(
            payload.kwargs.get("reply_markup"),
            "The answered question must not keep an active answer keyboard",
        )
        self.assertEqual(payload.kwargs.get("parse_mode"), "Markdown")

    async def test_ac1_ac3_ec1_correct_feedback_precedes_next_question(self):
        result = await self.run_accepted(mode="quiz", correct=True)

        result.query.answer.assert_awaited_once_with()
        self.assert_feedback(result, "✅")
        result.message.reply_text.assert_awaited_once()
        next_payload = result.message.reply_text.await_args
        self.assertIn(result.expected_next_label, next_payload.args[0])
        self.assertTrue(
            any(
                str(button.callback_data or "").startswith("bquiz:")
                for row in next_payload.kwargs["reply_markup"].inline_keyboard
                for button in row
            )
        )
        result.mark_correct.assert_called_once_with(result.idx)
        result.mark_wrong.assert_not_called()
        self.assertEqual(result.state["block_pos"], 1)

    async def test_ac2_ac3_ec1_incorrect_feedback_precedes_final_summary(self):
        result = await self.run_accepted(mode="quiz", correct=False, final=True)

        result.query.answer.assert_awaited_once_with()
        self.assert_feedback(result, "❌")
        result.message.reply_text.assert_awaited_once()
        self.assertEqual(result.message.reply_text.await_args.args[0], "SUMMARY")
        result.mark_wrong.assert_called_once_with(result.idx)
        result.mark_correct.assert_not_called()
        self.assertEqual(result.state["block_pos"], 1)

    async def test_ac4_adaptive_quiz_effective_question_uses_same_feedback_flow(self):
        result = await self.run_accepted(mode="adaptive", correct=True)

        result.query.answer.assert_awaited_once_with()
        self.assert_feedback(result, "✅")
        result.message.reply_text.assert_awaited_once()
        self.assertIn(
            result.expected_next_label,
            result.message.reply_text.await_args.args[0],
        )
        result.mark_correct.assert_called_once_with(result.idx)
        result.mark_wrong.assert_not_called()

    async def test_err1_invalid_callbacks_do_not_feedback_score_or_advance(self):
        cases = (
            ("stale", "bquiz:deadbeef:0:1", "quiz", 0),
            ("non-current", None, "quiz", 0),
            ("malformed", "bquiz:not-enough-parts", "quiz", 0),
            ("wrong-effective-mode", None, "adaptive", 3),
        )
        for label, data, mode, correct_count in cases:
            with self.subTest(case=label):
                state, words = self.state(mode=mode, correct_count=correct_count)
                callback_idx = (
                    self.indices[1] if label == "non-current" else self.indices[0]
                )
                update, context, query, message = self.callback(
                    state, idx=callback_idx, data=data,
                )
                before = deepcopy(state)
                with (
                    patch.object(bot, "W", return_value=words),
                    patch.object(bot, "block_advance", new=AsyncMock()) as advance,
                ):
                    await bot.block_quiz_cb.__wrapped__(update, context)

                query.answer.assert_awaited_once_with(
                    bot.BLOCK_STALE_TEXT, show_alert=True,
                )
                query.edit_message_text.assert_not_awaited()
                message.reply_text.assert_not_awaited()
                advance.assert_not_awaited()
                self.assertEqual(state, before)

    async def test_err2_rejected_durable_score_preserves_original_question(self):
        state, words = self.state(mode="quiz")
        idx = self.indices[0]
        update, context, query, message = self.callback(state, idx=idx, correct=True)
        store = object.__new__(DatabaseStore)
        runtime = bot.LearnerRuntime(
            user_id=USER_ID,
            store=store,
            progress={},
            words_by_lang={self.pack.pack_id: words},
        )
        token = bot._ACTIVE_RUNTIME.set(runtime)
        try:
            with (
                patch.object(bot, "W", return_value=words),
                patch.object(bot, "activate_block_language"),
                patch.object(
                    bot_learning,
                    "rate",
                    side_effect=bot_learning.BotLearningError("progress_changed"),
                ) as rate,
            ):
                await bot.block_quiz_cb.__wrapped__(update, context)
        finally:
            bot._ACTIVE_RUNTIME.reset(token)

        query.answer.assert_awaited_once_with()
        rate.assert_called_once()
        query.edit_message_text.assert_not_awaited()
        message.reply_text.assert_awaited_once()
        self.assertEqual(message.reply_text.await_args.args[0], bot.BLOCK_STALE_TEXT)
        self.assertEqual(state["block_pos"], 0)
        self.assertEqual(state["block_correct"], 0)
        self.assertEqual(state["block_wrong"], [])


if __name__ == "__main__":
    unittest.main()
