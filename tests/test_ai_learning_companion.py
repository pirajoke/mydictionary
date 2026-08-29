import json
import os
from pathlib import Path
from types import MappingProxyType, SimpleNamespace
import unittest
from unittest.mock import AsyncMock, MagicMock, Mock, patch


os.environ.setdefault("BOT_TOKEN", "123456:TESTTOKEN")
os.environ.setdefault("ALLOWED_USER_ID", "1")
os.environ.setdefault("ALLOW_SQLITE_DEV", "true")

import bot
import mydictionary.ai_tutor as ai_tutor
import mydictionary.mirror_assistant as companion
from mydictionary.localization import response_language_instruction, translate


ROOT = Path(__file__).resolve().parents[1]
PERSONA = "Answer as a careful language teacher using only grounded facts."


def required_public(testcase, owner, name):
    owner_name = getattr(owner, "__name__", owner.__class__.__name__)
    testcase.assertTrue(
        hasattr(owner, name),
        f"missing AI Learning Companion public behavior: {owner_name}.{name}",
    )
    return getattr(owner, name)


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


def text_update(user_id, text, *, interface_locale="en"):
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
            language_code=interface_locale,
            first_name=None,
        ),
        effective_chat=SimpleNamespace(id=user_id),
    )
    context = SimpleNamespace(user_data={}, args=[], bot=SimpleNamespace())
    return update, context, message


def recent_turns(count=12):
    return [
        {
            "role": "user" if index % 2 == 0 else "assistant",
            "text": f"turn-{index}",
        }
        for index in range(count)
    ]


def mirror_preferences():
    return {"mode": "teacher", "depth": "compact", "level": "a2"}


def mirror_policy():
    return {
        "enabled_modes": ["teacher"],
        "default_mode": "teacher",
        "mode_guidance": {"teacher": PERSONA},
    }


class HandlerStore:
    pass


class LearningCompanionContractTest(unittest.TestCase):
    def test_ac_1_message_language_uses_script_and_confident_lexical_detection(self):
        resolve = required_public(self, companion, "resolve_companion_locale")
        cases = {
            "Объясни, почему это слово здесь подходит.": "ru",
            "この言葉の使い方を説明してください。": "ja",
            "اشرح لماذا تستخدم هذه الكلمة هنا": "ar",
            "请解释这个词为什么用在这里。": "zh",
            "Please explain why this word is used here.": "en",
            "Pourquoi utilise-t-on ce mot dans cette phrase ?": "fr",
            "Warum verwendet man dieses Wort in diesem Satz?": "de",
            "¿Por qué se usa esta palabra en esta frase?": "es",
        }
        for message, expected in cases.items():
            with self.subTest(expected_locale=expected):
                self.assertEqual(
                    resolve(message, interface_locale="de"),
                    expected,
                )

    def test_ec_1_ambiguous_or_unsupported_text_uses_canonical_locale_fallback(self):
        resolve = required_public(self, companion, "resolve_companion_locale")
        cases = (
            ("", "fr", "fr"),
            ("hi", "fr", "fr"),
            ("🙂✨", "ja", "ja"),
            ("12345", "ar", "ar"),
            ("hello привет", "fr", "fr"),
            ("Bom dia obrigado", "de", "de"),
            ("🙂", "pt-BR", "en"),
        )
        for message, interface_locale, expected in cases:
            with self.subTest(
                message=message,
                interface_locale=interface_locale,
            ):
                self.assertEqual(
                    resolve(message, interface_locale=interface_locale),
                    expected,
                )

    def test_ac_1_ec_1_confident_greeting_and_mixed_latin_resolution(self):
        resolve = required_public(self, companion, "resolve_companion_locale")
        cases = (
            ("Bonjour", "de", "fr"),
            (
                "Please explain why this word est utilisé dans cette phrase",
                "de",
                "de",
            ),
            ("hi", "fr", "fr"),
        )
        for text, interface_locale, expected in cases:
            with self.subTest(text=text):
                self.assertEqual(
                    resolve(text, interface_locale=interface_locale),
                    expected,
                )

    def test_ac_1_ac_5_capability_questions_use_message_locale_cross_interface(self):
        resolve = required_public(self, companion, "resolve_companion_locale")
        cases = (
            ("What can you do?", "ja", "en"),
            ("Que peux-tu faire ?", "en", "fr"),
            ("Was kannst du?", "en", "de"),
            ("¿Qué puedes hacer?", "en", "es"),
        )
        for text, interface_locale, expected in cases:
            with self.subTest(text=text):
                self.assertEqual(
                    resolve(text, interface_locale=interface_locale),
                    expected,
                )

    def test_ac_3_learning_stage_is_deterministic_and_priority_ordered(self):
        resolve = required_public(self, companion, "resolve_learning_stage")
        cases = (
            ({"has_progress": False}, "starting"),
            (
                {
                    "has_progress": True,
                    "due_count": 2,
                    "weak_terms": [{"term": "猫"}],
                },
                "review_due",
            ),
            (
                {
                    "has_progress": True,
                    "due_count": 0,
                    "weak_terms": [{"term": "猫"}],
                },
                "needs_practice",
            ),
            (
                {
                    "has_progress": True,
                    "due_count": 0,
                    "weak_terms": [],
                },
                "building_habit",
            ),
        )
        for snapshot, expected in cases:
            with self.subTest(stage=expected):
                self.assertEqual(resolve(snapshot), expected)

    def test_ac_2_grounded_context_is_minimal_bounded_and_contains_no_identity(self):
        build_context = required_public(
            self,
            companion,
            "build_companion_learner_context",
        )
        profile = admitted_profile(
            telegram_user_id="PRIVATE-TELEGRAM-ID",
            username="PRIVATE-USERNAME",
            first_name="PRIVATE-NAME",
            credential="PRIVATE-CREDENTIAL",
        )
        snapshot = {
            "has_progress": True,
            "due_count": 3,
            "weak_terms": [{"term": "猫", "wrong": 2}],
            "accuracy_percent": 75,
            "raw_analytics_event": "PRIVATE-EVENT",
        }

        context = build_context(
            product_profile=profile,
            grounded_progress=snapshot,
            has_active_block=True,
            learner_level="a2",
        )

        self.assertEqual(
            context,
            {
                "onboarding_completed": True,
                "target_language": "ja",
                "active_pack_id": "ja-basics-100",
                "learning_goal": "travel",
                "daily_word_goal": 10,
                "learner_level": "a2",
                "learning_stage": "review_due",
                "has_active_block": True,
            },
        )
        serialized = json.dumps(context, ensure_ascii=False, sort_keys=True)
        for forbidden in (
            "PRIVATE-TELEGRAM-ID",
            "PRIVATE-USERNAME",
            "PRIVATE-NAME",
            "PRIVATE-CREDENTIAL",
            "PRIVATE-EVENT",
        ):
            self.assertNotIn(forbidden, serialized)

    def test_ac_4_payload_has_immutable_compact_policy_newest_eight_turns_and_safe_bound(self):
        build_context = required_public(
            self,
            companion,
            "build_companion_learner_context",
        )
        policy = required_public(
            self,
            companion,
            "MIRROR_COMPACT_REPLY_POLICY",
        )
        self.assertIsInstance(policy, MappingProxyType)
        self.assertEqual(
            dict(policy),
            {
                "max_short_paragraphs": 2,
                "max_optional_examples": 1,
                "max_next_steps": 1,
                "paragraph_style": "short",
            },
        )
        with self.assertRaises(TypeError):
            policy["max_next_steps"] = 2

        learner_context = build_context(
            product_profile=admitted_profile(),
            grounded_progress={
                "has_progress": True,
                "due_count": 0,
                "weak_terms": [],
            },
            has_active_block=False,
            learner_level="a2",
        )
        try:
            payload = companion.build_mirror_provider_payload(
                question="Pourquoi ce mot est-il différent ?",
                admin_guidance=PERSONA,
                grounded_snapshot={"has_progress": True},
                learner_context=learner_context,
                recent_dialogue=recent_turns(12),
                interface_locale="fr",
            )
        except TypeError as exc:
            self.fail(f"missing companion payload integration: {exc}")

        self.assertEqual(payload["recent_dialogue"], recent_turns(12)[-8:])
        self.assertEqual(payload["learner_context"], learner_context)
        self.assertEqual(payload["compact_reply_policy"], dict(policy))
        self.assertLess(
            len(json.dumps(payload, ensure_ascii=False, separators=(",", ":"))),
            12000,
        )

    def test_ac_4_builder_includes_validated_style_guidance_inside_safe_bound(self):
        learner_context = companion.build_companion_learner_context(
            product_profile=admitted_profile(),
            grounded_progress={
                "has_progress": True,
                "due_count": 0,
                "weak_terms": [],
            },
            has_active_block=False,
            learner_level="a2",
        )
        payload = companion.build_mirror_provider_payload(
            question="Pourquoi ce mot est-il différent ?",
            admin_guidance=PERSONA,
            grounded_snapshot={"has_progress": True},
            learner_context=learner_context,
            recent_dialogue=recent_turns(12),
            response_style="teacher",
            interface_locale="fr",
        )

        self.assertIn("style_guidance", payload)
        self.assertEqual(
            payload["style_guidance"],
            companion.MIRROR_STYLE_GUIDANCE["teacher"],
        )
        self.assertLess(
            len(
                json.dumps(
                    payload,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                )
            ),
            12000,
        )

    def test_ec_2_context_normalizes_bounds_and_rejects_malformed_or_unknown_fields(self):
        build_context = required_public(
            self,
            companion,
            "build_companion_learner_context",
        )
        context = build_context(
            product_profile=admitted_profile(
                active_lang="JA",
                active_pack_id="p" * 500,
                learning_goal="g" * 500,
                daily_word_goal="10",
            ),
            grounded_progress={
                "has_progress": True,
                "due_count": 0,
                "weak_terms": [],
            },
            has_active_block=False,
            learner_level="A2",
        )
        self.assertEqual(context["target_language"], "ja")
        self.assertLessEqual(len(context["active_pack_id"]), 128)
        self.assertLessEqual(len(context["learning_goal"]), 128)
        self.assertEqual(context["daily_word_goal"], 10)
        self.assertEqual(context["learner_level"], "a2")

        with self.assertRaises(ValueError):
            build_context(
                product_profile=admitted_profile(daily_word_goal="ten"),
                grounded_progress={"has_progress": False},
                has_active_block=False,
                learner_level="a2",
            )

        unknown = {**context, "telegram_user_id": 123}
        try:
            with self.assertRaises(ValueError):
                companion.build_mirror_provider_payload(
                    question="Explain this word",
                    admin_guidance=PERSONA,
                    grounded_snapshot={"has_progress": True},
                    learner_context=unknown,
                    recent_dialogue=[],
                    interface_locale="en",
                )
        except TypeError as exc:
            self.fail(f"missing fail-closed companion context validation: {exc}")


class LearningCompanionHandlerTest(unittest.IsolatedAsyncioTestCase):
    async def test_ac_5_greeting_and_capability_questions_are_localized_and_free(self):
        cases = (
            (
                "Bonjour",
                "fr",
                bot.render_mirror_greeting(
                    active_language="ja",
                    has_active_block=False,
                    locale="fr",
                ),
            ),
            (
                "何ができますか？",
                "ja",
                translate("mirror_capabilities", "ja"),
            ),
        )
        for question, locale, expected in cases:
            with self.subTest(locale=locale, question=question):
                update, context, message = text_update(
                    601,
                    question,
                    interface_locale=locale,
                )
                store = MagicMock()
                store.product_profile.return_value = admitted_profile()
                store.has_consent.return_value = True
                service = SimpleNamespace(
                    ask=AsyncMock(return_value="PROVIDER-MUST-NOT-RUN")
                )
                with (
                    patch.object(bot, "get_store", return_value=store),
                    patch.object(bot, "get_bot_profile", return_value=mirror_profile()),
                    patch.object(bot, "get_ai_tutor_service", return_value=service),
                    patch.object(bot, "_mirror_preferences", return_value=mirror_preferences()),
                    patch.object(bot, "_mirror_control_policy", return_value=mirror_policy()),
                    patch.object(bot, "_mirror_mode", return_value="text"),
                    patch.object(bot, "mirror_voice_output_enabled", return_value=False),
                    patch.object(
                        bot,
                        "MIRROR_MEMORY_SETTINGS",
                        SimpleNamespace(enabled=False, retention_days=7),
                    ),
                ):
                    await bot.mirror_text_handler.__wrapped__(update, context)

                service.ask.assert_not_awaited()
                store.has_consent.assert_not_called()
                message.reply_text.assert_awaited_once_with(expected)

    async def test_ac_6_normal_message_passes_locale_context_policy_and_bounded_memory(self):
        question = "Pourquoi emploie-t-on ce mot dans cette phrase ?"
        update, context, message = text_update(
            602,
            question,
            interface_locale="de",
        )
        context.user_data.update(
            {
                "block_session": "block-session",
                "block_pack_id": "ja-basics-100",
                "block_lang": "ja",
                "block_all_indices": [0],
            }
        )
        store = HandlerStore()
        store.product_profile = Mock(return_value=admitted_profile())
        store.has_consent = Mock(return_value=True)
        store.get_mirror_dialogue = Mock(return_value=recent_turns(12))
        store.append_mirror_exchange = Mock()
        snapshot = {
            "has_progress": True,
            "due_count": 2,
            "weak_terms": [{"term": "猫"}],
        }
        service = SimpleNamespace(ask=AsyncMock(return_value="Réponse courte."))
        active_words = {
            "language": "ja",
            "pack_id": "ja-basics-100",
            "source": "active_block",
            "words": [],
        }

        with (
            patch.object(bot, "DatabaseStore", HandlerStore),
            patch.object(bot, "get_store", return_value=store),
            patch.object(bot, "get_bot_profile", return_value=mirror_profile()),
            patch.object(bot, "get_ai_tutor_service", return_value=service),
            patch.object(bot, "grounded_progress_snapshot", return_value=snapshot),
            patch.object(bot, "build_mirror_learning_context", return_value=active_words),
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

        service.ask.assert_awaited_once()
        payload = service.ask.await_args.kwargs["mirror_payload"]
        with self.subTest(contract="message_locale"):
            self.assertEqual(payload["interface_locale"], "fr")
            self.assertEqual(
                payload["response_language_instruction"],
                response_language_instruction("fr"),
            )
        with self.subTest(contract="grounded_context"):
            self.assertIn("learner_context", payload)
            self.assertEqual(
                payload["learner_context"],
                {
                    "onboarding_completed": True,
                    "target_language": "ja",
                    "active_pack_id": "ja-basics-100",
                    "learning_goal": "travel",
                    "daily_word_goal": 10,
                    "learner_level": "a2",
                    "learning_stage": "review_due",
                    "has_active_block": True,
                },
            )
        with self.subTest(contract="compact_policy"):
            self.assertIn("compact_reply_policy", payload)
            self.assertEqual(
                payload["compact_reply_policy"],
                dict(companion.MIRROR_COMPACT_REPLY_POLICY),
            )
        with self.subTest(contract="bounded_memory"):
            self.assertEqual(payload["recent_dialogue"], recent_turns(12)[-8:])
            store.get_mirror_dialogue.assert_called_once_with(602, limit=8)
        with self.subTest(contract="memory_write"):
            store.append_mirror_exchange.assert_called_once_with(
                602,
                question=question,
                answer="Réponse courte.",
                retention_days=7,
            )
        self.assertNotIn("602", json.dumps(payload, ensure_ascii=False))
        self.assertEqual(
            [item.args[0] for item in message.reply_text.await_args_list],
            ["⚡", "Réponse courte."],
        )
        message.reply_text.return_value.delete.assert_awaited_once()

    async def test_ac_2_handler_rejects_stale_block_session_as_active_context(self):
        update, context, _message = text_update(
            605,
            "Pourquoi utilise-t-on cette forme dans la phrase ?",
            interface_locale="fr",
        )
        context.user_data.update(
            {
                "block_session": "stale-session",
                "block_pack_id": "missing-pack",
                "block_lang": "ja",
                "block_all_indices": [0],
            }
        )
        self.assertIsNone(bot.active_tutor_context(context.user_data))
        store = MagicMock()
        store.product_profile.return_value = admitted_profile()
        store.has_consent.return_value = True
        service = SimpleNamespace(ask=AsyncMock(return_value="Réponse courte."))

        with (
            patch.object(bot, "get_store", return_value=store),
            patch.object(bot, "get_bot_profile", return_value=mirror_profile()),
            patch.object(bot, "get_ai_tutor_service", return_value=service),
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
                SimpleNamespace(enabled=False, retention_days=7),
            ),
        ):
            await bot.mirror_text_handler.__wrapped__(update, context)

        payload = service.ask.await_args.kwargs["mirror_payload"]
        self.assertFalse(payload["learner_context"]["has_active_block"])

    async def test_ac_5_free_turns_never_enter_process_or_persisted_memory(self):
        for question, interface_locale in (
            ("Bonjour", "de"),
            ("What can you do?", "en"),
        ):
            with self.subTest(question=question):
                update, context, _message = text_update(
                    606,
                    question,
                    interface_locale=interface_locale,
                )
                store = MagicMock()
                store.product_profile.return_value = admitted_profile()
                store.has_consent.return_value = False
                service_factory = Mock(
                    side_effect=AssertionError("free turn must not build a provider")
                )
                with (
                    patch.object(bot, "get_store", return_value=store),
                    patch.object(bot, "get_bot_profile", return_value=mirror_profile()),
                    patch.object(bot, "get_ai_tutor_service", new=service_factory),
                    patch.object(
                        bot,
                        "_mirror_preferences",
                        return_value=mirror_preferences(),
                    ),
                    patch.object(
                        bot,
                        "_mirror_control_policy",
                        return_value=mirror_policy(),
                    ),
                    patch.object(bot, "_mirror_mode", return_value="text"),
                    patch.object(
                        bot,
                        "mirror_voice_output_enabled",
                        return_value=False,
                    ),
                    patch.object(
                        bot,
                        "MIRROR_MEMORY_SETTINGS",
                        SimpleNamespace(enabled=True, retention_days=7),
                    ),
                ):
                    await bot.mirror_text_handler.__wrapped__(update, context)

                service_factory.assert_not_called()
                store.has_consent.assert_not_called()
                store.get_mirror_dialogue.assert_not_called()
                store.append_mirror_exchange.assert_not_called()
                self.assertNotIn(companion.MIRROR_DIALOGUE_KEY, context.user_data)

    async def test_ac_6_memory_gate_forbids_persisted_read_and_write_when_disabled(self):
        question = "Why is this form used here?"
        update, context, _message = text_update(
            603,
            question,
            interface_locale="fr",
        )
        context.user_data[companion.MIRROR_DIALOGUE_KEY] = recent_turns(12)
        store = HandlerStore()
        store.product_profile = Mock(return_value=admitted_profile())
        store.has_consent = Mock(return_value=True)
        store.get_mirror_dialogue = Mock()
        store.append_mirror_exchange = Mock()
        service = SimpleNamespace(ask=AsyncMock(return_value="Short answer."))

        with (
            patch.object(bot, "DatabaseStore", HandlerStore),
            patch.object(bot, "get_store", return_value=store),
            patch.object(bot, "get_bot_profile", return_value=mirror_profile()),
            patch.object(bot, "get_ai_tutor_service", return_value=service),
            patch.object(
                bot,
                "grounded_progress_snapshot",
                return_value={
                    "has_progress": True,
                    "due_count": 0,
                    "weak_terms": [],
                },
            ),
            patch.object(
                bot,
                "build_mirror_learning_context",
                return_value={
                    "language": "ja",
                    "source": "profile",
                    "words": [],
                },
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
                SimpleNamespace(enabled=False, retention_days=7),
            ),
        ):
            await bot.mirror_text_handler.__wrapped__(update, context)

        store.get_mirror_dialogue.assert_not_called()
        store.append_mirror_exchange.assert_not_called()
        payload = service.ask.await_args.kwargs["mirror_payload"]
        self.assertEqual(payload["recent_dialogue"], recent_turns(12)[-8:])

    async def test_err_1_existing_access_onboarding_ai_and_metering_gates_remain_authoritative(self):
        processing_notice = "NOTICE-COMPAGNON-CONFIGURÉE"

        async def invoke(
            *,
            profile=None,
            consent=True,
            ai_enabled=True,
            service_result="Réponse sûre.",
            service_error=None,
            service_factory_error=None,
        ):
            update, context, message = text_update(
                604,
                "Pourquoi ce mot est-il utilisé ?",
                interface_locale="fr",
            )
            store = MagicMock()
            store.product_profile.return_value = profile or admitted_profile()
            store.has_consent.return_value = consent
            service = SimpleNamespace(
                ask=AsyncMock(
                    return_value=service_result,
                    side_effect=service_error,
                )
            )
            service_factory = (
                Mock(side_effect=service_factory_error)
                if service_factory_error is not None
                else Mock(return_value=service)
            )
            paywall = AsyncMock()
            with (
                patch.object(bot, "get_store", return_value=store),
                patch.object(bot, "get_bot_profile", return_value=mirror_profile()),
                patch.object(bot, "get_ai_tutor_service", new=service_factory),
                patch.object(bot, "send_ai_credit_paywall", new=paywall),
                patch.object(bot, "_mirror_preferences", return_value=mirror_preferences()),
                patch.object(bot, "_mirror_control_policy", return_value=mirror_policy()),
                patch.object(bot, "_mirror_mode", return_value="text"),
                patch.object(bot, "mirror_voice_output_enabled", return_value=False),
                patch.object(
                    bot,
                    "AI_SETTINGS",
                    SimpleNamespace(
                        enabled=ai_enabled,
                        consent_version="ai-v1",
                        processing_notice=processing_notice,
                    ),
                ),
                patch.object(
                    bot,
                    "MIRROR_MEMORY_SETTINGS",
                    SimpleNamespace(enabled=False, retention_days=7),
                ),
            ):
                await bot.mirror_text_handler.__wrapped__(update, context)
            return message, context, store, service, service_factory, paywall

        with self.subTest(gate="access"):
            (
                message,
                _context,
                _store,
                service,
                _factory,
                _paywall,
            ) = await invoke(profile=admitted_profile(access_status="blocked"))
            service.ask.assert_not_awaited()
            message.reply_text.assert_awaited_once_with(
                translate("mirror_unavailable", "fr")
            )

        with self.subTest(gate="onboarding"):
            (
                message,
                _context,
                _store,
                service,
                _factory,
                _paywall,
            ) = await invoke(profile=admitted_profile(onboarding_completed_at=None))
            service.ask.assert_not_awaited()
            message.reply_text.assert_awaited_once_with(
                translate("onboarding_required", "fr")
            )

        with self.subTest(gate="ai_disabled"):
            (
                message,
                _context,
                _store,
                service,
                _factory,
                _paywall,
            ) = await invoke(ai_enabled=False)
            service.ask.assert_not_awaited()
            message.reply_text.assert_awaited_once_with(
                translate("ai_disabled", "fr")
            )

        with self.subTest(gate="consent"):
            message, context, store, service, factory, _paywall = await invoke(
                consent=False
            )
            service.ask.assert_not_awaited()
            factory.assert_not_called()
            store.ai_usage_summary.assert_not_called()
            store.reserve_ai_usage.assert_not_called()
            pending = context.user_data["pending_ai_consent"]
            self.assertEqual(pending["request_kind"], "mirror_chat")
            self.assertEqual(
                pending["question"], "Pourquoi ce mot est-il utilisé ?"
            )
            self.assertIsNone(pending["block_session"])
            consent_payload = message.reply_text.await_args
            self.assertEqual(
                consent_payload.args[0],
                translate(
                    "ai_processing_consent",
                    "fr",
                    notice=processing_notice,
                    version="ai-v1",
                ),
            )
            consent_buttons = [
                button.callback_data
                for row in consent_payload.kwargs["reply_markup"].inline_keyboard
                for button in row
            ]
            self.assertEqual(
                consent_buttons,
                ["aiconsent:accept", "aiconsent:cancel"],
            )

        with self.subTest(gate="credits"):
            (
                _message,
                _context,
                _store,
                service,
                _factory,
                paywall,
            ) = await invoke(service_error=bot.AICreditExhausted("no credits"))
            service.ask.assert_awaited_once()
            paywall.assert_awaited_once()

        with self.subTest(gate="quota"):
            (
                message,
                _context,
                _store,
                service,
                _factory,
                _paywall,
            ) = await invoke(service_error=bot.AIQuotaExceeded("quota"))
            service.ask.assert_awaited_once()
            self.assertEqual(
                [item.args[0] for item in message.reply_text.await_args_list],
                [
                    "⚡",
                    translate("ai_unavailable_no_charge", "fr"),
                ],
            )
            message.reply_text.return_value.delete.assert_awaited_once()

        with self.subTest(gate="provider_readiness"):
            diagnostic = "PRIVATE-PROVIDER-READINESS-DIAGNOSTIC"
            (
                message,
                _context,
                _store,
                _service,
                factory,
                _paywall,
            ) = await invoke(service_factory_error=RuntimeError(diagnostic))
            factory.assert_called_once()
            rendered = " ".join(
                call.args[0] for call in message.reply_text.await_args_list
            )
            self.assertEqual(rendered, translate("ai_failure", "fr"))
            self.assertNotIn(diagnostic, rendered)

        with self.subTest(gate="provider_success"):
            (
                message,
                _context,
                _store,
                service,
                _factory,
                _paywall,
            ) = await invoke()
            service.ask.assert_awaited_once()
            self.assertEqual(
                [item.args[0] for item in message.reply_text.await_args_list],
                ["⚡", "Réponse sûre."],
            )
            message.reply_text.return_value.delete.assert_awaited_once()


class LearningCompanionServiceHardeningTest(unittest.IsolatedAsyncioTestCase):
    def valid_payload(self):
        learner_context = companion.build_companion_learner_context(
            product_profile=admitted_profile(),
            grounded_progress={
                "has_progress": True,
                "due_count": 0,
                "weak_terms": [],
            },
            has_active_block=False,
            learner_level="a2",
        )
        return companion.build_mirror_provider_payload(
            question="Pourquoi ce mot est-il différent ?",
            admin_guidance=PERSONA,
            grounded_snapshot={"has_progress": True},
            learner_context=learner_context,
            recent_dialogue=recent_turns(12),
            response_style="teacher",
            interface_locale="fr",
        )

    @staticmethod
    def service_fixture(*, max_provider_input_chars, provider_result=None):
        contract = SimpleNamespace(
            snapshot_id="companion-hardening-test",
            snapshot_sha256="a" * 64,
        )
        settings = SimpleNamespace(
            max_provider_input_chars=max_provider_input_chars,
            assert_runtime_ready=Mock(return_value=contract),
            pricing=ai_tutor.ModelPricing(),
            max_output_tokens=128,
            max_preflight_cost_micro_usd_per_request=1,
            reservation_timeout_seconds=300,
            credits_per_request=1,
            provider="test",
            model="test-model",
            initial_credits=2,
            max_daily_requests_per_user=5,
            service_tier="default",
            max_project_cost_micro_usd_per_day=1000,
            max_project_cost_micro_usd_per_month=10000,
            max_in_flight_cost_micro_usd=1000,
            retrospective_breaker_micro_usd_per_response=1000,
        )
        store = MagicMock()
        store.ai_charge_credits.return_value = 1
        store.reserve_ai_usage.return_value = "companion-request"
        store.complete_ai_usage.return_value = {"available_credits": 1}
        store.fail_ai_usage.return_value = True
        if provider_result is None:
            provider_result = ai_tutor.ProviderResult(
                answer=None,
                response_id="provider-response",
                model="test-model",
                usage=ai_tutor.ProviderUsage(),
                service_tier="default",
                status="completed",
                output_text=json.dumps(
                    {
                        "answer_ru": "Réponse sûre.",
                        "evidence_ru": [],
                        "interpretation_ru": "",
                        "language_items": [],
                        "examples": [],
                        "next_step_ru": "",
                    },
                    ensure_ascii=False,
                ),
            )
        provider = SimpleNamespace(
            generate_mirror=AsyncMock(return_value=provider_result)
        )
        journal = MagicMock()
        journal.pending_count.return_value = 0
        service = ai_tutor.AITutorService(
            store=store,
            provider=provider,
            settings=settings,
            metering_journal=journal,
        )
        return service, store, provider, settings

    async def test_ac_4_service_preserves_builder_payload_without_post_bound_growth(self):
        payload = self.valid_payload()
        payload["style_guidance"] = companion.MIRROR_STYLE_GUIDANCE["teacher"]
        serialized = json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        self.assertLess(len(serialized), 12000)
        service, _store, provider, _settings = self.service_fixture(
            max_provider_input_chars=len(serialized)
        )

        try:
            await service.ask_mirror(user_id=607, payload=payload)
        except ValueError as exc:
            self.fail(f"service rejected the normal bounded builder payload: {exc}")

        _store.reserve_ai_usage.assert_called_once()
        self.assertEqual(
            _store.reserve_ai_usage.call_args.kwargs["credits"],
            1,
        )
        self.assertIsNone(
            _store.reserve_ai_usage.call_args.kwargs["max_daily_requests"]
        )
        self.assertEqual(
            _store.complete_ai_usage.call_args.kwargs["billed_credits"],
            1,
        )

        sent = provider.generate_mirror.await_args.kwargs["payload"]
        self.assertEqual(sent, payload)
        self.assertEqual(
            len(
                json.dumps(
                    sent,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                )
            ),
            len(serialized),
        )

    async def test_ec_2_service_rejects_tampered_companion_values_before_metering(self):
        base = self.valid_payload()
        cases = {
            "daily_goal": {"daily_word_goal": "ten"},
            "learning_stage": {"learning_stage": "invented_progress"},
            "active_block": {"has_active_block": "yes"},
            "compact_policy": {
                "compact_reply_policy": {
                    **base["compact_reply_policy"],
                    "max_next_steps": 2,
                }
            },
        }
        for name, mutation in cases.items():
            with self.subTest(tampering=name):
                payload = dict(base)
                if name == "compact_policy":
                    payload.update(mutation)
                else:
                    payload["learner_context"] = {
                        **base["learner_context"],
                        **mutation,
                    }
                service, store, provider, settings = self.service_fixture(
                    max_provider_input_chars=12000
                )
                settings.assert_runtime_ready.side_effect = RuntimeError(
                    "metering boundary reached"
                )
                try:
                    await service.ask_mirror(user_id=608, payload=payload)
                except ValueError:
                    pass
                except RuntimeError as exc:
                    self.fail(
                        "tampered companion input reached metering readiness: "
                        f"{exc}"
                    )
                else:
                    self.fail("tampered companion input was not rejected")

                settings.assert_runtime_ready.assert_not_called()
                store.reserve_ai_usage.assert_not_called()
                provider.generate_mirror.assert_not_awaited()


class LearningCompanionPromptContractTest(unittest.TestCase):
    def test_ac_7_runtime_uses_exact_mirror_v6_contract_and_preserves_schema(self):
        path = ROOT / "prompts/mirror-v6.txt"
        self.assertTrue(path.is_file(), "missing reviewed Mirror V6 prompt contract")
        reviewed = path.read_text(encoding="utf-8")
        if reviewed.endswith("\n"):
            reviewed = reviewed[:-1]
        self.assertEqual(ai_tutor.MIRROR_INSTRUCTIONS, reviewed)

        normalized = " ".join(reviewed.casefold().split())
        for required in (
            "learner_context",
            "compact_reply_policy",
            "learning_stage",
            "safety_envelope",
            "is_continuation",
            "answer the question directly",
            "one thought per sentence",
            "avoid generic praise",
            "avoid report-style restatement",
            "at most one concrete follow-up question",
            "at most one next step",
            "direct",
            "friendly",
            "💡",
            "📌",
            "👉",
            "internal analysis",
            "use relevant recent dialogue naturally",
            "answer the current question directly",
            "do not claim context is missing when it is present",
        ):
            with self.subTest(prompt_marker=required):
                self.assertIn(required, normalized)
        self.assertRegex(normalized, r"never (?:invent|fabricate).{0,40}progress")
        self.assertEqual(
            set(ai_tutor.MIRROR_RESPONSE_SCHEMA["required"]),
            {
                "answer_ru",
                "evidence_ru",
                "interpretation_ru",
                "language_items",
                "examples",
                "next_step_ru",
            },
        )


if __name__ == "__main__":
    unittest.main()
