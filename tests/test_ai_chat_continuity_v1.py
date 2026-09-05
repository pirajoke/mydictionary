import asyncio
import json
import os
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch


os.environ.setdefault("BOT_TOKEN", "123456:TESTTOKEN")
os.environ.setdefault("ALLOWED_USER_ID", "1")
os.environ.setdefault("ALLOW_SQLITE_DEV", "true")

import bot
from mydictionary import ai_tutor
from mydictionary import mirror_assistant as companion
from mydictionary.localization import translate
from tests import test_ai_learning_companion as companion_tests
from tests import test_ai_response_experience_v1 as response_tests


PERSONA = "Answer directly as a careful language teacher using grounded facts."


class AIChatContinuityRoutingTest(unittest.TestCase):
    NATURAL_CONTEXT_FOLLOWUPS = {
        "en": "what's the issue?",
        "fr": "où est le problème ?",
        "de": "wo liegt das Problem?",
        "ja": "何が問題なの？",
        "ar": "ما المشكلة؟",
        "zh": "问题出在哪里？",
        "ru": "в чем затык",
        "es": "¿cuál es el problema?",
    }
    DEEP_METHODS = {
        "en": "tell me about language-learning methods",
        "fr": "parle-moi des méthodes d’apprentissage des langues",
        "de": "erzähle mir von Methoden zum Sprachenlernen",
        "ja": "語学学習の方法について教えて",
        "ar": "حدثني عن طرق تعلم اللغات",
        "zh": "告诉我语言学习的方法",
        "ru": "расскажи про методы изучения языков",
        "es": "háblame de métodos para aprender idiomas",
    }
    FAST_CONTROLS = {
        "en": "translate cat",
        "fr": "traduis chat",
        "de": "übersetze Katze",
        "ja": "猫を翻訳して",
        "ar": "ترجم كلمة قطة",
        "zh": "翻译猫",
        "ru": "переведи слово кот",
        "es": "traduce gato",
    }
    ORDINARY_METHOD_DISCUSSION = {
        "en": "can we discuss ways to learn a language?",
        "fr": "peut-on discuter des façons d’apprendre une langue ?",
        "de": "können wir über Wege zum Sprachenlernen sprechen?",
        "ja": "言語を学ぶ方法について話せますか？",
        "ar": "هل يمكننا مناقشة طرق تعلم اللغة؟",
        "zh": "我们可以聊聊学习语言的方法吗？",
        "ru": "можем обсудить способы изучения языка?",
        "es": "¿podemos hablar de formas de aprender un idioma?",
    }
    IMPERATIVE_METHOD_DISCUSSION = {
        "en": "discuss language-learning methods",
        "fr": "discute des méthodes d’apprentissage des langues",
        "de": "diskutiere Methoden zum Sprachenlernen",
        "ja": "語学学習の方法について議論して",
        "ar": "ناقش طرق تعلم اللغات",
        "zh": "讨论语言学习的方法",
        "ru": "обсуди методы изучения языков",
        "es": "discute métodos para aprender idiomas",
    }
    SIMPLE_FAST_CONTROLS = {
        "en": ("translate cat", "what does cat mean?", "how do I pronounce cat?"),
        "fr": ("traduis chat", "que veut dire chat ?", "comment prononcer chat ?"),
        "de": ("übersetze Katze", "was bedeutet Katze?", "wie spricht man Katze aus?"),
        "ja": ("猫を翻訳して", "猫はどういう意味？", "猫はどう発音する？"),
        "ar": ("ترجم كلمة قطة", "ما معنى قطة؟", "كيف أنطق قطة؟"),
        "zh": ("翻译猫", "猫是什么意思？", "猫怎么读？"),
        "ru": ("переведи слово кот", "что значит кот?", "как произнести кот?"),
        "es": ("traduce gato", "¿qué significa gato?", "¿cómo se pronuncia gato?"),
    }
    FOLLOWUPS = {
        "en": "thanks, now tell me about study methods",
        "fr": "merci, maintenant parle-moi des méthodes d’apprentissage",
        "de": "danke, und was ist mit Methoden zum Sprachenlernen?",
        "ja": "ありがとう、では語学学習の方法について教えて",
        "ar": "شكراً، والآن حدثني عن طرق تعلم اللغات",
        "zh": "谢谢，现在说说语言学习的方法",
        "ru": "спасибо, теперь расскажи про методы изучения языков",
        "es": "gracias, ahora háblame de métodos para aprender idiomas",
    }
    VARIABLE_TAIL_FOLLOWUPS = {
        "en": (
            "thanks, now tell me about spaced repetition",
            "and what about shadowing?",
        ),
        "fr": (
            "merci, maintenant parle-moi de la répétition espacée",
            "et qu’en est-il du shadowing ?",
        ),
        "de": (
            "danke, jetzt erzähl mir etwas über verteiltes Wiederholen",
            "und was ist mit Shadowing?",
        ),
        "ja": (
            "ありがとう、次は間隔反復について教えて",
            "では、シャドーイングはどうですか？",
        ),
        "ar": (
            "شكراً، والآن أخبرني عن التكرار المتباعد",
            "وماذا عن أسلوب الترديد؟",
        ),
        "zh": (
            "谢谢，现在告诉我间隔重复",
            "那影子跟读呢？",
        ),
        "ru": (
            "спасибо, теперь расскажи про интервальные повторения",
            "а что насчёт шэдоуинга?",
        ),
        "es": (
            "gracias, ahora háblame de la repetición espaciada",
            "¿y qué hay del shadowing?",
        ),
    }

    def test_ac1_broad_learning_conversation_is_deep_and_simple_controls_fast(self):
        classify = companion.classify_ai_response_route
        self.assertEqual(set(self.DEEP_METHODS), set(bot.INTERFACE_LOCALES))
        self.assertEqual(set(self.FAST_CONTROLS), set(bot.INTERFACE_LOCALES))
        for expected, table in (
            ("deep", self.DEEP_METHODS),
            ("fast", self.FAST_CONTROLS),
        ):
            for locale, question in table.items():
                with self.subTest(locale=locale, expected=expected):
                    self.assertEqual(classify(question), expected)
                    self.assertEqual(classify(question), expected)

    def test_ac1_ordinary_method_discussion_is_deep_without_broadening_simple_controls(self):
        classify = companion.classify_ai_response_route
        self.assertEqual(
            set(self.ORDINARY_METHOD_DISCUSSION), set(bot.INTERFACE_LOCALES)
        )
        self.assertEqual(set(self.SIMPLE_FAST_CONTROLS), set(bot.INTERFACE_LOCALES))
        for locale, question in self.ORDINARY_METHOD_DISCUSSION.items():
            with self.subTest(locale=locale, expected="deep"):
                self.assertEqual(classify(question), "deep")
                self.assertEqual(classify(question), "deep")
        for locale, questions in self.SIMPLE_FAST_CONTROLS.items():
            for question in questions:
                with self.subTest(locale=locale, expected="fast", question=question):
                    self.assertEqual(classify(question), "fast")
                    self.assertEqual(classify(question), "fast")

    def test_ac1_imperative_method_discussion_is_deep_and_deterministic(self):
        classify = companion.classify_ai_response_route
        self.assertEqual(
            set(self.IMPERATIVE_METHOD_DISCUSSION), set(bot.INTERFACE_LOCALES)
        )
        for locale, question in self.IMPERATIVE_METHOD_DISCUSSION.items():
            with self.subTest(locale=locale):
                self.assertEqual(classify(question), "deep")
                self.assertEqual(classify(question), "deep")

        for locale, questions in self.SIMPLE_FAST_CONTROLS.items():
            for question in questions:
                with self.subTest(locale=locale, control=question):
                    self.assertEqual(classify(question), "fast")

    def test_ac2_ec2_followups_keep_latest_dialogue_context_and_empty_is_false(self):
        history = companion_tests.recent_turns(12)
        learner_context = companion.build_companion_learner_context(
            product_profile=companion_tests.admitted_profile(),
            grounded_progress={"has_progress": True, "due_count": 2},
            has_active_block=False,
            learner_level="a2",
        )
        self.assertEqual(set(self.FOLLOWUPS), set(bot.INTERFACE_LOCALES))
        for locale, question in self.FOLLOWUPS.items():
            with self.subTest(locale=locale, history="present"):
                payload = companion.build_mirror_provider_payload(
                    question=question,
                    admin_guidance=PERSONA,
                    grounded_snapshot={
                        "has_progress": True,
                        "accuracy_percent": 75,
                        "due_count": 2,
                    },
                    learner_context=learner_context,
                    recent_dialogue=history,
                    response_style="teacher",
                    interface_locale=locale,
                )
                self.assertIs(payload["is_continuation"], True)
                self.assertEqual(payload["recent_dialogue"], history[-8:])
                self.assertEqual(payload["learner_context"], learner_context)
                self.assertLessEqual(
                    len(json.dumps(payload, ensure_ascii=False)), 12000
                )
                serialized = json.dumps(payload, ensure_ascii=False).casefold()
                self.assertNotIn("telegram_user_id", serialized)
                self.assertNotIn("user_id", serialized)

            with self.subTest(locale=locale, history="empty"):
                empty = companion.build_mirror_provider_payload(
                    question=question,
                    admin_guidance=PERSONA,
                    grounded_snapshot={"has_progress": False},
                    learner_context=learner_context,
                    recent_dialogue=[],
                    response_style="teacher",
                    interface_locale=locale,
                )
                self.assertIs(empty["is_continuation"], False)
                self.assertEqual(empty["recent_dialogue"], [])

    def test_ac2_variable_tail_followups_require_nonempty_history(self):
        history = companion_tests.recent_turns(12)
        self.assertEqual(
            set(self.VARIABLE_TAIL_FOLLOWUPS), set(bot.INTERFACE_LOCALES)
        )
        for locale, questions in self.VARIABLE_TAIL_FOLLOWUPS.items():
            for question in questions:
                with self.subTest(locale=locale, history="present", question=question):
                    payload = companion.build_mirror_provider_payload(
                        question=question,
                        admin_guidance=PERSONA,
                        grounded_snapshot={"has_progress": True, "due_count": 2},
                        recent_dialogue=history,
                        response_style="teacher",
                        interface_locale=locale,
                    )
                    self.assertIs(payload["is_continuation"], True)
                    self.assertEqual(payload["recent_dialogue"], history[-8:])

                with self.subTest(locale=locale, history="empty", question=question):
                    empty = companion.build_mirror_provider_payload(
                        question=question,
                        admin_guidance=PERSONA,
                        grounded_snapshot={"has_progress": False},
                        recent_dialogue=[],
                        response_style="teacher",
                        interface_locale=locale,
                    )
                    self.assertIs(empty["is_continuation"], False)
                    self.assertEqual(empty["recent_dialogue"], [])

    def test_ac2_natural_context_questions_continue_chat_not_dictionary_mode(self):
        history = companion_tests.recent_turns(3)
        self.assertEqual(
            set(self.NATURAL_CONTEXT_FOLLOWUPS), set(bot.INTERFACE_LOCALES)
        )
        for locale, question in self.NATURAL_CONTEXT_FOLLOWUPS.items():
            with self.subTest(locale=locale, history="present"):
                payload = companion.build_mirror_provider_payload(
                    question=question,
                    admin_guidance=PERSONA,
                    grounded_snapshot={"has_progress": True, "due_count": 2},
                    recent_dialogue=history,
                    response_style="teacher",
                    task_kind=companion.classify_mirror_task(question),
                    communication_mode="teacher",
                    answer_depth="balanced",
                    learner_level="adaptive",
                    interface_locale=locale,
                )
                self.assertIs(payload["is_continuation"], True)
                self.assertEqual(payload["task_kind"], "general_conversation")
                self.assertEqual(payload["recent_dialogue"], history[-8:])

            with self.subTest(locale=locale, history="empty"):
                payload = companion.build_mirror_provider_payload(
                    question=question,
                    admin_guidance=PERSONA,
                    grounded_snapshot={"has_progress": False},
                    recent_dialogue=[],
                    response_style="teacher",
                    task_kind=companion.classify_mirror_task(question),
                    communication_mode="teacher",
                    answer_depth="balanced",
                    learner_level="adaptive",
                    interface_locale=locale,
                )
                self.assertIs(payload["is_continuation"], False)

        for explicit_request in (
            "как перевести «в чем затык» на английский?",
            "что значит выражение «в чем затык»?",
        ):
            with self.subTest(explicit_request=explicit_request):
                self.assertEqual(
                    companion.classify_mirror_task(explicit_request),
                    "translation_nuance",
                )


class AIChatContinuityHandlerTest(unittest.IsolatedAsyncioTestCase):
    def fixture(self, *, locale, question, credits=3, enabled=True):
        return response_tests.AIResponseHandlerContractTest().handler_fixture(
            locale=locale,
            question=question,
            enabled=enabled,
            credits=credits,
        )

    @staticmethod
    def install_message_probe(message):
        temporary = SimpleNamespace(delete=AsyncMock())

        async def reply(text, *args, **kwargs):
            del args, kwargs
            return temporary if text == "⚡" else SimpleNamespace()

        message.reply_text = AsyncMock(side_effect=reply)
        return temporary

    async def test_ac3_indicator_matches_fast_deep_and_contextual_state(self):
        cases = (
            ("translate cat", False),
            ("explain this grammar rule", False),
            ("thanks, now tell me about study methods", True),
        )
        for question, contextual in cases:
            with self.subTest(question=question):
                update, context, message, _store, service, patches = self.fixture(
                    locale="en", question=question
                )
                if contextual:
                    context.user_data[companion.MIRROR_DIALOGUE_KEY] = (
                        companion_tests.recent_turns(3)
                    )
                temporary = self.install_message_probe(message)
                for active_patch in patches:
                    active_patch.start()
                try:
                    await bot.handle_mirror_question(
                        update, context, question=question
                    )
                finally:
                    for active_patch in reversed(patches):
                        active_patch.stop()

                service.ask.assert_awaited_once()
                status = message.reply_text.await_args_list[0].args[0]
                self.assertEqual(status, "⚡")
                context.bot.send_chat_action.assert_awaited_once_with(
                    chat_id=901, action="typing"
                )
                temporary.delete.assert_awaited_once()

    async def test_ac2_ac3_variable_tail_followups_use_localized_context_status(self):
        for locale, questions in (
            AIChatContinuityRoutingTest.VARIABLE_TAIL_FOLLOWUPS.items()
        ):
            for question in questions:
                with self.subTest(locale=locale, question=question):
                    update, context, message, _store, service, patches = self.fixture(
                        locale=locale, question=question
                    )
                    context.user_data[companion.MIRROR_DIALOGUE_KEY] = (
                        companion_tests.recent_turns(3)
                    )
                    temporary = self.install_message_probe(message)
                    for active_patch in patches:
                        active_patch.start()
                    try:
                        await bot.handle_mirror_question(
                            update, context, question=question
                        )
                    finally:
                        for active_patch in reversed(patches):
                            active_patch.stop()

                    service.ask.assert_awaited_once()
                    self.assertEqual(
                        message.reply_text.await_args_list[0].args[0],
                        "⚡",
                    )
                    temporary.delete.assert_awaited_once()

    async def test_ac3_ac5_eight_locale_status_and_failure_are_localized_no_charge(self):
        statuses = {}
        for locale, question in AIChatContinuityRoutingTest.DEEP_METHODS.items():
            with self.subTest(locale=locale):
                update, context, message, store, service, patches = self.fixture(
                    locale=locale, question=question
                )
                service.ask.side_effect = ai_tutor.AIProviderError(
                    "PRIVATE provider output must not leak"
                )
                temporary = self.install_message_probe(message)
                for active_patch in patches:
                    active_patch.start()
                try:
                    await bot.handle_mirror_question(
                        update, context, question=question
                    )
                finally:
                    for active_patch in reversed(patches):
                        active_patch.stop()

                rendered = [item.args[0] for item in message.reply_text.await_args_list]
                statuses[locale] = rendered[0]
                store.append_mirror_exchange.assert_not_called()
                temporary.delete.assert_awaited_once()
                self.assertEqual(
                    {
                        "text_lightning_status": rendered[0] == "⚡",
                        "no_charge_copy": rendered[-1]
                        == translate("ai_unavailable_no_charge", locale),
                        "private_detail_leaked": "private" in " ".join(rendered).casefold(),
                        "provider_detail_leaked": "provider" in " ".join(rendered).casefold(),
                    },
                    {
                        "text_lightning_status": True,
                        "no_charge_copy": True,
                        "private_detail_leaked": False,
                        "provider_detail_leaked": False,
                    },
                )
        self.assertEqual(set(statuses.values()), {"⚡"})

    async def test_ec1_free_capability_route_has_no_indicator_or_metering(self):
        update, context, message, store, service, patches = self.fixture(
            locale="en",
            question="hello, do you know what to do?",
            credits=0,
            enabled=False,
        )
        for active_patch in patches:
            active_patch.start()
        try:
            await bot.handle_mirror_question(
                update, context, question="hello, do you know what to do?"
            )
        finally:
            for active_patch in reversed(patches):
                active_patch.stop()

        service.ask.assert_not_awaited()
        store.has_consent.assert_not_called()
        store.reserve_ai_usage.assert_not_called()
        context.bot.send_chat_action.assert_not_awaited()
        rendered = [item.args[0] for item in message.reply_text.await_args_list]
        self.assertNotIn("⚡", rendered)


class AIChatContinuityEconomicsTest(unittest.IsolatedAsyncioTestCase):
    def payload(self, question):
        return companion.build_mirror_provider_payload(
            question=question,
            admin_guidance=PERSONA,
            grounded_snapshot={"has_progress": False},
            recent_dialogue=[],
            response_style="teacher",
            interface_locale="en",
        )

    async def test_ac4_provider_parameters_use_fast_320_and_deep_480(self):
        capture = response_tests.CaptureResponses()
        provider = ai_tutor.OpenAIResponsesProvider(
            api_key="test-key",
            model="gpt-5.6-luna",
            service_tier="default",
            safety_salt="continuity-provider-test-salt",
            max_output_tokens=1000,
            client=SimpleNamespace(responses=capture),
        )
        cases = (
            ("translate cat", "fast", "none", "low", 320),
            ("explain this grammar rule", "deep", "medium", "medium", 480),
        )
        for question, route, effort, verbosity, ceiling in cases:
            with self.subTest(route=route):
                payload = self.payload(question)
                self.assertEqual(payload["complexity_route"], route)
                await provider.generate_mirror(
                    request_id=f"continuity-{route}",
                    user_id=905,
                    payload=payload,
                )
                kwargs = capture.calls[-1]
                self.assertEqual(kwargs["reasoning"], {"effort": effort})
                self.assertEqual(kwargs["text"]["verbosity"], verbosity)
                self.assertEqual(kwargs["max_output_tokens"], ceiling)
                self.assertEqual(kwargs["model"], "gpt-5.6-luna")

    async def test_ac4_preflight_uses_same_ceiling_and_success_costs_one_credit(self):
        original = ai_tutor.estimate_mirror_provider_budget
        for question, expected_ceiling in (
            ("translate cat", 320),
            ("explain this grammar rule", 480),
        ):
            with self.subTest(expected_ceiling=expected_ceiling):
                service, store, provider, settings = (
                    companion_tests.LearningCompanionServiceHardeningTest.service_fixture(
                        max_provider_input_chars=12000
                    )
                )
                settings.max_output_tokens = 1000
                with patch.object(
                    ai_tutor,
                    "estimate_mirror_provider_budget",
                    wraps=original,
                ) as estimate:
                    await service.ask_mirror(
                        user_id=906,
                        payload=self.payload(question),
                    )
                self.assertEqual(
                    estimate.call_args.kwargs["max_output_tokens"],
                    expected_ceiling,
                )
                provider.generate_mirror.assert_awaited_once()
                self.assertEqual(
                    store.reserve_ai_usage.call_args.kwargs["credits"], 1
                )
                self.assertEqual(
                    store.complete_ai_usage.call_args.kwargs["billed_credits"], 1
                )

    async def test_err1_incomplete_response_is_not_retried_rendered_persisted_or_billed(self):
        incomplete = ai_tutor.ProviderResult(
            answer=None,
            response_id="incomplete-response",
            model="test-model",
            usage=ai_tutor.ProviderUsage(output_tokens=320, total_tokens=321),
            service_tier="default",
            status="incomplete",
            output_text=json.dumps(
                {
                    "answer_ru": "This output must never be rendered.",
                    "evidence_ru": [],
                    "interpretation_ru": "",
                    "language_items": [],
                    "examples": [],
                    "next_step_ru": "",
                }
            ),
        )
        service, store, provider, settings = (
            companion_tests.LearningCompanionServiceHardeningTest.service_fixture(
                max_provider_input_chars=12000,
                provider_result=incomplete,
            )
        )
        settings.max_output_tokens = 1000

        with self.assertRaises(ai_tutor.AIProviderError):
            await service.ask_mirror(
                user_id=907,
                payload=self.payload("translate cat"),
            )

        provider.generate_mirror.assert_awaited_once()
        store.fail_ai_usage.assert_called_once()
        store.complete_ai_usage.assert_not_called()
        store.record_mirror_quality.assert_not_called()
        store.append_mirror_exchange.assert_not_called()
        self.assertIsNone(
            store.fail_ai_usage.call_args.kwargs["open_breaker_reason"]
        )

    async def test_err2_cancelled_indicator_hook_precedes_provider_attempt_and_breaker(self):
        service, store, provider, settings = (
            companion_tests.LearningCompanionServiceHardeningTest.service_fixture(
                max_provider_input_chars=12000
            )
        )
        settings.max_output_tokens = 1000
        hook = AsyncMock(side_effect=asyncio.CancelledError())

        with self.assertRaises(asyncio.CancelledError):
            await service.ask_mirror(
                user_id=908,
                payload=self.payload("translate cat"),
                on_provider_start=hook,
            )

        hook.assert_awaited_once()
        provider.generate_mirror.assert_not_awaited()
        store.mark_ai_provider_attempt_started.assert_not_called()
        store.fail_ai_usage.assert_called_once()
        self.assertIsNone(
            store.fail_ai_usage.call_args.kwargs["open_breaker_reason"]
        )
        store.complete_ai_usage.assert_not_called()


if __name__ == "__main__":
    unittest.main()
