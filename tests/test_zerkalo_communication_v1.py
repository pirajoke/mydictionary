import json
import os
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock, patch


os.environ.setdefault("BOT_TOKEN", "123456:TESTTOKEN")
os.environ.setdefault("ALLOWED_USER_ID", "1")
os.environ.setdefault("ALLOW_SQLITE_DEV", "true")

import bot
from mydictionary import ai_tutor
from mydictionary import mirror_assistant as companion
from mydictionary.localization import INTERFACE_LOCALES, translate


PERSONA = "Answer directly as a careful language teacher using grounded facts."


def required_public(testcase, owner, name):
    testcase.assertTrue(
        hasattr(owner, name),
        f"missing Zerkalo communication behavior: {owner.__name__}.{name}",
    )
    return getattr(owner, name)


def recent_turns(count=12):
    return [
        {
            "role": "user" if index % 2 == 0 else "assistant",
            "text": f"turn-{index}",
        }
        for index in range(count)
    ]


def admitted_profile(**overrides):
    values = {
        "role": "learner",
        "access_status": "active",
        "onboarding_completed_at": "2026-08-23T00:00:00+00:00",
        "active_lang": "ja",
        "active_pack_id": "ja-basics-100",
        "learning_goal": "travel",
        "daily_word_goal": 10,
    }
    values.update(overrides)
    return values


def mirror_profile():
    return {
        "mirror_capabilities_version": "mirror-capabilities-v2",
        "mirror_capabilities_text": "I explain language and grounded progress.",
        "mirror_persona_guidance": PERSONA,
        "mirror_safety_envelope_checksum": "a" * 64,
    }


def mirror_preferences():
    return {"mode": "teacher", "depth": "compact", "level": "a2"}


def mirror_policy():
    return {
        "enabled_modes": ["teacher"],
        "default_mode": "teacher",
        "mode_guidance": {"teacher": PERSONA},
    }


def text_surface(text, *, locale="en", user_id=801):
    message = SimpleNamespace(
        text=text,
        reply_text=AsyncMock(),
        reply_voice=AsyncMock(),
    )
    update = SimpleNamespace(
        message=message,
        effective_message=message,
        effective_user=SimpleNamespace(
            id=user_id,
            language_code=locale,
            first_name=None,
        ),
        effective_chat=SimpleNamespace(id=user_id),
    )
    context = SimpleNamespace(
        user_data={"interface_locale": locale},
        args=[],
        bot=SimpleNamespace(),
    )
    return update, context, message


class HandlerStore:
    pass


class ZerkaloContinuationContractTest(unittest.TestCase):
    def test_ac1_short_followups_are_continuations_only_with_recent_dialogue(self):
        classify = required_public(self, companion, "is_mirror_continuation")
        phrases = {
            "en": "what next",
            "fr": "et ensuite",
            "de": "und weiter",
            "ja": "続きを",
            "ar": "وماذا بعد",
            "zh": "然后呢",
            "ru": "давай",
            "es": "y después",
        }
        self.assertEqual(set(phrases), set(INTERFACE_LOCALES))
        for locale, phrase in phrases.items():
            with self.subTest(locale=locale, continuity=True):
                self.assertTrue(classify(phrase, recent_dialogue=recent_turns(3)))
            with self.subTest(locale=locale, continuity=False):
                self.assertFalse(classify(phrase, recent_dialogue=[]))

        for greeting in ("привет", "hello", "bonjour", "こんにちは", "你好", "مرحبا"):
            with self.subTest(greeting=greeting):
                self.assertFalse(
                    classify(greeting, recent_dialogue=recent_turns(3))
                )

    def test_ac1_payload_owns_continuation_flag_and_exposes_latest_eight_only(self):
        payload = companion.build_mirror_provider_payload(
            question="et ensuite",
            admin_guidance=PERSONA,
            grounded_snapshot={"has_progress": True},
            recent_dialogue=recent_turns(12),
            response_style="conversation",
            interface_locale="fr",
        )

        self.assertIs(payload["is_continuation"], True)
        self.assertEqual(payload["recent_dialogue"], recent_turns(12)[-8:])
        self.assertNotIn("continuation", payload["question"].casefold())

        no_history = companion.build_mirror_provider_payload(
            question="et ensuite",
            admin_guidance=PERSONA,
            grounded_snapshot={"has_progress": False},
            recent_dialogue=[],
            response_style="conversation",
            interface_locale="fr",
        )
        self.assertIs(no_history["is_continuation"], False)
        self.assertEqual(no_history["recent_dialogue"], [])

    def test_ac1_max_payload_recomputes_continuation_after_dialogue_trimming(self):
        words = [
            {
                "target": str(index) + ("t" * (120 - len(str(index)))),
                "transcription": "x" * 120,
                "meaning_ru": "м" * 220,
                "example": "e" * 120,
            }
            for index in range(12)
        ]
        dialogue = [
            {
                "role": "user" if index % 2 == 0 else "assistant",
                "text": chr(65 + index) * 500,
            }
            for index in range(8)
        ]

        payload = companion.build_mirror_provider_payload(
            question="what next",
            admin_guidance="G" * 1000,
            grounded_snapshot={"has_progress": True, "summary": "s" * 900},
            learning_context={
                "language": "ja",
                "pack_id": "p" * 128,
                "topic": "t" * 128,
                "source": "s" * 128,
                "words": words,
            },
            learner_context={
                "onboarding_completed": True,
                "target_language": "ja",
                "active_pack_id": "p" * 128,
                "learning_goal": "g" * 128,
                "daily_word_goal": 100,
                "learner_level": "c1",
                "learning_stage": "review_due",
                "has_active_block": True,
            },
            recent_dialogue=dialogue,
            response_style="conversation",
            interface_locale="en",
        )
        serialized = json.dumps(
            payload,
            ensure_ascii=False,
            separators=(",", ":"),
        )

        self.assertLessEqual(len(serialized), 12000)
        self.assertEqual(len(payload["learning_context"]["words"]), 12)
        self.assertEqual(payload["recent_dialogue"], [])
        self.assertEqual(
            payload["is_continuation"],
            bool(payload["recent_dialogue"]),
        )
        self.assertIs(payload["is_continuation"], False)


class ZerkaloCompactRendererContractTest(unittest.TestCase):
    def test_ac2_renderer_deduplicates_sections_and_keeps_one_example(self):
        fact = "Точность сейчас 75%; повтори слово 猫."
        answer = ai_tutor.parse_mirror_answer(
            {
                "answer_ru": fact,
                "evidence_ru": [fact],
                "interpretation_ru": fact,
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
                "next_step_ru": fact,
            }
        )

        rendered = ai_tutor.render_mirror_answer(answer, available_credits=39)

        self.assertEqual(rendered.count(fact), 1)
        self.assertIn("猫が好きです。", rendered)
        self.assertNotIn("猫です。", rendered)
        self.assertLessEqual(len(rendered), 900)
        self.assertLessEqual(len(rendered.split("\n\n")), 3)
        self.assertNotRegex(rendered, r"answer_ru|evidence_ru|next_step_ru|AI-кредиты")

    def test_ac2_renderer_truncates_at_boundary_without_broken_markdown(self):
        sentences = " ".join(
            f"Предложение {index} содержит одну ясную мысль."
            for index in range(1, 25)
        )
        fenced = "\n\n```text\n" + ("слово " * 60) + "\n```"
        answer = ai_tutor.parse_mirror_answer(
            {
                "answer_ru": sentences + fenced,
                "evidence_ru": [],
                "interpretation_ru": "",
                "language_items": [],
                "examples": [],
                "next_step_ru": "",
            }
        )

        rendered = ai_tutor.render_mirror_answer(answer, available_credits=39)

        self.assertLessEqual(len(rendered), 900)
        self.assertRegex(rendered.rstrip(), r"[.!?。！？]$")
        self.assertEqual(rendered.count("```") % 2, 0)
        self.assertLessEqual(len(rendered.split("\n\n")), 3)

    def test_ac2_renderer_deduplicates_fact_contained_in_longer_answer(self):
        fact = "Точность 75%."
        answer = ai_tutor.parse_mirror_answer(
            {
                "answer_ru": f"{fact} Повтори 猫.",
                "evidence_ru": [fact],
                "interpretation_ru": "",
                "language_items": [],
                "examples": [],
                "next_step_ru": "",
            }
        )

        rendered = ai_tutor.render_mirror_answer(answer, available_credits=39)

        self.assertEqual(rendered.count(fact), 1)
        self.assertIn("Повтори 猫.", rendered)

    def test_ac2_dedupe_preserves_unique_sentence_from_overlapping_field(self):
        fact = "Точность 75%."
        unique = "Слабое слово 猫."
        answer = ai_tutor.parse_mirror_answer(
            {
                "answer_ru": fact,
                "evidence_ru": [],
                "interpretation_ru": f"{fact} {unique}",
                "language_items": [],
                "examples": [],
                "next_step_ru": "",
            }
        )

        rendered = ai_tutor.render_mirror_answer(answer, available_credits=39)

        self.assertEqual(rendered.count(fact), 1)
        self.assertEqual(rendered.count(unique), 1)

    def test_ac2_sentence_dedupe_preserves_decimals_and_abbreviations(self):
        answer = ai_tutor.parse_mirror_answer(
            {
                "answer_ru": (
                    "Точность 75.5%. Версия 2.0. "
                    "Используй e.g. в примере. Повтори слово."
                ),
                "evidence_ru": ["Повтори слово."],
                "interpretation_ru": "",
                "language_items": [],
                "examples": [],
                "next_step_ru": "",
            }
        )

        rendered = ai_tutor.render_mirror_answer(answer, available_credits=39)

        self.assertIn("Точность 75.5%.", rendered)
        self.assertIn("Версия 2.0.", rendered)
        self.assertIn("e.g.", rendered)
        self.assertEqual(rendered.count("Повтори слово."), 1)
        self.assertNotIn("75. 5%", rendered)
        self.assertNotIn("2. 0", rendered)
        self.assertNotIn("e. g.", rendered)

    def test_ac2_complete_fence_before_long_tail_stays_balanced_after_truncation(self):
        answer = ai_tutor.parse_mirror_answer(
            {
                "answer_ru": (
                    "Коротко.\n\n```text\nпример.\n```\n\n"
                    + ("длинный хвост без границы " * 45)
                ),
                "evidence_ru": [],
                "interpretation_ru": "",
                "language_items": [],
                "examples": [],
                "next_step_ru": "",
            }
        )

        rendered = ai_tutor.render_mirror_answer(answer, available_credits=39)

        self.assertTrue(rendered)
        self.assertLessEqual(len(rendered), 900)
        self.assertEqual(rendered.count("```") % 2, 0)
        self.assertRegex(rendered.rstrip(), r"[.!?。！？]$")

    def test_ac2_long_leading_fence_never_truncates_to_empty_text(self):
        answer = ai_tutor.parse_mirror_answer(
            {
                "answer_ru": (
                    "```text\n"
                    + ("пример без границы " * 65)
                    + ".\n```\nКороткий итог."
                ),
                "evidence_ru": [],
                "interpretation_ru": "",
                "language_items": [],
                "examples": [],
                "next_step_ru": "",
            }
        )

        rendered = ai_tutor.render_mirror_answer(answer, available_credits=39)

        self.assertTrue(rendered.strip())
        self.assertLessEqual(len(rendered), 900)
        self.assertEqual(rendered.count("```") % 2, 0)
        self.assertRegex(rendered.rstrip(), r"[.!?。！？]$")

    def test_ac2_cjk_truncation_ends_at_cjk_sentence_boundary(self):
        answer = ai_tutor.parse_mirror_answer(
            {
                "answer_ru": "".join(
                    f"第{index}句用于说明学习重点。" for index in range(1, 100)
                ),
                "evidence_ru": [],
                "interpretation_ru": "",
                "language_items": [],
                "examples": [],
                "next_step_ru": "",
            }
        )

        rendered = ai_tutor.render_mirror_answer(answer, available_credits=39)

        self.assertTrue(rendered)
        self.assertLessEqual(len(rendered), 900)
        self.assertRegex(rendered, r"[。！？]$")


class ZerkaloProgressFocusContractTest(unittest.IsolatedAsyncioTestCase):
    def test_ac3_progress_and_focus_intents_cover_all_interface_locales(self):
        phrases = {
            "en": "what should I focus on",
            "fr": "sur quoi dois-je me concentrer",
            "de": "worauf soll ich mich konzentrieren",
            "ja": "何に集中すればいい",
            "ar": "على ماذا أركز",
            "zh": "我应该专注什么",
            "ru": "на чем фокус",
            "es": "en qué debo enfocarme",
        }
        self.assertEqual(set(phrases), set(INTERFACE_LOCALES))
        for locale, phrase in phrases.items():
            with self.subTest(locale=locale):
                self.assertEqual(companion.classify_mirror_intent(phrase), "progress")

    def test_ac3_natural_direct_progress_allowlist_returns_matched_locale(self):
        variants = (
            ("en", "how is my progress?"),
            ("en", "what is my progress?"),
            ("ru", "как мой прогресс?"),
            ("ru", "какой у меня прогресс?"),
            ("fr", "comment sont mes progrès ?"),
            ("de", "wie ist mein fortschritt?"),
            ("es", "cómo va mi progreso?"),
            ("ja", "私の進捗はどうですか？"),
            ("zh", "我的学习进度怎么样？"),
            ("ar", "كيف هو تقدمي؟"),
        )
        for expected_locale, phrase in variants:
            with self.subTest(locale=expected_locale, phrase=phrase):
                self.assertEqual(
                    companion.direct_mirror_progress_locale(phrase),
                    expected_locale,
                )

        false_positives = (
            "продолжи фразу на японском",
            "объясни мою ошибку в предложении",
            "why is this word weak here?",
            "resume this sentence",
        )
        for phrase in false_positives:
            with self.subTest(non_progress=phrase):
                self.assertIsNone(companion.direct_mirror_progress_locale(phrase))

    def test_ac3_renderer_is_two_localized_grounded_lines_without_raw_pack_id(self):
        render = required_public(self, companion, "render_mirror_progress_focus")
        snapshot = {
            "has_progress": True,
            "active_pack_id": "PRIVATE-ja-basics-100",
            "accuracy_percent": 74,
            "tracked_words": 12,
            "due_count": 3,
            "streak": 4,
            "weak_terms": [{"term": "猫", "wrong": 3, "correct": 1}],
        }
        outputs = {}
        for locale in INTERFACE_LOCALES:
            with self.subTest(locale=locale):
                rendered = render(snapshot, locale=locale)
                outputs[locale] = rendered
                self.assertEqual(
                    rendered,
                    "\n".join(
                        (
                            translate(
                                "mirror_progress_facts",
                                locale,
                                accuracy=74,
                                tracked=12,
                                due=3,
                                streak=4,
                            ),
                            translate(
                                "mirror_progress_focus_weak",
                                locale,
                                term="猫",
                            ),
                        )
                    ),
                )
                self.assertEqual(len(rendered.splitlines()), 2)
                for value in ("74", "12", "3", "4", "猫"):
                    self.assertIn(value, rendered)
                self.assertNotIn("PRIVATE-ja-basics-100", rendered)
        self.assertGreaterEqual(len(set(outputs.values())), 7)

    def test_ac3_empty_history_is_plain_and_starts_one_five_word_lesson(self):
        render = required_public(self, companion, "render_mirror_progress_focus")
        for locale in INTERFACE_LOCALES:
            with self.subTest(locale=locale):
                rendered = render(
                    {"has_progress": False, "active_pack_id": "PRIVATE-pack"},
                    locale=locale,
                )
                self.assertEqual(
                    rendered,
                    "\n".join(
                        (
                            translate("mirror_progress_no_history", locale),
                            translate("mirror_progress_focus_starter", locale),
                        )
                    ),
                )
                self.assertEqual(len(rendered.splitlines()), 2)
                self.assertNotIn("PRIVATE-pack", rendered)

    def test_ac3_due_reviews_take_focus_when_no_weak_term_exists(self):
        render = required_public(self, companion, "render_mirror_progress_focus")
        snapshot = {
            "has_progress": True,
            "active_pack_id": "PRIVATE-pack",
            "accuracy_percent": 90,
            "tracked_words": 8,
            "due_count": 3,
            "streak": 2,
            "weak_terms": [],
        }
        for locale in INTERFACE_LOCALES:
            with self.subTest(locale=locale):
                rendered = render(snapshot, locale=locale)
                self.assertEqual(
                    rendered.splitlines()[1],
                    translate("mirror_progress_focus_due", locale, due=3),
                )
                self.assertNotIn("PRIVATE-pack", rendered)

    async def test_ac3_handler_is_free_when_ai_is_disabled_or_consent_missing(self):
        snapshot = {
            "has_progress": True,
            "active_pack_id": "PRIVATE-ja-basics-100",
            "accuracy_percent": 74,
            "tracked_words": 12,
            "due_count": 3,
            "streak": 4,
            "weak_terms": [{"term": "猫", "wrong": 3, "correct": 1}],
        }
        for enabled in (False, True):
            with self.subTest(ai_enabled=enabled):
                update, context, message = text_surface(
                    "sur quoi dois-je me concentrer",
                    locale="fr",
                )
                store = HandlerStore()
                store.product_profile = Mock(return_value=admitted_profile())
                store.has_consent = Mock(return_value=False)
                store.reserve_ai_usage = Mock()
                service = SimpleNamespace(
                    ask=AsyncMock(side_effect=bot.AIQuotaExceeded("quota"))
                )
                with (
                    patch.object(bot, "DatabaseStore", HandlerStore),
                    patch.object(bot, "get_store", return_value=store),
                    patch.object(bot, "get_bot_profile", return_value=mirror_profile()),
                    patch.object(bot, "get_ai_tutor_service", return_value=service),
                    patch.object(bot, "grounded_progress_snapshot", return_value=snapshot),
                    patch.object(bot, "_mirror_preferences", return_value=mirror_preferences()),
                    patch.object(bot, "_mirror_control_policy", return_value=mirror_policy()),
                    patch.object(bot, "_mirror_mode", return_value="text"),
                    patch.object(bot, "mirror_voice_output_enabled", return_value=False),
                    patch.object(
                        bot,
                        "AI_SETTINGS",
                        SimpleNamespace(enabled=enabled, consent_version="ai-v1"),
                    ),
                ):
                    await bot.mirror_text_handler.__wrapped__(update, context)

                render = required_public(
                    self,
                    companion,
                    "render_mirror_progress_focus",
                )
                message.reply_text.assert_awaited_once_with(
                    render(snapshot, locale="fr")
                )
                store.has_consent.assert_not_called()
                store.reserve_ai_usage.assert_not_called()
                service.ask.assert_not_awaited()

    async def test_ac3_learning_phrases_never_divert_to_free_progress(self):
        phrases = (
            "продолжи фразу на японском",
            "объясни мою ошибку в предложении",
            "why is this word weak here?",
            "resume this sentence",
        )
        for index, phrase in enumerate(phrases):
            with self.subTest(phrase=phrase):
                update, context, _message = text_surface(
                    phrase,
                    locale="en",
                    user_id=820 + index,
                )
                context.user_data[companion.MIRROR_DIALOGUE_KEY] = recent_turns(4)
                store = HandlerStore()
                store.product_profile = Mock(return_value=admitted_profile())
                store.has_consent = Mock(return_value=True)
                store.get_mirror_dialogue = Mock(return_value=recent_turns(4))
                store.append_mirror_exchange = Mock()
                service = SimpleNamespace(
                    ask=AsyncMock(
                        return_value=ai_tutor.MirrorRenderedResponse(
                            "Réponse concise.",
                            request_id=f"ordinary-{index}",
                        )
                    )
                )
                progress_renderer = Mock(return_value="WRONG PROGRESS SURFACE")
                sender = AsyncMock()
                with (
                    patch.object(bot, "DatabaseStore", HandlerStore),
                    patch.object(bot, "get_store", return_value=store),
                    patch.object(bot, "get_bot_profile", return_value=mirror_profile()),
                    patch.object(bot, "get_ai_tutor_service", return_value=service),
                    patch.object(
                        bot,
                        "grounded_progress_snapshot",
                        return_value={"has_progress": True, "weak_terms": []},
                    ),
                    patch.object(
                        bot,
                        "build_mirror_learning_context",
                        return_value={"language": "ja", "source": "profile", "words": []},
                    ),
                    patch.object(bot, "_mirror_preferences", return_value=mirror_preferences()),
                    patch.object(bot, "_mirror_control_policy", return_value=mirror_policy()),
                    patch.object(bot, "_mirror_mode", return_value="text"),
                    patch.object(bot, "mirror_voice_output_enabled", return_value=False),
                    patch.object(bot, "render_mirror_progress_focus", progress_renderer),
                    patch.object(bot, "send_mirror_response", sender),
                    patch.object(
                        bot,
                        "AI_SETTINGS",
                        SimpleNamespace(
                            enabled=True,
                            consent_version="ai-v1",
                            processing_notice="Test notice",
                        ),
                    ),
                    patch.object(
                        bot,
                        "MIRROR_MEMORY_SETTINGS",
                        SimpleNamespace(enabled=True, retention_days=7),
                    ),
                ):
                    await bot.mirror_text_handler.__wrapped__(update, context)

                service.ask.assert_awaited_once()
                progress_renderer.assert_not_called()
                sender.assert_awaited_once()

    async def test_ac3_direct_progress_uses_phrase_locale_with_english_interface(self):
        phrases = {
            "en": "what should I focus on",
            "fr": "sur quoi dois-je me concentrer",
            "de": "worauf soll ich mich konzentrieren",
            "ja": "何に集中すればいい",
            "ar": "على ماذا أركز",
            "zh": "我应该专注什么",
            "ru": "на чем фокус",
            "es": "en qué debo enfocarme",
        }
        for index, (expected_locale, phrase) in enumerate(phrases.items()):
            with self.subTest(locale=expected_locale):
                update, context, message = text_surface(
                    phrase,
                    locale="en",
                    user_id=840 + index,
                )
                context.user_data[companion.MIRROR_DIALOGUE_KEY] = recent_turns(4)
                store = HandlerStore()
                store.product_profile = Mock(return_value=admitted_profile())
                store.has_consent = Mock(return_value=False)
                service = SimpleNamespace(ask=AsyncMock())
                progress_renderer = Mock(
                    side_effect=lambda _snapshot, *, locale: f"free:{locale}"
                )
                with (
                    patch.object(bot, "DatabaseStore", HandlerStore),
                    patch.object(bot, "get_store", return_value=store),
                    patch.object(bot, "get_bot_profile", return_value=mirror_profile()),
                    patch.object(bot, "get_ai_tutor_service", return_value=service),
                    patch.object(
                        bot,
                        "grounded_progress_snapshot",
                        return_value={"has_progress": True, "weak_terms": []},
                    ),
                    patch.object(bot, "_mirror_preferences", return_value=mirror_preferences()),
                    patch.object(bot, "_mirror_control_policy", return_value=mirror_policy()),
                    patch.object(bot, "render_mirror_progress_focus", progress_renderer),
                    patch.object(
                        bot,
                        "AI_SETTINGS",
                        SimpleNamespace(
                            enabled=True,
                            consent_version="ai-v1",
                            processing_notice="Test notice",
                        ),
                    ),
                ):
                    await bot.mirror_text_handler.__wrapped__(update, context)

                message.reply_text.assert_awaited_once_with(
                    f"free:{expected_locale}"
                )
                progress_renderer.assert_called_once()
                self.assertEqual(
                    progress_renderer.call_args.kwargs["locale"],
                    expected_locale,
                )
                store.has_consent.assert_not_called()
                service.ask.assert_not_awaited()


class ZerkaloFeedbackContractTest(unittest.IsolatedAsyncioTestCase):
    async def test_ac4_successful_answer_is_one_message_without_feedback_prompt(self):
        update, context, message = text_surface(
            "Pourquoi ce mot est-il différent ?",
            locale="fr",
            user_id=804,
        )
        store = HandlerStore()
        store.product_profile = Mock(return_value=admitted_profile())
        store.has_consent = Mock(return_value=True)
        store.get_mirror_dialogue = Mock(return_value=recent_turns(10))
        store.append_mirror_exchange = Mock()
        response = ai_tutor.MirrorRenderedResponse(
            "Réponse courte et directe.",
            request_id="legacy-feedback-request",
        )
        service = SimpleNamespace(ask=AsyncMock(return_value=response))
        with (
            patch.object(bot, "DatabaseStore", HandlerStore),
            patch.object(bot, "get_store", return_value=store),
            patch.object(bot, "get_bot_profile", return_value=mirror_profile()),
            patch.object(bot, "get_ai_tutor_service", return_value=service),
            patch.object(
                bot,
                "grounded_progress_snapshot",
                return_value={"has_progress": True, "due_count": 0, "weak_terms": []},
            ),
            patch.object(
                bot,
                "build_mirror_learning_context",
                return_value={"language": "ja", "source": "profile", "words": []},
            ),
            patch.object(bot, "_mirror_preferences", return_value=mirror_preferences()),
            patch.object(bot, "_mirror_control_policy", return_value=mirror_policy()),
            patch.object(bot, "_mirror_mode", return_value="text"),
            patch.object(bot, "mirror_voice_output_enabled", return_value=False),
            patch.object(
                bot,
                "AI_SETTINGS",
                SimpleNamespace(enabled=True, consent_version="ai-v1"),
            ),
            patch.object(
                bot,
                "MIRROR_MEMORY_SETTINGS",
                SimpleNamespace(enabled=True, retention_days=7),
            ),
        ):
            await bot.mirror_text_handler.__wrapped__(update, context)

        message.reply_text.assert_awaited_once_with("Réponse courte et directe.")
        self.assertNotIn(
            translate("mirror_feedback_question", "fr"),
            " ".join(call.args[0] for call in message.reply_text.await_args_list),
        )
        self.assertTrue(callable(bot.mirror_feedback_cb))
        legacy = bot.mirror_feedback_keyboard("legacy-feedback-request", locale="fr")
        self.assertEqual(
            {
                button.callback_data
                for row in legacy.inline_keyboard
                for button in row
            },
            {
                "mirrorfb:legacy-feedback-request:helpful",
                "mirrorfb:legacy-feedback-request:not-helpful",
            },
        )


if __name__ == "__main__":
    unittest.main()
