import os
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, MagicMock, patch


os.environ.setdefault("BOT_TOKEN", "123456:TESTTOKEN")
os.environ.setdefault("ALLOWED_USER_ID", "1")
os.environ.setdefault("ALLOW_SQLITE_DEV", "true")

import bot
from mydictionary.localization import translate


def ai_settings(*, enabled: bool) -> SimpleNamespace:
    return SimpleNamespace(
        enabled=enabled,
        initial_credits=40,
        consent_version="ai-processing-test-v1",
        processing_notice="AI processing test notice.",
    )


class TutorSurface:
    def __init__(self, *, locale: str = "fr", user_id: int = 731):
        self.user_data = {"interface_locale": locale}
        bot.reset_block_state(
            self.user_data,
            list(range(10)),
            "ja",
            "food",
            pack_id="ja-basics-100",
        )
        self.session = self.user_data["block_session"]
        self.message = SimpleNamespace(
            chat_id=user_id,
            reply_text=AsyncMock(),
        )
        self.query = SimpleNamespace(
            data="",
            answer=AsyncMock(),
            edit_message_text=AsyncMock(),
            message=self.message,
        )
        self.update = SimpleNamespace(
            callback_query=self.query,
            message=self.message,
            effective_message=self.message,
            effective_user=SimpleNamespace(
                id=user_id,
                language_code=locale,
                first_name=None,
            ),
            effective_chat=SimpleNamespace(id=user_id),
        )
        self.context = SimpleNamespace(
            user_data=self.user_data,
            args=[],
            bot=SimpleNamespace(),
        )

    def select(self, action: str) -> None:
        self.query.data = f"bait:{self.session}:{action}"


SNAPSHOT = {
    "has_progress": True,
    "language": "ja",
    "accuracy_percent": 74,
    "lifetime_accuracy_percent": 74,
    "lifetime_correct": 23,
    "lifetime_wrong": 8,
    "tracked_words": 12,
    "learned_words": 4,
    "due_count": 3,
    "due_reviews": 3,
    "streak": 2,
    "streak_days": 2,
    "weak_terms": [
        {"term": "猫", "correct": 1, "wrong": 4},
        {"term": "犬", "correct": 0, "wrong": 2},
    ],
}

BAR_CELLS = frozenset("█▓▒░■□●○▰▱🟩⬜🟧⬛")


def has_ten_cell_progress_bar(text: str) -> bool:
    for line in text.replace("\ufe0f", "").splitlines():
        if len([character for character in line if character in BAR_CELLS]) == 10:
            return True
    return False


def callback_data_from_reply(message) -> list[str]:
    markup = message.reply_text.await_args.kwargs["reply_markup"]
    return [
        button.callback_data
        for row in markup.inline_keyboard
        for button in row
    ]


class DeterministicLearningStatsCardsTest(unittest.IsolatedAsyncioTestCase):
    async def invoke(
        self,
        action: str,
        *,
        snapshot: dict = SNAPSHOT,
        locale: str = "fr",
        ai_enabled: bool = True,
    ):
        surface = TutorSurface(locale=locale)
        surface.select(action)
        store = MagicMock()
        snapshot_reader = MagicMock(return_value=snapshot)
        compact_ai = AsyncMock()
        mirror_ai = AsyncMock()
        with (
            patch.object(bot, "AI_SETTINGS", ai_settings(enabled=ai_enabled)),
            patch.object(bot, "get_store", return_value=store),
            patch.object(
                bot,
                "grounded_progress_snapshot",
                new=snapshot_reader,
            ),
            patch.object(
                bot,
                "request_compact_learning_companion",
                new=compact_ai,
            ),
            patch.object(bot, "handle_mirror_question", new=mirror_ai),
            patch.object(bot, "get_ai_tutor_service") as ai_service,
        ):
            await bot.block_ai_action_cb.__wrapped__(
                surface.update,
                surface.context,
            )
        return surface, store, snapshot_reader, compact_ai, mirror_ai, ai_service

    async def test_ac1_ac6_statistics_actions_are_free_even_when_ai_is_disabled(self):
        for action in ("vocabulary", "mistakes", "progress"):
            with self.subTest(action=action):
                (
                    surface,
                    store,
                    snapshot_reader,
                    compact_ai,
                    mirror_ai,
                    ai_service,
                ) = await self.invoke(action, ai_enabled=False)

                surface.query.answer.assert_awaited_once_with()
                surface.message.reply_text.assert_awaited_once()
                snapshot_reader.assert_called_once_with(
                    store,
                    surface.update.effective_user.id,
                )
                store.has_consent.assert_not_called()
                store.reserve_ai_usage.assert_not_called()
                store.ai_usage_summary.assert_not_called()
                compact_ai.assert_not_awaited()
                mirror_ai.assert_not_awaited()
                ai_service.assert_not_called()

    async def test_ac2_ac5_each_action_renders_a_distinct_localized_gamified_card(self):
        expected = {
            "vocabulary": {
                "heading": "vocabulaire",
                "icon": "📚",
                "facts": ("12", "4", "3", "猫", "犬"),
            },
            "mistakes": {
                "heading": "erreurs",
                "icon": "🎯",
                "facts": ("23", "8", "74", "猫", "犬"),
            },
            "progress": {
                "heading": "progrès",
                "icon": "📈",
                "facts": ("74", "12", "4", "3", "2"),
            },
        }
        rendered_cards = {}
        for action, contract in expected.items():
            with self.subTest(action=action):
                surface, *_dependencies = await self.invoke(action)
                surface.message.reply_text.assert_awaited_once()
                text = surface.message.reply_text.await_args.args[0]
                rendered_cards[action] = text

                self.assertIn(contract["icon"], text)
                self.assertIn(contract["heading"], text.casefold())
                self.assertTrue(has_ten_cell_progress_bar(text), text)
                for fact in contract["facts"]:
                    self.assertIn(fact, text)
                self.assertLessEqual(len(text), 600)
                self.assertNotIn("1. 2.", text)
                self.assertNotIn("Faits mesurés", text)
                self.assertEqual(
                    callback_data_from_reply(surface.message),
                    ["start:review", "start:daily"],
                )
                markup = surface.message.reply_text.await_args.kwargs["reply_markup"]
                labels = [
                    button.text
                    for row in markup.inline_keyboard
                    for button in row
                ]
                self.assertEqual(
                    labels,
                    [translate("start_review", "fr"), translate("start_daily", "fr")],
                )

        self.assertEqual(len(set(rendered_cards.values())), 3)

    async def test_ec2_empty_history_is_safe_and_starts_the_first_lesson(self):
        empty = {"has_progress": False, "active_pack_id": "PRIVATE-pack-id"}
        for action in ("vocabulary", "mistakes", "progress"):
            with self.subTest(action=action):
                surface, store, snapshot_reader, compact_ai, mirror_ai, ai_service = (
                    await self.invoke(action, snapshot=empty, locale="ru", ai_enabled=False)
                )
                surface.message.reply_text.assert_awaited_once()
                text = surface.message.reply_text.await_args.args[0]

                self.assertTrue(text.strip())
                self.assertLessEqual(len(text), 300)
                self.assertNotIn("PRIVATE-pack-id", text)
                self.assertNotIn("100%", text)
                self.assertEqual(
                    callback_data_from_reply(surface.message),
                    ["start:daily"],
                )
                snapshot_reader.assert_called_once_with(
                    store,
                    surface.update.effective_user.id,
                )
                compact_ai.assert_not_awaited()
                mirror_ai.assert_not_awaited()
                ai_service.assert_not_called()

    async def test_ac6_explicit_ask_action_remains_ai_gated_when_ai_is_disabled(self):
        surface, store, snapshot_reader, compact_ai, mirror_ai, ai_service = (
            await self.invoke("ask", ai_enabled=False)
        )

        surface.query.answer.assert_awaited_once_with(
            translate("ai_disabled", "fr"),
            show_alert=True,
        )
        surface.message.reply_text.assert_not_awaited()
        snapshot_reader.assert_not_called()
        store.has_consent.assert_not_called()
        store.reserve_ai_usage.assert_not_called()
        compact_ai.assert_not_awaited()
        mirror_ai.assert_not_awaited()
        ai_service.assert_not_called()

    def test_ac3_progress_focus_uses_due_then_weak_then_daily_priority(self):
        cases = (
            (
                {**SNAPSHOT, "due_count": 3, "due_reviews": 3},
                translate("learning_stats_focus_due", "fr", count=3),
            ),
            (
                {**SNAPSHOT, "due_count": 0, "due_reviews": 0},
                translate("learning_stats_focus_weak", "fr"),
            ),
            (
                {
                    **SNAPSHOT,
                    "due_count": 0,
                    "due_reviews": 0,
                    "weak_terms": [],
                },
                translate("learning_stats_focus_daily", "fr"),
            ),
        )
        for snapshot, expected_focus in cases:
            with self.subTest(expected_focus=expected_focus):
                text = bot.render_learning_stats_card(
                    "progress", snapshot, locale="fr"
                )
                self.assertIn(expected_focus, text)

    def test_ac4_weak_terms_are_bounded_deduplicated_and_safe(self):
        long_term = "extraordinairement-long-terme"
        snapshot = {
            **SNAPSHOT,
            "weak_terms": [
                {"term": "chat"},
                {"term": "chat"},
                {"term": long_term},
                {"term": 42},
                {"term": "chien"},
                {"term": "oiseau"},
            ],
        }
        text = bot.render_learning_stats_card(
            "vocabulary", snapshot, locale="fr"
        )

        self.assertEqual(text.count("chat"), 1)
        self.assertIn(long_term[:24], text)
        self.assertNotIn(long_term, text)
        self.assertIn("chien", text)
        self.assertNotIn("oiseau", text)
        self.assertNotIn("42", text)

    def test_ec1_malformed_snapshot_values_render_safe_placeholders(self):
        malformed = {
            "has_progress": True,
            "accuracy_percent": True,
            "lifetime_correct": "not-a-number",
            "lifetime_wrong": -3,
            "tracked_words": None,
            "learned_words": object(),
            "due_count": float("inf"),
            "streak": False,
            "weak_terms": [{"term": {"private": "value"}}],
        }
        for action in ("vocabulary", "mistakes", "progress"):
            with self.subTest(action=action):
                text = bot.render_learning_stats_card(
                    action, malformed, locale="ru"
                )
                self.assertTrue(has_ten_cell_progress_bar(text), text)
                self.assertNotIn("not-a-number", text)
                self.assertNotIn("private", text)
                self.assertNotIn("100%", text)
                self.assertLessEqual(len(text), 600)

    async def test_err1_invalid_callbacks_do_not_read_statistics_storage(self):
        for callback in (
            "bait:malformed",
            "bait:too:many:parts:progress",
            "bait:stale-session:progress",
        ):
            with self.subTest(callback=callback):
                surface = TutorSurface(locale="ru")
                surface.query.data = callback
                store = MagicMock()
                snapshot_reader = MagicMock()
                with (
                    patch.object(bot, "AI_SETTINGS", ai_settings(enabled=True)),
                    patch.object(bot, "get_store", return_value=store) as get_store,
                    patch.object(
                        bot,
                        "grounded_progress_snapshot",
                        new=snapshot_reader,
                    ),
                ):
                    await bot.block_ai_action_cb.__wrapped__(
                        surface.update, surface.context
                    )

                surface.query.answer.assert_awaited_once()
                get_store.assert_not_called()
                snapshot_reader.assert_not_called()
                surface.message.reply_text.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
