from __future__ import annotations

import copy
import inspect
import os
import time
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch


os.environ.setdefault("BOT_TOKEN", "123456:TESTTOKEN_ABCDEFGHIJKLMNOP")
os.environ.setdefault("ALLOWED_USER_ID", "1")
os.environ.setdefault("ALLOW_SQLITE_DEV", "true")

import bot
from mydictionary.localization import INTERFACE_LOCALES, translate


USER_ID = 784_001
PENDING_KEY = "pending_dictionary_lookup"
DICTIONARY_TTL_SECONDS = 10 * 60


def required_handler(testcase: unittest.TestCase):
    handler = getattr(bot, "cmd_dictionary", None)
    testcase.assertIsNotNone(handler, "missing /dictionary command handler")
    testcase.assertTrue(callable(handler), "/dictionary handler must be callable")
    testcase.assertTrue(
        hasattr(handler, "__wrapped__"),
        "/dictionary must use the existing authenticated command boundary",
    )
    return handler


def command_update(
    args: list[str],
    *,
    locale: str = "ru",
) -> tuple[SimpleNamespace, SimpleNamespace, SimpleNamespace]:
    message = SimpleNamespace(
        text="/dictionary" + (f" {' '.join(args)}" if args else ""),
        chat_id=USER_ID,
        reply_text=AsyncMock(),
    )
    update = SimpleNamespace(
        message=message,
        effective_message=message,
        effective_user=SimpleNamespace(
            id=USER_ID,
            username=None,
            first_name="Learner",
            last_name=None,
            language_code=locale,
        ),
        effective_chat=SimpleNamespace(id=USER_ID, type="private"),
    )
    context = SimpleNamespace(
        user_data={"interface_locale": locale},
        args=list(args),
        bot=SimpleNamespace(),
    )
    return update, context, message


def text_update(
    value: str,
    *,
    locale: str = "ru",
    user_data: dict | None = None,
) -> tuple[SimpleNamespace, SimpleNamespace, SimpleNamespace]:
    message = SimpleNamespace(
        text=value,
        chat_id=USER_ID,
        reply_text=AsyncMock(),
    )
    update = SimpleNamespace(
        message=message,
        effective_message=message,
        effective_user=SimpleNamespace(
            id=USER_ID,
            username=None,
            first_name="Learner",
            last_name=None,
            language_code=locale,
        ),
        effective_chat=SimpleNamespace(id=USER_ID, type="private"),
    )
    context = SimpleNamespace(
        user_data=user_data if user_data is not None else {"interface_locale": locale},
        args=[],
        bot=SimpleNamespace(),
    )
    return update, context, message


def learner_runtime(
    *,
    pack_id: str = "fr-basics-100",
    active_language: str = "fr",
    meaning_language: str = "ru",
    locale: str = "ru",
    words: list[dict] | None = None,
) -> bot.LearnerRuntime:
    store = MagicMock()
    store.load_word_progress.return_value = {}
    progress = dict(bot.PROGRESS_DEFAULTS)
    progress.update(
        {
            "active_lang": active_language,
            "active_pack_id": pack_id,
            "total_correct": 7,
            "total_wrong": 2,
            "xp": 91,
        }
    )
    runtime = bot.LearnerRuntime(
        user_id=USER_ID,
        store=store,
        progress=progress,
        meaning_language=meaning_language,
        interface_locale=locale,
        role="learner",
        access_status="active",
        onboarding_completed=True,
    )
    if words is None and bot.CATALOG.get(pack_id) is not None:
        words = bot.CATALOG.words(bot.CATALOG.require(pack_id))
    if words is not None:
        runtime.words_by_lang[pack_id] = copy.deepcopy(words)
    return runtime


async def invoke(handler, update, context) -> None:
    callback = getattr(handler, "__wrapped__", handler)
    await callback(update, context)


def reply_body(message: SimpleNamespace) -> str:
    call = message.reply_text.await_args
    if call.args:
        return str(call.args[0])
    return str(call.kwargs.get("text") or "")


class DictionaryLookupModeV1Test(unittest.IsolatedAsyncioTestCase):
    async def invoke_dictionary(
        self,
        args: list[str],
        *,
        runtime: bot.LearnerRuntime,
        locale: str = "ru",
    ) -> tuple[SimpleNamespace, SimpleNamespace]:
        update, context, message = command_update(args, locale=locale)
        token = bot._ACTIVE_RUNTIME.set(runtime)
        try:
            await invoke(required_handler(self), update, context)
        finally:
            bot._ACTIVE_RUNTIME.reset(token)
        return message, context

    async def test_ac1_err2_direct_target_lookup_is_unicode_normalized_compact_plain_text(self):
        runtime = learner_runtime()

        message, _context = await self.invoke_dictionary(
            ["E\u0301COLE"],
            runtime=runtime,
        )

        message.reply_text.assert_awaited_once()
        rendered = reply_body(message)
        self.assertIn("🇫🇷", rendered)
        self.assertIn("école", rendered)
        self.assertIn("/e.kɔl/", rendered)
        self.assertIn("🇷🇺", rendered)
        self.assertIn("школа", rendered)
        self.assertLessEqual(len(rendered), 512)
        self.assertLess(len(rendered), 4096)
        self.assertIsNone(message.reply_text.await_args.kwargs.get("parse_mode"))

    async def test_ac1_direct_reverse_meaning_lookup_is_case_insensitive(self):
        runtime = learner_runtime()

        message, _context = await self.invoke_dictionary(
            ["ШКОЛА"],
            runtime=runtime,
        )

        message.reply_text.assert_awaited_once()
        rendered = reply_body(message)
        self.assertIn("🇫🇷", rendered)
        self.assertIn("école", rendered)
        self.assertIn("/e.kɔl/", rendered)
        self.assertIn("🇷🇺", rendered)
        self.assertIn("школа", rendered)

    async def test_ac2_no_arg_mode_stores_only_a_bounded_expiry_marker(self):
        runtime = learner_runtime()
        update, context, message = command_update([], locale="ru")

        token = bot._ACTIVE_RUNTIME.set(runtime)
        try:
            with patch.object(bot.time, "time", return_value=10_000):
                await invoke(required_handler(self), update, context)
        finally:
            bot._ACTIVE_RUNTIME.reset(token)

        message.reply_text.assert_awaited_once_with(
            translate("dictionary_prompt", "ru")
        )
        self.assertEqual(
            context.user_data[PENDING_KEY],
            {"expires_at": 10_000 + DICTIONARY_TTL_SECONDS},
        )
        self.assertEqual(
            getattr(bot, "PENDING_DICTIONARY_LOOKUP_KEY", PENDING_KEY),
            PENDING_KEY,
        )
        self.assertNotRegex(repr(context.user_data[PENDING_KEY]), r"слово|word|query")

    async def test_ac2_pending_text_is_consumed_once_before_mirror(self):
        runtime = learner_runtime()
        user_data = {
            "interface_locale": "ru",
            PENDING_KEY: {"expires_at": int(time.time()) + DICTIONARY_TTL_SECONDS},
        }
        first_update, context, first_message = text_update(
            "école",
            user_data=user_data,
        )
        second_update, _unused_context, second_message = text_update(
            "Какой у меня прогресс?",
            user_data=user_data,
        )
        mirror = AsyncMock()

        token = bot._ACTIVE_RUNTIME.set(runtime)
        try:
            with patch.object(bot, "handle_mirror_question", new=mirror):
                await invoke(bot.mirror_text_handler, first_update, context)
                self.assertNotIn(PENDING_KEY, context.user_data)
                mirror.assert_not_awaited()
                await invoke(bot.mirror_text_handler, second_update, context)
        finally:
            bot._ACTIVE_RUNTIME.reset(token)

        self.assertIn("école", reply_body(first_message))
        second_message.reply_text.assert_not_awaited()
        mirror.assert_awaited_once()
        self.assertEqual(
            mirror.await_args.kwargs.get("question"),
            "Какой у меня прогресс?",
        )

    async def test_ac2_ec3_active_written_answer_keeps_priority_over_pending_lookup(self):
        runtime = learner_runtime()
        user_data = {
            "interface_locale": "ru",
            PENDING_KEY: {"expires_at": int(time.time()) + DICTIONARY_TTL_SECONDS},
        }
        bot.reset_block_state(
            user_data,
            [0],
            "fr",
            "greetings",
            "fr-basics-100",
        )
        bot.start_block_attempt(user_data, "type")
        user_data["block_typing"] = True
        user_data["type_idx"] = 0
        update, context, message = text_update("школа", user_data=user_data)
        pending_before = dict(user_data[PENDING_KEY])
        written_answer = AsyncMock()
        mirror = AsyncMock()

        token = bot._ACTIVE_RUNTIME.set(runtime)
        try:
            with (
                patch.object(bot, "handle_type_answer", new=written_answer),
                patch.object(bot, "handle_mirror_question", new=mirror),
            ):
                await invoke(bot.mirror_text_handler, update, context)
        finally:
            bot._ACTIVE_RUNTIME.reset(token)

        written_answer.assert_awaited_once_with(update, context)
        mirror.assert_not_awaited()
        message.reply_text.assert_not_awaited()
        self.assertEqual(context.user_data[PENDING_KEY], pending_before)

    async def test_ec2_expired_or_malformed_pending_fails_closed_and_is_removed(self):
        runtime = learner_runtime()
        cases = (
            {"expires_at": 19_999},
            {"expires_at": "not-a-time"},
            {},
            "malformed",
        )

        token = bot._ACTIVE_RUNTIME.set(runtime)
        try:
            for pending in cases:
                with self.subTest(pending=pending):
                    user_data = {
                        "interface_locale": "ru",
                        PENDING_KEY: copy.deepcopy(pending),
                    }
                    update, context, message = text_update(
                        "école",
                        user_data=user_data,
                    )
                    mirror = AsyncMock()
                    with (
                        patch.object(bot.time, "time", return_value=20_000),
                        patch.object(bot, "handle_mirror_question", new=mirror),
                    ):
                        await invoke(bot.mirror_text_handler, update, context)

                    self.assertNotIn(PENDING_KEY, context.user_data)
                    message.reply_text.assert_awaited_once_with(
                        translate("dictionary_pending_stale", "ru")
                    )
                    mirror.assert_not_awaited()
        finally:
            bot._ACTIVE_RUNTIME.reset(token)

    async def test_ac3_ec1_unknown_multiline_and_oversized_queries_are_local_and_free(self):
        runtime = learner_runtime()
        progress_before = copy.deepcopy(runtime.progress)
        words_before = copy.deepcopy(runtime.words_by_lang)
        cases = (
            ["definitely-not-curated"],
            ["école\nbonjour"],
            ["x" * 81],
        )

        for args in cases:
            with self.subTest(args=args):
                provider = MagicMock()
                mirror = AsyncMock()
                mark_correct = MagicMock()
                mark_wrong = MagicMock()
                with (
                    patch.object(bot, "get_ai_tutor_service", new=provider),
                    patch.object(bot, "handle_mirror_question", new=mirror),
                    patch.object(bot, "mark_correct", new=mark_correct),
                    patch.object(bot, "mark_wrong", new=mark_wrong),
                ):
                    message, context = await self.invoke_dictionary(
                        args,
                        runtime=runtime,
                    )

                message.reply_text.assert_awaited_once()
                rendered = reply_body(message)
                self.assertEqual(rendered, translate("dictionary_not_found", "ru"))
                self.assertIn("/ai", rendered)
                self.assertNotIn(PENDING_KEY, context.user_data)
                provider.assert_not_called()
                mirror.assert_not_awaited()
                mark_correct.assert_not_called()
                mark_wrong.assert_not_called()

        self.assertEqual(runtime.progress, progress_before)
        self.assertEqual(runtime.words_by_lang, words_before)
        runtime.store.reserve_ai_usage.assert_not_called()
        runtime.store.complete_ai_usage.assert_not_called()
        runtime.store.save_profile.assert_not_called()
        runtime.store.save_learning_state.assert_not_called()
        runtime.store.activate_pack.assert_not_called()
        runtime.store.update_product_profile.assert_not_called()

    async def test_ec4_colliding_alias_uses_the_earliest_curated_entry(self):
        words = [
            {
                "entry_id": "first",
                "target": "first",
                "meaning": "общий",
                "transcription": "/fɜːrst/",
            },
            {
                "entry_id": "second",
                "target": "second",
                "meaning": "общий",
                "transcription": "/ˈsekənd/",
            },
        ]
        runtime = learner_runtime(
            pack_id="en-basics-100",
            active_language="en",
            words=words,
        )

        message, _context = await self.invoke_dictionary(
            ["ОБЩИЙ"],
            runtime=runtime,
        )

        rendered = reply_body(message)
        self.assertIn("first", rendered)
        self.assertNotIn("second", rendered)

    async def test_err1_no_active_visible_pack_is_localized_and_does_not_leak_details(self):
        runtime = learner_runtime(
            pack_id="missing-pack",
            active_language="xx",
            words=[],
        )
        provider = MagicMock()
        mirror = AsyncMock()

        with (
            patch.object(bot, "get_ai_tutor_service", new=provider),
            patch.object(bot, "handle_mirror_question", new=mirror),
        ):
            message, _context = await self.invoke_dictionary(
                ["hello"],
                runtime=runtime,
            )

        message.reply_text.assert_awaited_once_with(
            translate("dictionary_unavailable", "ru")
        )
        rendered = reply_body(message)
        self.assertNotRegex(rendered.casefold(), r"missing-pack|pack_id|traceback")
        provider.assert_not_called()
        mirror.assert_not_awaited()
        runtime.store.reserve_ai_usage.assert_not_called()
        runtime.store.save_learning_state.assert_not_called()

    async def test_ec1_raw_multiline_command_fails_closed_when_args_look_valid(self):
        runtime = learner_runtime(
            pack_id="en-basics-100",
            active_language="en",
        )
        update, context, message = command_update(["thank", "you"], locale="ru")
        update.message.text = "/dictionary thank\nyou"
        provider = MagicMock()
        mirror = AsyncMock()

        token = bot._ACTIVE_RUNTIME.set(runtime)
        try:
            with (
                patch.object(bot, "get_ai_tutor_service", new=provider),
                patch.object(bot, "handle_mirror_question", new=mirror),
            ):
                await invoke(required_handler(self), update, context)
        finally:
            bot._ACTIVE_RUNTIME.reset(token)

        message.reply_text.assert_awaited_once_with(
            translate("dictionary_not_found", "ru")
        )
        rendered = reply_body(message)
        self.assertNotIn("/θæŋk juː/", rendered)
        provider.assert_not_called()
        mirror.assert_not_awaited()

    async def test_ac2_direct_command_clears_existing_pending_before_lookup(self):
        runtime = learner_runtime()
        update, context, message = command_update(["école"], locale="ru")
        context.user_data[PENDING_KEY] = {
            "expires_at": int(time.time()) + DICTIONARY_TTL_SECONDS
        }
        next_update, _unused_context, next_message = text_update(
            "Какой у меня прогресс?",
            user_data=context.user_data,
        )
        mirror = AsyncMock()

        token = bot._ACTIVE_RUNTIME.set(runtime)
        try:
            with patch.object(bot, "handle_mirror_question", new=mirror):
                await invoke(required_handler(self), update, context)
                self.assertNotIn(PENDING_KEY, context.user_data)
                self.assertIn("école", reply_body(message))
                await invoke(bot.mirror_text_handler, next_update, context)
        finally:
            bot._ACTIVE_RUNTIME.reset(token)

        next_message.reply_text.assert_not_awaited()
        mirror.assert_awaited_once()
        self.assertEqual(
            mirror.await_args.kwargs.get("question"),
            "Какой у меня прогресс?",
        )

    async def test_ec2_whitespace_text_removes_expired_or_malformed_pending_without_ai(self):
        runtime = learner_runtime()
        cases = ({"expires_at": 29_999}, "malformed")

        token = bot._ACTIVE_RUNTIME.set(runtime)
        try:
            for pending in cases:
                with self.subTest(pending=pending):
                    user_data = {
                        "interface_locale": "ru",
                        PENDING_KEY: copy.deepcopy(pending),
                    }
                    update, context, message = text_update("   ", user_data=user_data)
                    mirror = AsyncMock()
                    provider = MagicMock()
                    with (
                        patch.object(bot.time, "time", return_value=30_000),
                        patch.object(bot, "handle_mirror_question", new=mirror),
                        patch.object(bot, "get_ai_tutor_service", new=provider),
                    ):
                        await invoke(bot.mirror_text_handler, update, context)

                    self.assertNotIn(PENDING_KEY, context.user_data)
                    message.reply_text.assert_awaited_once_with(
                        translate("dictionary_pending_stale", "ru")
                    )
                    mirror.assert_not_awaited()
                    provider.assert_not_called()
        finally:
            bot._ACTIVE_RUNTIME.reset(token)

    async def test_ac1_err2_rtl_meaning_is_wrapped_in_unicode_bidi_isolates(self):
        runtime = learner_runtime(
            pack_id="en-basics-100",
            active_language="en",
            meaning_language="ar",
        )

        message, _context = await self.invoke_dictionary(
            ["hello"],
            runtime=runtime,
            locale="ar",
        )

        message.reply_text.assert_awaited_once()
        rendered = reply_body(message)
        self.assertIn("🇬🇧", rendered)
        self.assertIn("hello", rendered)
        self.assertIn("\u2067مرحبا\u2069", rendered)
        self.assertNotIn("🇷🇺", rendered)
        self.assertIsNone(message.reply_text.await_args.kwargs.get("parse_mode"))

    def test_ac4_dictionary_is_registered_and_localized_in_all_eight_command_menus(self):
        source = inspect.getsource(bot.manual_polling)
        self.assertIn('CommandHandler("dictionary", cmd_dictionary)', source)
        self.assertEqual(
            INTERFACE_LOCALES,
            frozenset({"en", "fr", "de", "ja", "ar", "zh", "ru", "es"}),
        )

        required_copy = (
            "command_dictionary",
            "dictionary_prompt",
            "dictionary_not_found",
            "dictionary_pending_stale",
            "dictionary_unavailable",
        )
        for locale in INTERFACE_LOCALES:
            with self.subTest(locale=locale):
                localized = {
                    key: translate(key, locale).strip() for key in required_copy
                }
                self.assertTrue(all(localized.values()))
                commands = {
                    command.command: command.description
                    for command in bot.build_bot_commands(
                        ai_enabled=False,
                        miniapp_enabled=False,
                        locale=locale,
                    )
                }
                self.assertEqual(
                    commands.get("dictionary"),
                    localized["command_dictionary"],
                )


if __name__ == "__main__":
    unittest.main()
