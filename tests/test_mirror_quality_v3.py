import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from alembic import command
from alembic.config import Config
from sqlalchemy import func, inspect, select, text

import bot
from mydictionary import ai_tutor, mirror_assistant, privacy, storage
from mydictionary.privacy import erase_user_learning_data
from mydictionary.storage import DatabaseStore
from tests.test_mirror_assistant import (
    AI_CONSENT_VERSION,
    admitted_profile,
    invoke_handler,
    mirror_profile,
    text_update,
)


def required(testcase, owner, name):
    testcase.assertTrue(hasattr(owner, name), f"missing public behavior: {name}")
    return getattr(owner, name)


class MirrorNaturalReplyContractTest(unittest.TestCase):
    def test_ac_01_plain_reply_has_no_report_chrome_or_credit_footer(self):
        answer = ai_tutor.parse_mirror_answer(
            {
                "answer_ru": (
                    "Привет! Можем продолжить французский или просто поговорить "
                    "о том, что сейчас непонятно."
                ),
                "language_items": [],
                "examples": [],
                "next_step_ru": "",
            }
        )

        rendered = ai_tutor.render_mirror_answer(answer, available_credits=39)

        self.assertEqual(rendered, answer.answer_ru)
        self.assertNotIn("AI-кредиты", rendered)
        self.assertNotIn("🇷🇺", rendered)
        self.assertNotIn("Следующий шаг:", rendered)

    def test_ac_02_language_detail_is_compact_and_keeps_ambiguous_meanings(self):
        answer = ai_tutor.parse_mirror_answer(
            {
                "answer_ru": "Bonjour зависит от ситуации общения.",
                "language_items": [
                    {
                        "target": "bonjour",
                        "transcription": "/bɔ̃.ʒuʁ/",
                        "meaning_ru": "здравствуйте; добрый день",
                        "note_ru": "Нейтральное дневное приветствие.",
                    }
                ],
                "examples": [
                    {
                        "target": "Bonjour, Marie !",
                        "transcription": "/bɔ̃.ʒuʁ ma.ʁi/",
                        "russian": "Добрый день, Мари!",
                    }
                ],
                "next_step_ru": "Сравни его с более разговорным salut.",
            }
        )

        rendered = ai_tutor.render_mirror_answer(answer, available_credits=39)

        self.assertTrue(rendered.startswith("Bonjour зависит"))
        self.assertIn("bonjour /bɔ̃.ʒuʁ/ — здравствуйте; добрый день", rendered)
        self.assertIn("Нейтральное дневное приветствие.", rendered)
        self.assertIn("Bonjour, Marie ! /bɔ̃.ʒuʁ ma.ʁi/ — Добрый день, Мари!", rendered)
        self.assertIn("Сравни его с более разговорным salut.", rendered)
        self.assertNotIn("Значение:", rendered)
        self.assertNotIn("Транскрипция:", rendered)
        self.assertNotIn("AI-кредиты", rendered)

    def test_ac_04_payload_contains_style_and_latest_twenty_turns(self):
        turns = [
            {"role": "user" if index % 2 == 0 else "assistant", "text": f"turn {index}"}
            for index in range(24)
        ]

        payload = mirror_assistant.build_mirror_provider_payload(
            question="А чем отличается salut?",
            admin_guidance="Отвечай живо и точно как преподаватель языка.",
            grounded_snapshot={"language": "fr", "has_progress": True},
            learning_context={"language": "fr", "words": []},
            recent_dialogue=turns,
            response_style="conversation",
        )

        self.assertEqual(payload["response_style"], "conversation")
        self.assertEqual(len(payload["recent_dialogue"]), 20)
        self.assertEqual(payload["recent_dialogue"][0]["text"], "turn 4")
        self.assertEqual(payload["recent_dialogue"][-1]["text"], "turn 23")


class MirrorMemorySettingsContractTest(unittest.TestCase):
    def test_ac_06_memory_is_off_by_default_and_requires_current_consent(self):
        settings_type = required(
            self, mirror_assistant, "MirrorMemorySettings"
        )

        disabled = settings_type.from_env({}, ai_consent_version=None)
        self.assertFalse(disabled.enabled)
        self.assertEqual(disabled.retention_days, 7)

        with self.assertRaises(ValueError):
            settings_type.from_env(
                {"MIRROR_MEMORY_ENABLED": "true"}, ai_consent_version=None
            )

        enabled = settings_type.from_env(
            {
                "MIRROR_MEMORY_ENABLED": "true",
                "MIRROR_DIALOGUE_RETENTION_DAYS": "5",
            },
            ai_consent_version="ai-processing-memory-v1",
        )
        self.assertTrue(enabled.enabled)
        self.assertEqual(enabled.retention_days, 5)

    def test_err_01_memory_config_rejects_invalid_values(self):
        settings_type = required(
            self, mirror_assistant, "MirrorMemorySettings"
        )
        for values in (
            {"MIRROR_MEMORY_ENABLED": "sometimes"},
            {"MIRROR_DIALOGUE_RETENTION_DAYS": "0"},
            {"MIRROR_DIALOGUE_RETENTION_DAYS": "31"},
        ):
            with self.subTest(values=values), self.assertRaises(ValueError):
                settings_type.from_env(values, ai_consent_version="v1")


class MirrorPersistentContextContractTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="mirror-quality-v3-")
        self.database_url = f"sqlite:///{self.temporary.name}/mirror.sqlite3"
        self.store = DatabaseStore(self.database_url)
        self.now = datetime(2026, 8, 11, 12, 0, tzinfo=timezone.utc)

    def tearDown(self):
        self.store.close()
        self.temporary.cleanup()

    def test_ac_03_style_defaults_persists_and_is_user_isolated(self):
        get_style = required(self, self.store, "get_mirror_style")
        set_style = required(self, self.store, "set_mirror_style")
        self.store.ensure_user_id(701)
        self.store.ensure_user_id(702)

        self.assertEqual(get_style(701), "teacher")
        self.assertEqual(set_style(701, "conversation"), "conversation")
        self.assertEqual(get_style(701), "conversation")
        self.assertEqual(get_style(702), "teacher")
        with self.assertRaises(ValueError):
            set_style(701, "unbounded")

    def test_ac_05_memory_survives_restart_and_returns_latest_unexpired_twenty(self):
        append_exchange = required(self, self.store, "append_mirror_exchange")
        get_dialogue = required(self, self.store, "get_mirror_dialogue")
        for index in range(12):
            append_exchange(
                703,
                question=f"question {index}",
                answer=f"answer {index}",
                retention_days=7,
                now=self.now + timedelta(minutes=index),
            )

        self.store.close()
        self.store = DatabaseStore(self.database_url, migrate=False)
        dialogue = self.store.get_mirror_dialogue(703, limit=20, now=self.now)

        self.assertEqual(len(dialogue), 20)
        self.assertEqual(dialogue[0], {"role": "user", "text": "question 2"})
        self.assertEqual(dialogue[-1], {"role": "assistant", "text": "answer 11"})
        with self.store.Session() as session:
            stored_turns = session.scalar(
                select(func.count()).select_from(storage.MirrorDialogueTurn)
            )
        self.assertEqual(stored_turns, 20)
        self.assertEqual(
            self.store.get_mirror_dialogue(
                703, limit=20, now=self.now + timedelta(days=8)
            ),
            [],
        )

    def test_ec_01_memory_is_user_isolated_and_bounds_text(self):
        append_exchange = required(self, self.store, "append_mirror_exchange")
        append_exchange(
            704,
            question=" q ",
            answer=" a " * 1000,
            retention_days=7,
            now=self.now,
        )
        self.store.ensure_user_id(705)

        first = self.store.get_mirror_dialogue(704, limit=20, now=self.now)
        second = self.store.get_mirror_dialogue(705, limit=20, now=self.now)

        self.assertEqual(first[0], {"role": "user", "text": "q"})
        self.assertLessEqual(len(first[1]["text"]), 500)
        self.assertEqual(second, [])

    def test_ac_07_privacy_erasure_deletes_dialogue_and_resets_style(self):
        self.store.set_mirror_style(706, "brief")
        self.store.append_mirror_exchange(
            706,
            question="private question",
            answer="private answer",
            retention_days=7,
            now=self.now,
        )

        erase_user_learning_data(self.store, user_id=706, actor="self-service")

        self.assertEqual(self.store.get_mirror_style(706), "teacher")
        self.assertEqual(self.store.get_mirror_dialogue(706, now=self.now), [])

    def test_ac_07_retention_reports_and_deletes_expired_dialogue(self):
        turn_model = required(self, storage, "MirrorDialogueTurn")
        self.store.append_mirror_exchange(
            707,
            question="expired question",
            answer="expired answer",
            retention_days=1,
            now=self.now - timedelta(days=2),
        )
        policy = privacy.RetentionPolicy.from_env({})

        report = privacy.retention_report(self.store, policy, now=self.now)
        self.assertEqual(report.mirror_dialogue_turns, 2)
        applied = privacy.apply_retention(self.store, policy, now=self.now)
        self.assertEqual(applied.mirror_dialogue_turns, 2)
        with self.store.Session() as session:
            remaining = session.scalar(select(func.count()).select_from(turn_model))
        self.assertEqual(remaining, 0)

    def test_ac_07_migration_head_contains_style_and_dialogue_table(self):
        columns = {item["name"] for item in inspect(self.store.engine).get_columns("users")}
        self.assertIn("mirror_style", columns)
        self.assertIn("mirror_dialogue_turns", inspect(self.store.engine).get_table_names())
        with self.store.engine.connect() as connection:
            revision = connection.execute(
                text("select version_num from alembic_version")
            ).scalar_one()
        self.assertEqual(revision, "0015_mirror_quality_v3")

    def test_ac_07_migration_upgrade_downgrade_roundtrip(self):
        self.store.close()
        root = Path(__file__).resolve().parents[1]
        config = Config(str(root / "alembic.ini"))
        config.attributes["configure_logging"] = False
        config.set_main_option("script_location", str(root / "migrations"))
        config.set_main_option("sqlalchemy.url", self.database_url)

        command.downgrade(config, "0014_mirror_assistant_v1")
        downgraded = DatabaseStore(self.database_url, migrate=False)
        try:
            inspector = inspect(downgraded.engine)
            self.assertNotIn("mirror_dialogue_turns", inspector.get_table_names())
            user_columns = {
                item["name"] for item in inspector.get_columns("users")
            }
            self.assertNotIn("mirror_style", user_columns)
        finally:
            downgraded.close()

        command.upgrade(config, "head")
        self.store = DatabaseStore(self.database_url, migrate=False)
        inspector = inspect(self.store.engine)
        self.assertIn("mirror_dialogue_turns", inspector.get_table_names())
        user_columns = {item["name"] for item in inspector.get_columns("users")}
        self.assertIn("mirror_style", user_columns)
        self.store.ensure_user_id(710)
        self.assertEqual(self.store.get_mirror_style(710), "teacher")


class MirrorTelegramStyleContractTest(unittest.IsolatedAsyncioTestCase):
    async def test_ac_08_settings_exposes_four_styles_without_new_command(self):
        product = {"daily_word_goal": 10, "mirror_style": "conversation"}

        keyboard = bot.settings_keyboard(product)
        callbacks = [
            button.callback_data
            for row in keyboard.inline_keyboard
            for button in row
            if button.callback_data
        ]

        self.assertEqual(
            {value for value in callbacks if value.startswith("settings:mirror:")},
            {
                "settings:mirror:teacher",
                "settings:mirror:conversation",
                "settings:mirror:brief",
                "settings:mirror:practice",
            },
        )

    async def test_ac_04_handler_uses_durable_context_and_selected_style(self):
        handler = bot.mirror_text_handler
        update, context, message = text_update(708, "А в разговоре так можно?")
        store = MagicMock()
        store.product_profile.return_value = admitted_profile(active_lang="fr")
        store.has_consent.return_value = True
        store.get_mirror_style.return_value = "conversation"
        store.get_mirror_dialogue.return_value = [
            {"role": "user", "text": "Как переводится bonjour?"},
            {"role": "assistant", "text": "Здравствуйте или добрый день."},
        ]
        service = MagicMock()
        service.ask = AsyncMock(return_value="Да, это нейтральный вариант.")
        memory = SimpleNamespace(enabled=True, retention_days=7)

        with (
            patch.object(bot, "get_store", return_value=store),
            patch.object(bot, "get_bot_profile", return_value=mirror_profile()),
            patch.object(bot, "get_ai_tutor_service", return_value=service),
            patch.object(bot, "MIRROR_MEMORY_SETTINGS", memory, create=True),
            patch.object(bot, "send_mirror_response", new=AsyncMock()),
        ):
            await invoke_handler(handler, update, context)

        payload = service.ask.await_args.kwargs["mirror_payload"]
        self.assertEqual(payload["response_style"], "conversation")
        self.assertEqual(payload["recent_dialogue"], store.get_mirror_dialogue.return_value)
        store.append_mirror_exchange.assert_called_once_with(
            708,
            question="А в разговоре так можно?",
            answer="Да, это нейтральный вариант.",
            retention_days=7,
        )
        message.reply_text.assert_not_awaited()

    async def test_err_02_memory_write_failure_does_not_hide_generated_answer(self):
        handler = bot.mirror_text_handler
        update, context, _message = text_update(709, "Объясни приветствия")
        store = MagicMock()
        store.product_profile.return_value = admitted_profile(active_lang="fr")
        store.has_consent.return_value = True
        store.get_mirror_style.return_value = "teacher"
        store.get_mirror_dialogue.return_value = []
        store.append_mirror_exchange.side_effect = RuntimeError("database unavailable")
        service = MagicMock()
        service.ask = AsyncMock(return_value="Да, начнём с приветствий.")
        send = AsyncMock()

        with (
            patch.object(bot, "get_store", return_value=store),
            patch.object(bot, "get_bot_profile", return_value=mirror_profile()),
            patch.object(bot, "get_ai_tutor_service", return_value=service),
            patch.object(
                bot,
                "MIRROR_MEMORY_SETTINGS",
                SimpleNamespace(enabled=True, retention_days=7),
                create=True,
            ),
            patch.object(bot, "send_mirror_response", new=send),
        ):
            await invoke_handler(handler, update, context)

        send.assert_awaited_once()
        self.assertEqual(send.await_args.args[1], "Да, начнём с приветствий.")


if __name__ == "__main__":
    unittest.main()
