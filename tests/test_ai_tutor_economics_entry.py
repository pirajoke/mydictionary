import inspect
import os
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, MagicMock, Mock, patch


os.environ.setdefault("BOT_TOKEN", "123456:TESTTOKEN")
os.environ.setdefault("ALLOWED_USER_ID", "1")
os.environ.setdefault("ALLOW_SQLITE_DEV", "true")

import bot
from mydictionary.localization import (
    INTERFACE_LOCALES,
    billing_product_display_copy,
    catalog_is_complete,
    translate,
)


AI_CONSENT_VERSION = "ai-processing-2026-08-09"
AI_PROCESSING_NOTICE = (
    "AI Tutor sends the current question and grounded learning context only "
    "after explicit learner consent."
)
ECONOMICS_COPY_KEYS = (
    "ai_tutor_economics_intro",
    "ai_tutor_economics_balance",
    "ai_tutor_economics_balance_unavailable",
    "ai_tutor_economics_policy",
    "ai_tutor_economics_purchase_unavailable",
    "ai_tutor_action_start_lesson",
    "ai_tutor_general_ask_prompt",
)


def ai_settings(*, enabled=True):
    return SimpleNamespace(
        enabled=enabled,
        initial_credits=40,
        consent_version=AI_CONSENT_VERSION,
        processing_notice=AI_PROCESSING_NOTICE,
    )


def billing_settings(*, enabled):
    return SimpleNamespace(enabled=enabled, terms_version="stars-terms-v1")


def canary_settings(*, enabled=False, owner_id=None):
    return SimpleNamespace(
        enabled=enabled,
        allows_user=lambda user_id: owner_id is not None and user_id == owner_id,
    )


def admitted_profile():
    return {
        "role": "learner",
        "access_status": "active",
        "onboarding_completed_at": "2026-08-23T00:00:00+00:00",
        "active_lang": "ja",
        "active_pack_id": "ja-basics-100",
        "learning_goal": "travel",
        "daily_word_goal": 10,
    }


def mirror_profile():
    return {
        "mirror_capabilities_version": "mirror-capabilities-v2",
        "mirror_capabilities_text": "I explain language and grounded progress.",
        "mirror_persona_guidance": "Answer as a careful language teacher.",
        "mirror_safety_envelope_checksum": "a" * 64,
    }


ONE_TIME_PRODUCTS = (
    {
        "product_id": "ai-mini",
        "title": "Мини",
        "description": "20 AI-кредитов для знакомства с репетитором",
        "credits": 20,
        "price_xtr": 69,
        "billing_mode": "one_time",
        "status": "active",
    },
    {
        "product_id": "ai-value",
        "title": "Выгодно",
        "description": "150 AI-кредитов для регулярной практики",
        "credits": 150,
        "price_xtr": 319,
        "billing_mode": "one_time",
        "status": "active",
    },
)
HIDDEN_PRODUCTS = (
    {
        "product_id": "ai-monthly",
        "title": "Месяц",
        "description": "100 AI-кредитов каждые 30 дней",
        "credits": 100,
        "price_xtr": 229,
        "billing_mode": "subscription",
        "status": "active",
    },
    {
        "product_id": "ai-draft",
        "title": "Draft package",
        "description": "Must not be public",
        "credits": 999,
        "price_xtr": 1,
        "billing_mode": "one_time",
        "status": "draft",
    },
)


class TutorEconomicsSurface:
    def __init__(self, *, locale="fr", user_id=987654321, active_block=False):
        self.user_data = {"interface_locale": locale}
        if active_block:
            bot.reset_block_state(
                self.user_data,
                list(range(10)),
                "ja",
                "food",
                pack_id="ja-basics-100",
            )
        self.message = SimpleNamespace(
            chat_id=user_id,
            text="",
            reply_text=AsyncMock(),
            reply_voice=AsyncMock(),
        )
        self.query = SimpleNamespace(
            data="aitutor:ask",
            answer=AsyncMock(),
            edit_message_text=AsyncMock(),
            edit_message_reply_markup=AsyncMock(),
            message=self.message,
        )
        self.update = SimpleNamespace(
            callback_query=None,
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

    def use_callback(self, data):
        self.query.data = data
        self.update.callback_query = self.query


def reply_payload(surface):
    call = surface.message.reply_text.await_args
    return call.args[0], call.kwargs.get("reply_markup")


def buttons(markup):
    if markup is None:
        return []
    return [button for row in markup.inline_keyboard for button in row]


class AITutorEconomicsScreenTest(unittest.IsolatedAsyncioTestCase):
    async def _open(
        self,
        surface,
        *,
        checkout_enabled,
        balance=17,
        balance_error=None,
        products=ONE_TIME_PRODUCTS + HIDDEN_PRODUCTS,
        catalog_error=None,
    ):
        store = MagicMock()
        if balance_error is None:
            store.ai_usage_summary.return_value = {"available_credits": balance}
        else:
            store.ai_usage_summary.side_effect = balance_error
        service = MagicMock()
        if catalog_error is None:
            service.active_products.return_value = list(products)
        else:
            service.active_products.side_effect = catalog_error
        provider = MagicMock()
        with (
            patch.object(bot, "AI_SETTINGS", ai_settings()),
            patch.object(
                bot,
                "BILLING_SETTINGS",
                billing_settings(enabled=checkout_enabled),
            ),
            patch.object(
                bot,
                "STARS_PRODUCTION_CANARY_SETTINGS",
                canary_settings(),
            ),
            patch.object(bot, "get_store", return_value=store),
            patch.object(bot, "get_billing_service", return_value=service),
            patch.object(bot, "get_ai_tutor_service", return_value=provider),
            patch.object(bot, "handle_mirror_question", new=AsyncMock()) as mirror,
        ):
            await bot.cmd_ai.__wrapped__(surface.update, surface.context)
        return store, service, provider, mirror

    async def test_ac1_no_block_shows_localized_balance_policy_read_only_packs_and_actions(self):
        surface = TutorEconomicsSurface(locale="fr")
        store, service, provider, mirror = await self._open(
            surface,
            checkout_enabled=False,
        )

        self.assertEqual(surface.message.reply_text.await_count, 1)
        text, markup = reply_payload(surface)
        self.assertIn(
            translate("ai_tutor_economics_balance", "fr", balance=17), text
        )
        self.assertIn(translate("ai_tutor_economics_policy", "fr"), text)
        self.assertIn(
            translate("ai_tutor_economics_purchase_unavailable", "fr"), text
        )
        for product in ONE_TIME_PRODUCTS:
            title, _description = billing_product_display_copy(
                product["product_id"],
                "fr",
                title=product["title"],
                description=product["description"],
                credits=product["credits"],
            )
            self.assertIn(title, text)
            self.assertIn(str(product["credits"]), text)
            self.assertIn(str(product["price_xtr"]), text)
        self.assertNotIn("Mensuel", text)
        self.assertNotIn("Draft package", text)

        callback_data = [button.callback_data for button in buttons(markup)]
        self.assertEqual(callback_data, ["aitutor:ask", "aitutor:start"])
        self.assertFalse(any(data.startswith("buy:") for data in callback_data))
        self.assertNotIn(str(surface.update.effective_user.id), text)
        self.assertTrue(
            all(str(surface.update.effective_user.id) not in data for data in callback_data)
        )
        self.assertTrue(all(len(data.encode("utf-8")) <= 64 for data in callback_data))

        store.ai_usage_summary.assert_called_once_with(
            surface.update.effective_user.id,
            initial_credits=40,
        )
        store.has_consent.assert_not_called()
        store.grant_consent.assert_not_called()
        store.reserve_ai_usage.assert_not_called()
        store.append_mirror_exchange.assert_not_called()
        service.active_products.assert_called_once()
        service.create_order.assert_not_called()
        provider.assert_not_called()
        mirror.assert_not_awaited()
        self.assertNotIn("pending_ai_consent", surface.user_data)
        self.assertNotIn(bot.PENDING_AI_TUTOR_KEY, surface.user_data)

    async def test_ac2_checkout_enabled_uses_exact_existing_buy_callbacks_and_economics(self):
        surface = TutorEconomicsSurface(locale="en")
        await self._open(surface, checkout_enabled=True)

        text, markup = reply_payload(surface)
        rendered_buttons = buttons(markup)
        product_buttons = [
            button for button in rendered_buttons if button.callback_data.startswith("buy:")
        ]
        self.assertEqual(
            [button.callback_data for button in product_buttons],
            ["buy:ai-mini", "buy:ai-value"],
        )
        for button, product in zip(product_buttons, ONE_TIME_PRODUCTS, strict=True):
            title, _description = billing_product_display_copy(
                product["product_id"],
                "en",
                title=product["title"],
                description=product["description"],
                credits=product["credits"],
            )
            self.assertIn(title, button.text)
            self.assertIn(str(product["credits"]), button.text)
            self.assertIn(str(product["price_xtr"]), button.text)
            self.assertIn("⭐", button.text)
            self.assertLessEqual(len(button.callback_data.encode("utf-8")), 64)
        self.assertNotIn("Monthly", text)
        self.assertFalse(any(button.callback_data == "buy:ai-monthly" for button in rendered_buttons))
        self.assertFalse(any(button.callback_data == "buy:ai-draft" for button in rendered_buttons))

    async def test_ac2_group_chat_uses_effective_learner_identity_not_chat_id(self):
        learner_id = 7001
        group_chat_id = -1009876543210
        surface = TutorEconomicsSurface(locale="en", user_id=learner_id)
        surface.message.chat_id = group_chat_id
        surface.update.effective_chat.id = group_chat_id
        store = MagicMock()
        store.ai_usage_summary.return_value = {"available_credits": 6}
        service = MagicMock()
        service.active_products.return_value = [dict(ONE_TIME_PRODUCTS[0])]
        provider = MagicMock()
        with (
            patch.object(bot, "AI_SETTINGS", ai_settings()),
            patch.object(
                bot,
                "BILLING_SETTINGS",
                billing_settings(enabled=False),
            ),
            patch.object(
                bot,
                "STARS_PRODUCTION_CANARY_SETTINGS",
                canary_settings(enabled=True, owner_id=learner_id),
            ),
            patch.object(bot, "get_store", return_value=store),
            patch.object(bot, "get_billing_service", return_value=service),
            patch.object(bot, "get_ai_tutor_service", return_value=provider),
        ):
            await bot.cmd_ai.__wrapped__(surface.update, surface.context)

        store.ai_usage_summary.assert_called_once_with(
            learner_id,
            initial_credits=40,
        )
        service.active_products.assert_called_once_with(user_id=learner_id)
        service.create_order.assert_not_called()
        provider.assert_not_called()
        self.assertEqual(surface.message.reply_text.await_count, 1)
        text, markup = reply_payload(surface)
        self.assertIn(
            translate("ai_tutor_economics_balance", "en", balance=6), text
        )
        rendered_buttons = buttons(markup)
        self.assertEqual(
            [button.callback_data for button in rendered_buttons],
            ["aitutor:ask", "aitutor:start", "buy:ai-mini"],
        )
        rendered_surface = "\n".join(
            [text, *[button.text for button in rendered_buttons]]
        )
        callback_surface = "\n".join(
            button.callback_data for button in rendered_buttons
        )
        for private_identifier in (str(learner_id), str(group_chat_id)):
            self.assertNotIn(private_identifier, rendered_surface)
            self.assertNotIn(private_identifier, callback_surface)

    async def test_ac1_malformed_balance_is_unavailable_not_invented(self):
        for balance, balance_error in (
            (None, None),
            ("not-a-number", None),
            (-1, None),
            (17, RuntimeError("balance unavailable")),
        ):
            with self.subTest(balance=balance, balance_error=balance_error):
                surface = TutorEconomicsSurface(locale="de")
                await self._open(
                    surface,
                    checkout_enabled=False,
                    balance=balance,
                    balance_error=balance_error,
                    products=(),
                )
                text, _markup = reply_payload(surface)
                self.assertIn(
                    translate("ai_tutor_economics_balance_unavailable", "de"),
                    text,
                )
                self.assertNotIn(
                    translate("ai_tutor_economics_balance", "de", balance=0),
                    text,
                )

    async def test_ac5_catalog_failure_keeps_free_screen_and_never_shows_buy_callback(self):
        surface = TutorEconomicsSurface(locale="ja")
        store, service, provider, mirror = await self._open(
            surface,
            checkout_enabled=True,
            catalog_error=RuntimeError("catalog unavailable"),
        )
        text, markup = reply_payload(surface)
        self.assertIn(
            translate("ai_tutor_economics_balance", "ja", balance=17), text
        )
        self.assertIn(
            translate("ai_tutor_economics_purchase_unavailable", "ja"), text
        )
        callback_data = [button.callback_data for button in buttons(markup)]
        self.assertEqual(callback_data, ["aitutor:ask", "aitutor:start"])
        store.reserve_ai_usage.assert_not_called()
        service.create_order.assert_not_called()
        provider.assert_not_called()
        mirror.assert_not_awaited()

    async def test_edge_ai_disabled_keeps_existing_message_and_does_not_read_catalog(self):
        surface = TutorEconomicsSurface(locale="es")
        store = MagicMock()
        service = MagicMock()
        with (
            patch.object(bot, "AI_SETTINGS", ai_settings(enabled=False)),
            patch.object(bot, "get_store", return_value=store),
            patch.object(bot, "get_billing_service", return_value=service),
        ):
            await bot.cmd_ai.__wrapped__(surface.update, surface.context)
        surface.message.reply_text.assert_awaited_once_with(
            translate("ai_disabled", "es")
        )
        store.ai_usage_summary.assert_not_called()
        service.active_products.assert_not_called()

    async def test_ac4_active_block_keeps_four_session_bound_lesson_actions(self):
        surface = TutorEconomicsSurface(locale="ru", active_block=True)
        self.assertIsNotNone(bot.active_tutor_context(surface.user_data))
        await self._open(
            surface,
            checkout_enabled=False,
            products=(),
        )
        _text, markup = reply_payload(surface)
        session = surface.user_data["block_session"]
        callback_data = [button.callback_data for button in buttons(markup)]
        for action in ("vocabulary", "mistakes", "progress", "ask"):
            self.assertIn(f"bait:{session}:{action}", callback_data)
        self.assertNotIn("aitutor:start", callback_data)
        self.assertNotIn("aitutor:ask", callback_data)

    async def test_ac4_stale_malformed_or_incomplete_session_shows_only_general_actions(self):
        invalid_states = (
            {
                "block_session": "stale-session",
                "block_pack_id": "missing-pack",
                "block_lang": "ja",
                "block_all_indices": [0],
            },
            {
                "block_session": 12345,
                "block_pack_id": None,
                "block_lang": None,
                "block_all_indices": "not-a-list",
            },
            {
                "block_session": "incomplete-session",
                "block_pack_id": "ja-basics-100",
                "block_lang": "ja",
                "block_all_indices": [],
            },
        )
        for invalid_state in invalid_states:
            with self.subTest(invalid_state=invalid_state):
                surface = TutorEconomicsSurface(locale="en")
                surface.user_data.update(invalid_state)
                self.assertIsNone(bot.active_tutor_context(surface.user_data))

                await self._open(
                    surface,
                    checkout_enabled=False,
                    products=(),
                )

                _text, markup = reply_payload(surface)
                callback_data = [
                    button.callback_data for button in buttons(markup)
                ]
                self.assertEqual(
                    callback_data,
                    ["aitutor:ask", "aitutor:start"],
                )
                self.assertFalse(
                    any(data.startswith("bait:") for data in callback_data)
                )


class AITutorGeneralChatTest(unittest.IsolatedAsyncioTestCase):
    async def test_ac3_general_ask_replaces_one_ten_minute_pending_state_without_ai(self):
        surface = TutorEconomicsSurface(locale="ru")
        surface.use_callback("aitutor:ask")
        mirror = AsyncMock()
        provider = MagicMock()
        with (
            patch.object(bot, "AI_SETTINGS", ai_settings()),
            patch.object(bot.time, "time", side_effect=(1_000, 1_001)),
            patch.object(bot, "handle_mirror_question", new=mirror),
            patch.object(bot, "get_ai_tutor_service", return_value=provider),
        ):
            await bot.ai_tutor_entry_cb.__wrapped__(surface.update, surface.context)
            first = dict(surface.user_data[bot.PENDING_AI_TUTOR_KEY])
            surface.query.answer.reset_mock()
            surface.message.reply_text.reset_mock()
            await bot.ai_tutor_entry_cb.__wrapped__(surface.update, surface.context)

        self.assertEqual(first["request_kind"], "mirror_chat")
        self.assertEqual(first["expires_at"], 1_600)
        self.assertEqual(
            surface.user_data[bot.PENDING_AI_TUTOR_KEY],
            {"request_kind": "mirror_chat", "expires_at": 1_601},
        )
        surface.query.answer.assert_awaited_once_with()
        surface.message.reply_text.assert_awaited_once_with(
            translate("ai_tutor_general_ask_prompt", "ru")
        )
        mirror.assert_not_awaited()
        provider.assert_not_called()

    async def test_ac3_valid_pending_routes_next_text_once_through_ordinary_mirror(self):
        surface = TutorEconomicsSurface(locale="fr")
        surface.message.text = "Explique-moi la répétition espacée."
        surface.user_data[bot.PENDING_AI_TUTOR_KEY] = {
            "request_kind": "mirror_chat",
            "expires_at": 1_600,
        }
        mirror = AsyncMock()
        with (
            patch.object(bot.time, "time", return_value=1_001),
            patch.object(bot, "handle_mirror_question", new=mirror),
        ):
            await bot.mirror_text_handler.__wrapped__(surface.update, surface.context)
        mirror.assert_awaited_once_with(
            surface.update,
            surface.context,
            question="Explique-moi la répétition espacée.",
        )
        self.assertNotIn(bot.PENDING_AI_TUTOR_KEY, surface.user_data)

        mirror.reset_mock()
        surface.message.text = "Et donne-moi un exemple."
        with patch.object(bot, "handle_mirror_question", new=mirror):
            await bot.mirror_text_handler.__wrapped__(surface.update, surface.context)
        mirror.assert_awaited_once_with(
            surface.update,
            surface.context,
            question="Et donne-moi un exemple.",
        )

    async def test_ac3_expired_or_malformed_pending_is_removed_without_ai_or_spend(self):
        cases = (
            {"request_kind": "mirror_chat", "expires_at": 999},
            {"request_kind": "other", "expires_at": 1_600},
            {"expires_at": "bad"},
            "malformed",
        )
        for pending in cases:
            with self.subTest(pending=pending):
                surface = TutorEconomicsSurface(locale="en")
                surface.message.text = "This must not be billed."
                surface.user_data[bot.PENDING_AI_TUTOR_KEY] = pending
                mirror = AsyncMock()
                service = MagicMock()
                store = MagicMock()
                with (
                    patch.object(bot.time, "time", return_value=1_001),
                    patch.object(bot, "handle_mirror_question", new=mirror),
                    patch.object(bot, "get_ai_tutor_service", return_value=service),
                    patch.object(bot, "get_store", return_value=store),
                ):
                    await bot.mirror_text_handler.__wrapped__(
                        surface.update, surface.context
                    )
                self.assertNotIn(bot.PENDING_AI_TUTOR_KEY, surface.user_data)
                mirror.assert_not_awaited()
                service.assert_not_called()
                store.reserve_ai_usage.assert_not_called()

    async def test_ac3_malformed_legacy_pending_needs_a_genuinely_active_block(self):
        cases = (
            (
                {},
                {"block_session": None, "expires_at": 1_600},
            ),
            (
                {
                    "block_session": "stale-session",
                    "block_pack_id": "missing-pack",
                    "block_lang": "ja",
                    "block_all_indices": [0],
                },
                {"block_session": "stale-session", "expires_at": 1_600},
            ),
        )
        for user_state, pending in cases:
            with self.subTest(user_state=user_state, pending=pending):
                surface = TutorEconomicsSurface(locale="en")
                surface.user_data.update(user_state)
                self.assertIsNone(bot.active_tutor_context(surface.user_data))
                surface.user_data[bot.PENDING_AI_TUTOR_KEY] = pending
                surface.message.text = "This malformed state must stay free."
                mirror = AsyncMock()
                provider = MagicMock()
                store = MagicMock()
                with (
                    patch.object(bot.time, "time", return_value=1_001),
                    patch.object(bot, "handle_mirror_question", new=mirror),
                    patch.object(
                        bot,
                        "get_ai_tutor_service",
                        return_value=provider,
                    ),
                    patch.object(bot, "get_store", return_value=store),
                ):
                    await bot.mirror_text_handler.__wrapped__(
                        surface.update,
                        surface.context,
                    )

                surface.message.reply_text.assert_awaited_once_with(
                    translate("ai_tutor_pending_stale", "en")
                )
                self.assertNotIn(bot.PENDING_AI_TUTOR_KEY, surface.user_data)
                mirror.assert_not_awaited()
                provider.assert_not_called()
                store.ai_usage_summary.assert_not_called()
                store.reserve_ai_usage.assert_not_called()

    async def test_ac3_exercise_answer_has_priority_over_general_pending(self):
        surface = TutorEconomicsSurface(locale="en", active_block=True)
        surface.message.text = "answer"
        surface.user_data.update(
            {
                bot.PENDING_AI_TUTOR_KEY: {
                    "request_kind": "mirror_chat",
                    "expires_at": 1_600,
                },
                "type_idx": 0,
                "block_typing": False,
            }
        )
        typed = AsyncMock()
        mirror = AsyncMock()
        with (
            patch.object(bot.time, "time", return_value=1_001),
            patch.object(bot, "handle_type_answer", new=typed),
            patch.object(bot, "handle_mirror_question", new=mirror),
        ):
            await bot.mirror_text_handler.__wrapped__(surface.update, surface.context)
        typed.assert_awaited_once_with(surface.update, surface.context)
        mirror.assert_not_awaited()
        self.assertIn(bot.PENDING_AI_TUTOR_KEY, surface.user_data)

    async def test_ac3_ai_question_without_block_is_ordinary_mirror_but_block_is_compact(self):
        for active_block, expected_kwargs in (
            (False, {"question": "How should I study?"}),
            (
                True,
                {
                    "question": "How should I study?",
                    "communication_mode": "brief",
                    "answer_depth": "compact",
                },
            ),
        ):
            with self.subTest(active_block=active_block):
                surface = TutorEconomicsSurface(
                    locale="en", active_block=active_block
                )
                surface.context.args = ["How", "should", "I", "study?"]
                mirror = AsyncMock()
                with (
                    patch.object(bot, "AI_SETTINGS", ai_settings()),
                    patch.object(bot, "get_store", return_value=MagicMock()),
                    patch.object(bot, "handle_mirror_question", new=mirror),
                ):
                    await bot.cmd_ai.__wrapped__(surface.update, surface.context)
                mirror.assert_awaited_once_with(
                    surface.update, surface.context, **expected_kwargs
                )

    async def test_ac3_missing_consent_persists_mirror_chat_and_acceptance_resumes_once(self):
        surface = TutorEconomicsSurface(locale="en")
        question = "Explain spaced repetition for my progress."
        store = MagicMock()
        store.product_profile.return_value = admitted_profile()
        store.has_consent.return_value = False
        mirror = AsyncMock()
        with (
            patch.object(bot, "AI_SETTINGS", ai_settings()),
            patch.object(bot, "get_store", return_value=store),
            patch.object(bot, "get_bot_profile", return_value=mirror_profile()),
            patch.object(
                bot,
                "_mirror_preferences",
                return_value={"mode": "teacher", "depth": "deep", "level": "a2"},
            ),
            patch.object(
                bot,
                "_mirror_control_policy",
                return_value={
                    "enabled_modes": ["teacher"],
                    "default_mode": "teacher",
                    "mode_guidance": {"teacher": "Be useful."},
                },
            ),
            patch.object(bot, "classify_mirror_intent", return_value="learning"),
            patch.object(bot, "classify_mirror_task", return_value="explanation"),
            patch.object(bot, "direct_mirror_capability_greeting_locale", return_value=None),
            patch.object(bot, "direct_mirror_progress_locale", return_value=None),
        ):
            await bot.handle_mirror_question(
                surface.update,
                surface.context,
                question=question,
            )

        pending = surface.user_data["pending_ai_consent"]
        self.assertEqual(pending["request_kind"], "mirror_chat")
        self.assertEqual(pending["question"], question)
        self.assertIsNone(pending["block_session"])
        store.reserve_ai_usage.assert_not_called()

        surface.use_callback("aiconsent:accept")
        store.grant_consent.return_value = True
        with (
            patch.object(bot, "AI_SETTINGS", ai_settings()),
            patch.object(bot, "get_store", return_value=store),
            patch.object(bot, "handle_mirror_question", new=mirror),
            patch.object(bot.time, "time", return_value=pending["expires_at"] - 1),
        ):
            await bot.ai_consent_cb.__wrapped__(surface.update, surface.context)
        mirror.assert_awaited_once_with(
            surface.update,
            surface.context,
            question=question,
        )
        self.assertNotIn("pending_ai_consent", surface.user_data)

    async def test_ac4_start_action_uses_existing_topic_picker(self):
        surface = TutorEconomicsSurface(locale="zh")
        surface.use_callback("aitutor:start")
        pack = SimpleNamespace(label="Japanese basics", pack_id="ja-basics-100")
        topic_markup = object()
        with (
            patch.object(bot, "active_content_pack", return_value=pack),
            patch.object(bot, "build_topic_keyboard", return_value=topic_markup),
        ):
            await bot.ai_tutor_entry_cb.__wrapped__(surface.update, surface.context)
        surface.query.answer.assert_awaited_once_with()
        surface.message.reply_text.assert_awaited_once_with(
            f"📚 *{pack.label}*\n\n{translate('topic_prompt', 'zh')}",
            reply_markup=topic_markup,
            parse_mode="Markdown",
        )


class AITutorEconomicsContractTest(unittest.TestCase):
    def test_ac6_localization_registration_and_callback_privacy_contract(self):
        self.assertEqual(
            set(INTERFACE_LOCALES),
            {"en", "fr", "de", "ja", "ar", "zh", "ru", "es"},
        )
        self.assertTrue(catalog_is_complete())
        for locale in INTERFACE_LOCALES:
            with self.subTest(locale=locale):
                rendered = {
                    key: translate(
                        key,
                        locale,
                        **({"balance": 17} if key == "ai_tutor_economics_balance" else {}),
                    )
                    for key in ECONOMICS_COPY_KEYS
                }
                self.assertTrue(all(value.strip() for value in rendered.values()))
                self.assertNotIn("provider token", " ".join(rendered.values()).lower())

        source = inspect.getsource(bot.manual_polling)
        self.assertIn(
            'CallbackQueryHandler(ai_tutor_entry_cb, pattern=r"^aitutor:")',
            source,
        )
        for callback in (
            "aitutor:ask",
            "aitutor:start",
            "buy:ai-mini",
            "buy:ai-value",
        ):
            self.assertLessEqual(len(callback.encode("utf-8")), 64)
            self.assertNotRegex(callback, r"\d{6,}")


if __name__ == "__main__":
    unittest.main()
