import asyncio
import json
import os
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, MagicMock, patch


os.environ.setdefault("BOT_TOKEN", "123456:TESTTOKEN")
os.environ.setdefault("ALLOWED_USER_ID", "1")
os.environ.setdefault("ALLOW_SQLITE_DEV", "true")

import bot
from mydictionary import ai_tutor
from mydictionary import mirror_assistant as companion
from mydictionary.localization import translate
from mydictionary.storage import AICreditExhausted, AIQuotaExceeded
from tests import test_ai_learning_companion as companion_tests
from tests.test_ai_learning_companion import (
    admitted_profile,
    mirror_policy,
    mirror_preferences,
    mirror_profile,
    text_update,
)


PERSONA = "Answer directly as a careful language teacher using grounded facts."


class CaptureResponses:
    def __init__(self):
        self.calls = []

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(
            id="response-experience",
            model=kwargs["model"],
            service_tier=kwargs["service_tier"],
            status="completed",
            output_text=json.dumps(
                {
                    "answer_ru": "💡 Direct answer.",
                    "evidence_ru": [],
                    "interpretation_ru": "",
                    "language_items": [],
                    "examples": [],
                    "next_step_ru": "",
                }
            ),
            usage=SimpleNamespace(
                input_tokens=1,
                input_tokens_details=SimpleNamespace(
                    cached_tokens=0, cache_write_tokens=0
                ),
                output_tokens=1,
                output_tokens_details=SimpleNamespace(reasoning_tokens=0),
                total_tokens=2,
            ),
        )


class AIResponseRendererContractTest(unittest.TestCase):
    def test_ac1_renderer_is_emoji_led_compact_deduplicated_and_schema_free(self):
        answer = ai_tutor.parse_mirror_answer(
            {
                "answer_ru": "Точность 75%. Повтори 猫.",
                "evidence_ru": ["Точность 75%.", "Слово 猫 пока слабое."],
                "interpretation_ru": "Слово 猫 пока слабое.",
                "language_items": [],
                "examples": [
                    {
                        "target": "猫が好きです。",
                        "transcription": "neko ga suki desu",
                        "russian": "Я люблю кошек.",
                    },
                    {
                        "target": "猫です。",
                        "transcription": "neko desu",
                        "russian": "Это кошка.",
                    },
                ],
                "next_step_ru": "Повтори 猫 в одном предложении.",
            }
        )

        rendered = ai_tutor.render_mirror_answer(answer, available_credits=9)
        paragraphs = rendered.split("\n\n")

        self.assertLessEqual(len(rendered), 900)
        self.assertTrue(1 <= len(paragraphs) <= 3)
        self.assertTrue(paragraphs[0].startswith("💡"))
        self.assertTrue(paragraphs[1].startswith("📌"))
        self.assertTrue(paragraphs[-1].startswith("👉"))
        self.assertEqual(rendered.count("Точность 75%."), 1)
        self.assertEqual(rendered.count("Слово 猫 пока слабое."), 1)
        self.assertIn("猫が好きです。", rendered)
        self.assertNotIn("猫です。", rendered)
        self.assertNotIn("AI-кредиты", rendered)
        for label in ai_tutor.MIRROR_RESPONSE_SCHEMA["required"]:
            self.assertNotIn(label, rendered)

    def test_ac1_renderer_strips_adversarial_schema_tokens_and_duplicate_emoji(self):
        answer = ai_tutor.parse_mirror_answer(
            {
                "answer_ru": (
                    "Полезный ответ. answer_ru — внутренняя метка. "
                    "💡 Лишний встроенный значок."
                ),
                "evidence_ru": [
                    "Факт сохранён. evidence_ru — внутренняя метка. "
                    "📌 Лишний встроенный значок."
                ],
                "interpretation_ru": (
                    "Вывод сохранён. interpretation_ru и language_items — "
                    "внутренние метки."
                ),
                "language_items": [
                    {
                        "target": "猫",
                        "transcription": "neko",
                        "meaning_ru": "кошка",
                        "note_ru": "Подсказка сохранена. examples — внутренняя метка.",
                    }
                ],
                "examples": [],
                "next_step_ru": (
                    "Сделай один пример. next_step_ru — внутренняя метка. "
                    "👉 Лишний встроенный значок."
                ),
            }
        )

        rendered = ai_tutor.render_mirror_answer(answer, available_credits=4)

        self.assertTrue(rendered.strip())
        self.assertLessEqual(len(rendered), 900)
        for safe_content in (
            "Полезный ответ.",
            "Факт сохранён.",
            "Вывод сохранён.",
            "Подсказка сохранена.",
            "Сделай один пример.",
            "猫 neko — кошка",
        ):
            with self.subTest(safe_content=safe_content):
                self.assertIn(safe_content, rendered)
        violations = {
            "schema_tokens": [
                label
                for label in ai_tutor.MIRROR_RESPONSE_SCHEMA["required"]
                if label.casefold() in rendered.casefold()
            ],
            "emoji_contract_violations": {
                "💡": rendered.count("💡") != 1,
                "📌": rendered.count("📌") > 1,
                "👉": rendered.count("👉") > 1,
            },
        }
        self.assertEqual(
            violations,
            {
                "schema_tokens": [],
                "emoji_contract_violations": {
                    "💡": False,
                    "📌": False,
                    "👉": False,
                },
            },
        )

    def test_ac1_renderer_preserves_ordinary_examples_but_strips_schema_forms(self):
        answer = ai_tutor.parse_mirror_answer(
            {
                "answer_ru": (
                    "Here are examples. The examples make the rule clearer. "
                    "answer_ru: internal schema label."
                ),
                "evidence_ru": [
                    "Use examples in practice. evidence_ru: internal schema label. "
                    "examples: internal schema label. `examples` is internal."
                ],
                "interpretation_ru": (
                    "Good examples reinforce memory. "
                    "interpretation_ru: internal schema label."
                ),
                "language_items": [
                    {
                        "target": "example",
                        "transcription": "/ɪɡˈzɑːmpəl/",
                        "meaning_ru": "пример",
                        "note_ru": (
                            "Compare two examples. "
                            "`language_items` is internal."
                        ),
                    }
                ],
                "examples": [],
                "next_step_ru": (
                    "Write one of your own examples. "
                    "next_step_ru: internal schema label."
                ),
            }
        )

        rendered = ai_tutor.render_mirror_answer(answer, available_credits=4)

        for safe_sentence in (
            "Here are examples.",
            "The examples make the rule clearer.",
            "Use examples in practice.",
            "Good examples reinforce memory.",
            "Compare two examples.",
            "Write one of your own examples.",
        ):
            with self.subTest(safe_sentence=safe_sentence):
                self.assertIn(safe_sentence, rendered)
        self.assertNotIn("examples:", rendered.casefold())
        self.assertNotIn("`examples`", rendered.casefold())
        for label in (
            "answer_ru",
            "evidence_ru",
            "interpretation_ru",
            "language_items",
            "next_step_ru",
        ):
            self.assertNotIn(label, rendered.casefold())


class AIResponseHandlerContractTest(unittest.IsolatedAsyncioTestCase):
    GREETING_CASES = {
        "en": "hello, do you know what to do?",
        "fr": "bonjour, tu sais quoi faire ?",
        "de": "hallo, weißt du, was zu tun ist?",
        "ja": "こんにちは、何をすればいいかわかりますか？",
        "ar": "مرحباً، هل تعرف ماذا تفعل؟",
        "zh": "你好，你知道该做什么吗？",
        "ru": "привет, ты знаешь что делать?",
        "es": "hola, ¿sabes qué hacer?",
    }
    PROGRESS_CASES = {
        "en": "what have I already completed?",
        "fr": "qu'est-ce que j'ai déjà terminé ?",
        "de": "was habe ich schon abgeschlossen?",
        "ja": "もう何を終えましたか？",
        "ar": "ماذا أكملت بالفعل؟",
        "zh": "我已经完成了什么？",
        "ru": "что я уже прошел?",
        "es": "¿qué he completado ya?",
    }

    def handler_fixture(self, *, locale, question, enabled=False, credits=0):
        update, context, message = text_update(901, question, interface_locale=locale)
        context.user_data["interface_locale"] = locale
        context.bot = SimpleNamespace(send_chat_action=AsyncMock())
        store = MagicMock()
        store.product_profile.return_value = admitted_profile()
        store.has_consent.return_value = True
        store.ai_usage_summary.return_value = {"available_credits": credits}
        service = SimpleNamespace(ask=AsyncMock(return_value="💡 Safe answer."))
        settings = SimpleNamespace(
            enabled=enabled,
            initial_credits=0,
            consent_version="ai-v1",
            processing_notice="notice",
        )
        patches = (
            patch.object(bot, "get_store", return_value=store),
            patch.object(bot, "get_bot_profile", return_value=mirror_profile()),
            patch.object(bot, "get_ai_tutor_service", return_value=service),
            patch.object(bot, "_mirror_preferences", return_value=mirror_preferences()),
            patch.object(bot, "_mirror_control_policy", return_value=mirror_policy()),
            patch.object(bot, "_mirror_mode", return_value="text"),
            patch.object(bot, "mirror_voice_output_enabled", return_value=False),
            patch.object(bot, "AI_SETTINGS", settings),
            patch.object(
                bot,
                "MIRROR_MEMORY_SETTINGS",
                SimpleNamespace(enabled=False, retention_days=7),
            ),
        )
        return update, context, message, store, service, patches

    async def invoke(self, *, locale, question, enabled=False, credits=0):
        values = self.handler_fixture(
            locale=locale, question=question, enabled=enabled, credits=credits
        )
        update, context, message, store, service, patches = values
        for active_patch in patches:
            active_patch.start()
            self.addCleanup(active_patch.stop)
        await bot.handle_mirror_question(update, context, question=question)
        return update, context, message, store, service

    async def test_ac2_eight_locale_capability_greetings_are_free_and_two_paragraph(self):
        self.assertEqual(set(self.GREETING_CASES), set(bot.INTERFACE_LOCALES))
        for locale, question in self.GREETING_CASES.items():
            with self.subTest(locale=locale):
                _update, context, message, store, service = await self.invoke(
                    locale=locale, question=question
                )
                rendered = message.reply_text.await_args_list[-1].args[0]
                paragraphs = rendered.split("\n\n")
                self.assertEqual(len(paragraphs), 2)
                self.assertTrue(paragraphs[0].startswith("👋"))
                self.assertTrue(paragraphs[1].startswith("💡"))
                self.assertNotIn("transcription", rendered.casefold())
                self.assertNotIn("request report", rendered.casefold())
                service.ask.assert_not_awaited()
                store.has_consent.assert_not_called()
                store.reserve_ai_usage.assert_not_called()
                store.append_mirror_exchange.assert_not_called()
                context.bot.send_chat_action.assert_not_awaited()
                self.assertFalse(
                    any(
                        c.args[0][:1] in {"⚡", "🧠", "💭"}
                        for c in message.reply_text.await_args_list
                    )
                )

    async def test_ac2_eight_locale_completed_progress_is_free_and_grounded(self):
        self.assertEqual(set(self.PROGRESS_CASES), set(bot.INTERFACE_LOCALES))
        for locale, question in self.PROGRESS_CASES.items():
            with self.subTest(locale=locale):
                _update, context, message, store, service = await self.invoke(
                    locale=locale, question=question
                )
                rendered = message.reply_text.await_args_list[-1].args[0]
                self.assertEqual(
                    rendered,
                    "\n".join(
                        (
                            "📊 " + translate("mirror_progress_no_history", locale),
                            "👉 " + translate("mirror_progress_focus_starter", locale),
                        )
                    ),
                )
                self.assertNotIn("ja-basics-100", rendered)
                self.assertNotIn("901", rendered)
                service.ask.assert_not_awaited()
                store.has_consent.assert_not_called()
                store.append_mirror_exchange.assert_not_called()
                context.bot.send_chat_action.assert_not_awaited()

    async def test_ac2_broad_substrings_remain_provider_learning_questions(self):
        for question in (
            "what can you do with the word can?",
            "Is ‘hello, do you know what to do?’ a natural English phrase?",
        ):
            with self.subTest(question=question):
                _update, _context, _message, _store, service = await self.invoke(
                    locale="en", question=question, enabled=True, credits=3
                )
                service.ask.assert_awaited_once()

    async def test_edge_empty_text_stays_local_and_never_starts_thinking(self):
        update, context, message, store, service, patches = self.handler_fixture(
            locale="fr", question="", enabled=True, credits=3
        )
        for active_patch in patches:
            active_patch.start()
            self.addCleanup(active_patch.stop)
        await bot.handle_mirror_question(update, context, question="")
        message.reply_text.assert_awaited_once_with(
            translate("mirror_question_unrecognized", "fr")
        )
        service.ask.assert_not_awaited()
        store.has_consent.assert_not_called()
        context.bot.send_chat_action.assert_not_awaited()

    async def test_ac4_thinking_lifecycle_cleans_up_success_errors_quota_and_cancel(self):
        deep_status = "⚡"
        cases = (
            ("success", None, None),
            ("provider", RuntimeError("provider failed"), None),
            ("quota", AIQuotaExceeded("budget"), None),
            ("cancel", asyncio.CancelledError(), asyncio.CancelledError),
        )
        for label, failure, raised in cases:
            with self.subTest(case=label):
                update, context, message, _store, service, patches = self.handler_fixture(
                    locale="en", question="explain this grammar", enabled=True, credits=3
                )
                temporary = SimpleNamespace(delete=AsyncMock())

                async def reply(text, *args, **kwargs):
                    del args, kwargs
                    return temporary if text == deep_status else SimpleNamespace()

                message.reply_text = AsyncMock(side_effect=reply)
                if failure is not None:
                    service.ask.side_effect = failure
                for active_patch in patches:
                    active_patch.start()
                try:
                    if raised is None:
                        await bot.handle_mirror_question(
                            update, context, question="explain this grammar"
                        )
                    else:
                        with self.assertRaises(raised):
                            await bot.handle_mirror_question(
                                update, context, question="explain this grammar"
                            )
                finally:
                    for active_patch in reversed(patches):
                        active_patch.stop()
                context.bot.send_chat_action.assert_awaited_once_with(
                    chat_id=901, action="typing"
                )
                self.assertEqual(
                    [c.args[0] for c in message.reply_text.await_args_list].count(
                        deep_status
                    ),
                    1,
                )
                temporary.delete.assert_awaited_once()

    async def test_ac4_no_credit_does_not_create_thinking_or_call_provider(self):
        update, context, message, _store, service, patches = self.handler_fixture(
            locale="en", question="explain this grammar", enabled=True, credits=0
        )
        service.ask.side_effect = AICreditExhausted("empty wallet")
        paywall = patch.object(bot, "send_ai_credit_paywall", new_callable=AsyncMock)
        paywall_mock = paywall.start()
        self.addCleanup(paywall.stop)
        for active_patch in patches:
            active_patch.start()
            self.addCleanup(active_patch.stop)
        await bot.handle_mirror_question(
            update, context, question="explain this grammar"
        )
        paywall_mock.assert_awaited_once()
        service.ask.assert_not_awaited()
        context.bot.send_chat_action.assert_not_awaited()
        self.assertFalse(
            any(
                c.args[0][:1] in {"⚡", "🧠", "💭"}
                for c in message.reply_text.await_args_list
            )
        )

    async def test_ac4_indicator_send_and_delete_failures_are_non_blocking(self):
        deep_status = "⚡"
        for failure_point in ("action", "emoji", "delete", "missing_methods"):
            with self.subTest(failure=failure_point):
                update, context, message, _store, service, patches = self.handler_fixture(
                    locale="en", question="explain this grammar", enabled=True, credits=3
                )
                temporary = SimpleNamespace(delete=AsyncMock())
                if failure_point == "delete":
                    temporary.delete.side_effect = RuntimeError("delete failed")
                if failure_point == "missing_methods":
                    temporary = SimpleNamespace()
                    context.bot = SimpleNamespace()
                elif failure_point == "action":
                    context.bot.send_chat_action.side_effect = RuntimeError("action failed")

                async def reply(text, *args, **kwargs):
                    del args, kwargs
                    if text == deep_status and failure_point == "emoji":
                        raise RuntimeError("emoji failed")
                    return temporary if text == deep_status else SimpleNamespace()

                message.reply_text = AsyncMock(side_effect=reply)
                for active_patch in patches:
                    active_patch.start()
                try:
                    await bot.handle_mirror_question(
                        update, context, question="explain this grammar"
                    )
                finally:
                    for active_patch in reversed(patches):
                        active_patch.stop()
                service.ask.assert_awaited_once()
                self.assertIn("💡 Safe answer.", [c.args[0] for c in message.reply_text.await_args_list])
                if failure_point == "action":
                    context.bot.send_chat_action.assert_awaited_once()
                elif failure_point == "emoji":
                    self.assertEqual(
                        [c.args[0] for c in message.reply_text.await_args_list].count(
                            deep_status
                        ),
                        1,
                    )
                elif failure_point == "delete":
                    temporary.delete.assert_awaited_once()

    async def test_edge_concurrent_requests_delete_only_their_own_thinking_message(self):
        deep_status = "⚡"
        update1, context1, message1, _store, service, patches = self.handler_fixture(
            locale="en", question="explain this grammar", enabled=True, credits=3
        )
        update1.effective_user.id = update1.effective_chat.id = 911
        update2, context2, message2 = text_update(
            912, "explain this grammar", interface_locale="en"
        )
        context2.user_data["interface_locale"] = "en"
        context2.bot = SimpleNamespace(send_chat_action=AsyncMock())
        first, second = (
            SimpleNamespace(delete=AsyncMock()),
            SimpleNamespace(delete=AsyncMock()),
        )

        async def reply1(text, *args, **kwargs):
            del args, kwargs
            return first if text == deep_status else SimpleNamespace()

        async def reply2(text, *args, **kwargs):
            del args, kwargs
            return second if text == deep_status else SimpleNamespace()

        async def answer(**kwargs):
            del kwargs
            await asyncio.sleep(0)
            return "💡 Safe answer."

        message1.reply_text = AsyncMock(side_effect=reply1)
        message2.reply_text = AsyncMock(side_effect=reply2)
        service.ask.side_effect = answer
        for active_patch in patches:
            active_patch.start()
        try:
            await asyncio.gather(
                bot.handle_mirror_question(
                    update1, context1, question="explain this grammar"
                ),
                bot.handle_mirror_question(
                    update2, context2, question="explain this grammar"
                ),
            )
        finally:
            for active_patch in reversed(patches):
                active_patch.stop()

        self.assertEqual(service.ask.await_count, 2)
        first.delete.assert_awaited_once()
        second.delete.assert_awaited_once()
        self.assertIsNot(first, second)


class AIResponseRoutingContractTest(unittest.IsolatedAsyncioTestCase):
    def test_ac3_pure_classifier_assigns_fast_or_deep_without_false_overlap(self):
        classify = getattr(companion, "classify_ai_response_route", None)
        self.assertTrue(callable(classify), "missing pure fast/deep response classifier")
        cases = {
            "fast": (
                "translate cat",
                "how do I pronounce bonjour?",
                "what does casa mean?",
                "hello there",
                "is Paris in France?",
            ),
            "deep": (
                "explain why this grammar rule works",
                "correct this paragraph and explain every change",
                "compare the present perfect and past simple",
                "create a multi-step exercise from my mistakes",
                "analyze my progress and weak words in detail",
            ),
        }
        for expected, questions in cases.items():
            for question in questions:
                with self.subTest(expected=expected, question=question):
                    self.assertEqual(classify(question), expected)
                    self.assertEqual(classify(question), expected)

    def test_ac3_semantically_equivalent_fast_and_deep_routes_cover_eight_locales(self):
        classify = companion.classify_ai_response_route
        deep = {
            "en": "explain this grammar rule",
            "fr": "explique cette règle de grammaire",
            "de": "erkläre diese Grammatikregel",
            "ja": "この文法規則を説明してください",
            "ar": "اشرح هذه القاعدة النحوية",
            "zh": "请解释这个语法规则",
            "ru": "объясни это грамматическое правило",
            "es": "explica esta regla gramatical",
        }
        fast = {
            "en": 'translate "grammar rule"',
            "fr": "traduis « règle de grammaire »",
            "de": "übersetze „Grammatikregel“",
            "ja": "「文法規則」を翻訳して",
            "ar": "ترجم «قاعدة نحوية»",
            "zh": "翻译“语法规则”",
            "ru": "переведи «грамматическое правило»",
            "es": "traduce «regla gramatical»",
        }
        common_deep_variants = {
            "fr": "explique-moi cette règle simplement",
            "de": "erkläre bitte diese Regel",
            "ja": "この規則を詳しく説明して",
            "ar": "اشرح هذه القاعدة بالتفصيل",
            "zh": "请详细解释这条规则",
            "ru": "объясни это правило подробно",
            "es": "explica esta regla en detalle",
        }
        correction_deep = {
            "en": "correct this sentence",
            "fr": "corrige cette phrase",
            "de": "korrigiere diesen Satz",
            "ja": "この文を直して",
            "ar": "صحح هذه الجملة",
            "zh": "改正这个句子",
            "ru": "исправь это предложение",
            "es": "corrige esta frase",
        }
        comparison_deep = {
            "en": "compare these two tenses",
            "fr": "compare ces deux temps",
            "de": "vergleiche diese beiden Zeitformen",
            "ja": "この二つの時制を比較して",
            "ar": "قارن بين هذين الزمنين",
            "zh": "比较这两个时态",
            "ru": "сравни эти два времени",
            "es": "compara estos dos tiempos",
        }
        pronunciation_fast = {
            "en": "pronounce hello",
            "fr": "prononce bonjour",
            "de": "sprich Hallo aus",
            "ja": "こんにちはの発音",
            "ar": "انطق مرحبا",
            "zh": "怎么读你好",
            "ru": "произнеси привет",
            "es": "pronuncia hola",
        }
        english_deep_action_families = (
            "compare and contrast these two tenses",
            "build a multi-step exercise from my errors",
            "review and analyze my mistakes",
            "why is this sentence wrong?",
        )
        reviewer_fast_controls = (
            ("ja", "quoted_translation", "「比較して」を翻訳して"),
            ("ja", "quoted_meaning", "「比較して」はどういう意味ですか"),
            ("zh", "pronunciation", "比较怎么读"),
            ("zh", "quoted_meaning", "“比较”是什么意思"),
        )
        self.assertEqual(set(deep), set(bot.INTERFACE_LOCALES))
        self.assertEqual(set(fast), set(bot.INTERFACE_LOCALES))
        self.assertEqual(set(correction_deep), set(bot.INTERFACE_LOCALES))
        self.assertEqual(set(comparison_deep), set(bot.INTERFACE_LOCALES))
        self.assertEqual(set(pronunciation_fast), set(bot.INTERFACE_LOCALES))
        self.assertEqual(
            set(common_deep_variants),
            set(bot.INTERFACE_LOCALES) - {"en"},
        )
        for expected, table in (("deep", deep), ("fast", fast)):
            for locale, phrase in table.items():
                with self.subTest(locale=locale, expected=expected):
                    self.assertEqual(classify(phrase), expected)
                    self.assertEqual(classify(phrase), expected)
        for locale, phrase in common_deep_variants.items():
            with self.subTest(locale=locale, expected="deep", shape="common"):
                self.assertEqual(classify(phrase), "deep")
                self.assertEqual(classify(phrase), "deep")
        for expected, table in (
            ("deep", correction_deep),
            ("deep", comparison_deep),
            ("fast", pronunciation_fast),
        ):
            for locale, phrase in table.items():
                with self.subTest(
                    locale=locale,
                    expected=expected,
                    shape="action_family",
                ):
                    self.assertEqual(classify(phrase), expected)
                    self.assertEqual(classify(phrase), expected)
        with self.subTest(locale="zh", expected="deep", shape="polite_correction"):
            self.assertEqual(classify("请改正这个句子"), "deep")
            self.assertEqual(classify("请改正这个句子"), "deep")
        for phrase in english_deep_action_families:
            with self.subTest(locale="en", expected="deep", phrase=phrase):
                self.assertEqual(classify(phrase), "deep")
                self.assertEqual(classify(phrase), "deep")
        for locale, shape, phrase in reviewer_fast_controls:
            with self.subTest(locale=locale, expected="fast", shape=shape):
                self.assertEqual(classify(phrase), "fast")
                self.assertEqual(classify(phrase), "fast")

        complex_without_exact_marker = {
            "ja": (
                "最近の学習内容を踏まえて二つの文型の違いを段階的に整理し、"
                "間違いを直す練習も作ってください"
            ),
            "zh": (
                "请根据我最近的学习记录逐步整理两个句型的差异，"
                "并给出纠错练习和复习建议"
            ),
            "ar": (
                "راجع إجاباتي الأخيرة وحدد الأنماط المختلفة في الأخطاء ثم اقترح "
                "خطة تدريبية متعددة الخطوات مع أمثلة وتمارين مناسبة لمستواي الحالي"
            ),
        }
        simple_target_phrases = {
            "ja": "おはよう",
            "zh": "早上好",
            "ar": "صباح الخير",
        }
        for locale, phrase in complex_without_exact_marker.items():
            with self.subTest(locale=locale, expected="deep", shape="long"):
                self.assertEqual(classify(phrase), "deep")
        for locale, phrase in simple_target_phrases.items():
            with self.subTest(locale=locale, expected="fast", shape="short"):
                self.assertEqual(classify(phrase), "fast")

    async def test_ac4_legacy_service_adapter_keeps_thinking_and_final_answer(self):
        deep_status = "⚡"
        update, context, message, _store, service, patches = (
            AIResponseHandlerContractTest().handler_fixture(
                locale="en",
                question="explain this grammar",
                enabled=True,
                credits=3,
            )
        )
        calls = []

        class LegacyService:
            async def ask(self, *, user_id, question, mirror_payload):
                calls.append((user_id, question, mirror_payload))
                return "💡 Legacy-safe answer."

        service.ask = LegacyService().ask
        temporary = SimpleNamespace(delete=AsyncMock())

        async def reply(text, *args, **kwargs):
            del args, kwargs
            return temporary if text == deep_status else SimpleNamespace()

        message.reply_text = AsyncMock(side_effect=reply)
        for active_patch in patches:
            active_patch.start()
        try:
            await bot.handle_mirror_question(
                update, context, question="explain this grammar"
            )
        finally:
            for active_patch in reversed(patches):
                active_patch.stop()

        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][0:2], (901, "explain this grammar"))
        self.assertEqual(calls[0][2]["complexity_route"], "deep")
        rendered = [item.args[0] for item in message.reply_text.await_args_list]
        self.assertEqual(rendered, [deep_status, "💡 Legacy-safe answer."])
        self.assertNotIn(translate("ai_failure", "en"), rendered)
        temporary.delete.assert_awaited_once()

    async def test_ac3_route_is_immutable_validated_pre_metering_and_one_credit(self):
        payload = companion.build_mirror_provider_payload(
            question="translate cat",
            admin_guidance=PERSONA,
            grounded_snapshot={"has_progress": False},
            recent_dialogue=[],
            response_style="teacher",
            interface_locale="en",
        )
        tampered = {**payload, "complexity_route": "deep"}
        service2, store2, provider2, settings2 = (
            companion_tests.LearningCompanionServiceHardeningTest.service_fixture(
                max_provider_input_chars=12000
            )
        )
        settings2.assert_runtime_ready.side_effect = AssertionError("metering reached")
        with self.assertRaises(ValueError):
            await service2.ask_mirror(user_id=902, payload=tampered)
        settings2.assert_runtime_ready.assert_not_called()
        store2.reserve_ai_usage.assert_not_called()
        provider2.generate_mirror.assert_not_awaited()

        self.assertEqual(payload["complexity_route"], "fast")
        service, store, provider, _settings = (
            companion_tests.LearningCompanionServiceHardeningTest.service_fixture(
                max_provider_input_chars=12000
            )
        )
        await service.ask_mirror(user_id=902, payload=payload)
        sent = provider.generate_mirror.await_args.kwargs["payload"]
        self.assertEqual(sent["complexity_route"], "fast")
        self.assertEqual(store.reserve_ai_usage.call_count, 1)
        self.assertEqual(store.reserve_ai_usage.call_args.kwargs["credits"], 1)
        self.assertEqual(store.complete_ai_usage.call_args.kwargs["billed_credits"], 1)

    async def test_ac4_cancelled_thinking_hook_releases_before_provider_attempt(self):
        payload = (
            companion_tests.LearningCompanionServiceHardeningTest().valid_payload()
        )
        service, store, provider, _settings = (
            companion_tests.LearningCompanionServiceHardeningTest.service_fixture(
                max_provider_input_chars=12000
            )
        )
        on_provider_start = AsyncMock(side_effect=asyncio.CancelledError())

        with self.assertRaises(asyncio.CancelledError):
            await service.ask_mirror(
                user_id=904,
                payload=payload,
                on_provider_start=on_provider_start,
            )

        on_provider_start.assert_awaited_once()
        provider.generate_mirror.assert_not_awaited()
        store.reserve_ai_usage.assert_called_once()
        store.fail_ai_usage.assert_called_once()
        self.assertEqual(
            store.fail_ai_usage.call_args.kwargs["error_code"],
            "CancelledError",
        )
        self.assertIsNone(
            store.fail_ai_usage.call_args.kwargs["open_breaker_reason"]
        )
        store.mark_ai_provider_attempt_started.assert_not_called()
        store.complete_ai_usage.assert_not_called()

    async def test_ac3_provider_uses_exact_adaptive_parameters_on_one_approved_model(self):
        capture = CaptureResponses()
        provider = ai_tutor.OpenAIResponsesProvider(
            api_key="test-key",
            model="gpt-5.6-luna",
            service_tier="default",
            safety_salt="response-experience-test-salt",
            max_output_tokens=1000,
            client=SimpleNamespace(responses=capture),
        )
        for route, effort, verbosity, max_tokens in (
            ("fast", "none", "low", 320),
            ("deep", "medium", "medium", 480),
        ):
            payload = companion.build_mirror_provider_payload(
                question=("translate cat" if route == "fast" else "explain this grammar rule"),
                admin_guidance=PERSONA,
                grounded_snapshot={"has_progress": False},
                response_style="teacher",
                interface_locale="en",
            )
            self.assertEqual(payload["complexity_route"], route)
            await provider.generate_mirror(
                request_id=f"route-{route}", user_id=903, payload=payload
            )
            kwargs = capture.calls[-1]
            self.assertEqual(kwargs["model"], "gpt-5.6-luna")
            self.assertEqual(kwargs["service_tier"], "default")
            self.assertEqual(kwargs["reasoning"], {"effort": effort})
            self.assertEqual(kwargs["text"]["verbosity"], verbosity)
            self.assertEqual(kwargs["max_output_tokens"], max_tokens)


if __name__ == "__main__":
    unittest.main()
