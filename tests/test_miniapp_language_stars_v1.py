from __future__ import annotations

import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import tempfile
from types import SimpleNamespace
from urllib.parse import urlencode
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from sqlalchemy import func, select


os.environ.setdefault("BOT_TOKEN", "123456:TESTTOKEN_ABCDEFGHIJKLMNOP")
os.environ.setdefault("ALLOWED_USER_ID", "1")
os.environ.setdefault("ALLOW_SQLITE_DEV", "true")

import bot
from mydictionary import billing, miniapp
from mydictionary.admin import create_app
from mydictionary.billing import BillingConfigurationError, InvoiceOrder
from mydictionary.storage import (
    AIUsage,
    AIWallet,
    DatabaseStore,
    RateLimitBucket,
    User,
    UserPackEnrollment,
    UserProgress,
    WordProgress,
)
from ops import mydictionary_commercial_launch as commercial_launch
from ops import mydictionary_economics as economics


ROOT = Path(__file__).resolve().parents[1]
HTML_PATH = ROOT / "mydictionary/templates/miniapp.html"
CSS_PATH = ROOT / "mydictionary/static/miniapp.css"
JS_PATH = ROOT / "mydictionary/static/miniapp.js"
TOKEN = "123456:TESTTOKEN_ABCDEFGHIJKLMNOP"
MINIAPP_URL = "https://mydictionary.example.test/miniapp"
SAFE_USERNAME = "mydictionary_test_bot"
USER_ID = 912_345
OTHER_USER_ID = 912_346
CURRENT_PACK = "en-basics-100"
NEXT_PACK = "fr-basics-100"


def signed_init_data(*, user_id: int = USER_ID, auth_date: int = 1_800_000_000) -> str:
    fields = {
        "auth_date": str(auth_date),
        "query_id": "AAHdF6IQAAAAAN0XohDhrOrc",
        "user": json.dumps(
            {
                "id": user_id,
                "first_name": "Mila",
                "language_code": "fr",
                "username": "must-not-enter-response",
            },
            separators=(",", ":"),
        ),
    }
    data_check = "\n".join(f"{key}={fields[key]}" for key in sorted(fields))
    secret = hmac.new(b"WebAppData", TOKEN.encode(), hashlib.sha256).digest()
    fields["hash"] = hmac.new(
        secret,
        data_check.encode(),
        hashlib.sha256,
    ).hexdigest()
    return urlencode(fields)


def verified_user(user_id: int = USER_ID) -> dict[str, object]:
    return {
        "user_id": user_id,
        "display_name": "Mila",
        "language_code": "fr",
    }


def callback_update(user_id: int, data: str):
    message = SimpleNamespace(chat_id=user_id, reply_text=AsyncMock())
    query = SimpleNamespace(
        data=data,
        answer=AsyncMock(),
        edit_message_reply_markup=AsyncMock(),
        message=message,
    )
    update = SimpleNamespace(
        callback_query=query,
        effective_message=message,
        effective_user=SimpleNamespace(id=user_id, language_code="en"),
        effective_chat=SimpleNamespace(id=user_id, type="private"),
    )
    return update, query


class MiniAppLanguageSwitchHTTPContractTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="miniapp-switch-")
        self.store = DatabaseStore(
            f"sqlite:///{Path(self.temporary.name) / 'switch.sqlite3'}"
        )
        for user_id in (USER_ID, OTHER_USER_ID):
            self.store.ensure_user_id(user_id)
            with self.store.Session.begin() as session:
                learner = session.get(User, user_id)
                learner.access_status = "active"
                learner.privacy_status = "active"
                learner.native_language = "ru"
            self.store.activate_pack(
                user_id,
                pack_id=CURRENT_PACK,
                language="en",
                source="test",
            )

    def tearDown(self):
        self.store.close()
        self.temporary.cleanup()

    def app(self):
        return create_app(
            {
                "TESTING": True,
                "SECRET_KEY": "s" * 40,
                "ADMIN_USERNAME": "owner",
                "ADMIN_PASSWORD": "password",
                "MINIAPP_ENABLED": True,
                "MINIAPP_PUBLIC_URL": MINIAPP_URL,
                "MINIAPP_BOT_USERNAME": SAFE_USERNAME,
                "MINIAPP_AUTH_MAX_AGE_SECONDS": 300,
                "BOT_TOKEN_FILE": "/protected/bot-token",
                "TELEGRAM_STARS_ENABLED": False,
            },
            database_store=self.store,
        )

    def post_switch(self, pack_id: str, *, user_id: int = USER_ID):
        client = self.app().test_client()
        with patch.object(miniapp, "verify_init_data", return_value=verified_user(user_id)):
            return client.post(
                "/miniapp/api/active-pack",
                headers={"X-Telegram-Init-Data": signed_init_data(user_id=user_id)},
                json={"pack_id": pack_id},
            )

    def profile(self, user_id: int = USER_ID) -> tuple[str | None, str]:
        value = self.store.product_profile(user_id)
        return value["active_pack_id"], value["active_lang"]

    def mutation_snapshot(self, user_id: int = USER_ID) -> dict[str, object]:
        with self.store.Session() as session:
            progress = session.get(UserProgress, user_id)
            return {
                "active_pack_id": progress.active_pack_id,
                "active_lang": progress.active_lang,
                "updated_at": progress.updated_at,
                "enrollments": session.scalar(
                    select(func.count()).select_from(UserPackEnrollment).where(
                        UserPackEnrollment.telegram_user_id == user_id
                    )
                ),
                "word_progress": session.scalar(
                    select(func.count()).select_from(WordProgress).where(
                        WordProgress.telegram_user_id == user_id
                    )
                ),
                "wallets": session.scalar(
                    select(func.count()).select_from(AIWallet).where(
                        AIWallet.telegram_user_id == user_id
                    )
                ),
                "usage": session.scalar(
                    select(func.count()).select_from(AIUsage).where(
                        AIUsage.telegram_user_id == user_id
                    )
                ),
            }

    def test_ac_1_ac_2_authenticated_switch_commits_exact_pack_and_returns_fresh_safe_bootstrap(self):
        unrelated_before = self.mutation_snapshot(OTHER_USER_ID)

        response = self.post_switch(NEXT_PACK)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["Cache-Control"], "no-store")
        payload = response.get_json()
        self.assertEqual(self.profile(), (NEXT_PACK, "fr"))
        self.assertEqual(self.mutation_snapshot(OTHER_USER_ID), unrelated_before)
        self.assertEqual(
            sum(language["current"] is True for language in payload["languages"]),
            1,
        )
        selected = next(language for language in payload["languages"] if language["current"])
        self.assertEqual(selected["switch_value"], NEXT_PACK)
        self.assertEqual(selected["direction"], "ltr")
        self.assertGreater(selected["word_count"], 0)
        rendered = json.dumps(payload, ensure_ascii=False)
        for forbidden in (
            str(USER_ID),
            "must-not-enter-response",
            "telegram_user_id",
            "username",
            "init_data",
            "BOT_TOKEN",
        ):
            self.assertNotIn(forbidden, rendered)

    def test_ec_2_current_pack_is_idempotent_and_two_commits_leave_last_pack_selected(self):
        before = self.mutation_snapshot()
        same = self.post_switch(CURRENT_PACK)
        self.assertEqual(same.status_code, 200)
        self.assertEqual(self.mutation_snapshot(), before)

        first = self.post_switch(NEXT_PACK)
        last = self.post_switch("ja-basics-100")
        self.assertEqual((first.status_code, last.status_code), (200, 200))
        self.assertEqual(self.profile(), ("ja-basics-100", "ja"))
        selected = [
            language["switch_value"]
            for language in last.get_json()["languages"]
            if language["current"]
        ]
        self.assertEqual(selected, ["ja-basics-100"])

    def test_err_1_auth_body_access_and_pack_failures_are_fixed_and_mutation_free(self):
        client = self.app().test_client()
        before = self.mutation_snapshot()

        for headers in ({}, {"X-Telegram-Init-Data": "bad"}):
            with self.subTest(kind="authentication", headers=bool(headers)):
                response = client.post(
                    "/miniapp/api/active-pack",
                    headers=headers,
                    json={"pack_id": NEXT_PACK},
                )
                self.assertEqual(response.status_code, 401)
                self.assertEqual(response.get_json(), {"error": "authentication_failed"})
                self.assertEqual(response.headers["Cache-Control"], "no-store")

        with patch.object(miniapp, "verify_init_data", return_value=verified_user()):
            invalid_requests = (
                ({"data": "not-json", "content_type": "application/json"}, "malformed"),
                ({"json": {}}, "missing"),
                ({"json": {"pack_id": "unknown-pack"}}, "unknown"),
                ({"json": {"pack_id": "x" * 65}}, "oversized"),
                ({"json": {"pack_id": "../../private"}}, "not-allowlisted"),
            )
            for request_kwargs, label in invalid_requests:
                with self.subTest(kind=label):
                    response = client.post(
                        "/miniapp/api/active-pack",
                        headers={"X-Telegram-Init-Data": signed_init_data()},
                        **request_kwargs,
                    )
                    self.assertEqual(response.status_code, 400)
                    self.assertEqual(response.get_json(), {"error": "invalid_request"})
                    self.assertEqual(response.headers["Cache-Control"], "no-store")

        self.assertEqual(self.mutation_snapshot(), before)

    def test_err_1_incompatible_and_erased_learner_fail_closed_without_mutation(self):
        with self.store.Session.begin() as session:
            learner = session.get(User, USER_ID)
            learner.native_language = "en"
        before = self.mutation_snapshot()
        incompatible = self.post_switch("en-basics-100")
        self.assertEqual(incompatible.status_code, 400)
        self.assertEqual(incompatible.get_json(), {"error": "invalid_request"})
        self.assertEqual(self.mutation_snapshot(), before)

        with self.store.Session.begin() as session:
            learner = session.get(User, USER_ID)
            learner.privacy_status = "erased"
        erased_before = self.mutation_snapshot()
        denied = self.post_switch(NEXT_PACK)
        self.assertEqual(denied.status_code, 403)
        self.assertEqual(denied.get_json(), {"error": "access_denied"})
        self.assertEqual(self.mutation_snapshot(), erased_before)

    def test_err_2_database_or_bootstrap_failure_is_fixed_503_and_rolls_back(self):
        before = self.mutation_snapshot()
        client = self.app().test_client()
        with (
            patch.object(miniapp, "verify_init_data", return_value=verified_user()),
            patch.object(
                miniapp,
                "build_bootstrap",
                side_effect=RuntimeError("PRIVATE database url"),
            ),
        ):
            response = client.post(
                "/miniapp/api/active-pack",
                headers={"X-Telegram-Init-Data": signed_init_data()},
                json={"pack_id": NEXT_PACK},
            )

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.headers["Cache-Control"], "no-store")
        self.assertEqual(response.get_json(), {"error": "temporarily_unavailable"})
        self.assertNotIn("PRIVATE", response.get_data(as_text=True))
        self.assertEqual(self.mutation_snapshot(), before)

    def test_ec_2_err_2_interleaved_newer_commit_survives_failed_older_response_and_rollback(self):
        real_activate = self.store.activate_pack
        activation_calls = []

        def interleaving_activation(user_id, *, pack_id, language, source):
            activation_calls.append(pack_id)
            if pack_id == NEXT_PACK:
                real_activate(
                    USER_ID,
                    pack_id="ja-basics-100",
                    language="ja",
                    source="newer-switch",
                )
                raise RuntimeError("PRIVATE uncertain older activation failure")
            return real_activate(
                user_id,
                pack_id=pack_id,
                language=language,
                source=source,
            )

        client = self.app().test_client()
        with (
            patch.object(miniapp, "verify_init_data", return_value=verified_user()),
            patch.object(
                self.store,
                "activate_pack",
                side_effect=interleaving_activation,
            ),
        ):
            response = client.post(
                "/miniapp/api/active-pack",
                headers={"X-Telegram-Init-Data": signed_init_data()},
                json={"pack_id": NEXT_PACK},
            )

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.headers["Cache-Control"], "no-store")
        self.assertEqual(response.get_json(), {"error": "temporarily_unavailable"})
        self.assertEqual(
            self.profile(),
            ("ja-basics-100", "ja"),
            "an older failed response must never restore over a newer committed switch",
        )
        rendered = response.get_data(as_text=True).casefold()
        self.assertNotIn("private", rendered)
        self.assertNotIn("mutation_free", rendered)
        self.assertNotIn("unchanged", rendered)
        self.assertEqual(activation_calls, [NEXT_PACK])
        self.assertNotIn(CURRENT_PACK, activation_calls, "must not issue a stale restore")

    def test_err_1_switch_post_uses_persistent_per_user_rate_limit_before_mutation(self):
        client = self.app().test_client()

        def verify(value, **_kwargs):
            return verified_user(USER_ID if value == "user-a" else OTHER_USER_ID)

        responses = []
        with patch.object(miniapp, "verify_init_data", side_effect=verify):
            for index in range(12):
                responses.append(
                    client.post(
                        "/miniapp/api/active-pack",
                        headers={"X-Telegram-Init-Data": "user-a"},
                        json={
                            "pack_id": NEXT_PACK if index % 2 == 0 else "ja-basics-100"
                        },
                    )
                )
                if responses[-1].status_code == 429:
                    break

            self.assertEqual(responses[0].status_code, 200)
            self.assertIn(429, [response.status_code for response in responses])
            denied = next(response for response in responses if response.status_code == 429)
            before_denied_retry = self.mutation_snapshot()
            self.assertEqual(denied.get_json(), {"error": "rate_limited"})
            self.assertEqual(denied.headers["Cache-Control"], "no-store")
            self.assertRegex(denied.headers.get("Retry-After", ""), r"^[1-9]\d*$")

            persisted = self.app().test_client().post(
                "/miniapp/api/active-pack",
                headers={"X-Telegram-Init-Data": "user-a"},
                json={"pack_id": NEXT_PACK},
            )
            independent = self.app().test_client().post(
                "/miniapp/api/active-pack",
                headers={"X-Telegram-Init-Data": "user-b"},
                json={"pack_id": NEXT_PACK},
            )

        self.assertEqual(persisted.status_code, 429)
        self.assertEqual(self.mutation_snapshot(), before_denied_retry)
        self.assertEqual(independent.status_code, 200)
        with self.store.Session() as session:
            self.assertGreater(
                session.scalar(select(func.count()).select_from(RateLimitBucket)),
                0,
            )


class MiniAppLanguageSwitchFrontendContractTest(unittest.TestCase):
    def setUp(self):
        self.html = HTML_PATH.read_text(encoding="utf-8")
        self.css = CSS_PATH.read_text(encoding="utf-8")
        self.js = JS_PATH.read_text(encoding="utf-8")

    def test_ac_1_ec_3_each_language_uses_accessible_selected_disabled_switch(self):
        combined = f"{self.html}\n{self.js}"
        required = (
            'role="switch"',
            'aria-checked',
            "language.current",
            "switch.disabled",
            "language.switch_value",
            "language.direction",
            "language.word_count",
            "copy.language_current",
        )
        self.assertEqual([token for token in required if token not in combined], [])
        self.assertIn('aria-live="polite"', self.html)

    def test_ac_2_ec_2_err_2_post_is_authenticated_pending_retry_and_stale_response_safe(self):
        required = (
            '"/miniapp/api/active-pack"',
            'method: "POST"',
            '"X-Telegram-Init-Data"',
            '"Content-Type": "application/json"',
            'cache: "no-store"',
            "aria-busy",
            "language_switch_pending",
            "language_switch_error",
            "language_switch_retry",
        )
        missing_tokens = [token for token in required if token not in self.js]
        missing_copy = [
            f"{locale}:{key}"
            for locale, copy in miniapp.MINIAPP_COPY.items()
            for key in (
                "language_switch_pending",
                "language_switch_error",
                "language_switch_retry",
            )
            if not copy.get(key, "").strip()
        ]
        self.assertEqual(
            {"tokens": missing_tokens, "copy": missing_copy},
            {"tokens": [], "copy": []},
        )

    def test_ec_3_rtl_320_focus_reduced_motion_and_switch_states_are_readable(self):
        required = (
            ".language-switch",
            ".language-switch:focus-visible",
            ".language-switch[aria-checked=\"true\"]",
            ".language-switch[aria-busy=\"true\"]",
            ".language-switch-error",
            "[dir=\"rtl\"]",
            "@media (max-width: 359px)",
            "@media (prefers-reduced-motion: reduce)",
            "min-height: 44px",
        )
        self.assertEqual([token for token in required if token not in self.css], [])

    def test_ec_2_err_2_rapid_switches_are_serialized_and_failure_reloads_authoritative_state(self):
        required = (
            "languageSwitchPending",
            "if (languageSwitchPending) return",
            "setLanguageSwitchesDisabled(true)",
            "setLanguageSwitchesDisabled(false)",
            'document.querySelectorAll(".language-switch")',
            "await load()",
        )
        self.assertEqual([token for token in required if token not in self.js], [])
        switch_start = self.js.find("async function switchLanguage")
        self.assertGreaterEqual(switch_start, 0)
        switch_body = self.js[switch_start : switch_start + 4_000]
        self.assertRegex(
            switch_body,
            r"catch\s*\([^)]*\)\s*\{[^}]*await\s+load\(\)",
        )
        self.assertNotRegex(
            switch_body,
            r"catch\s*\([^)]*\)\s*\{[^}]*render\(previous",
        )


class MiniAppStarsSelectionContractTest(unittest.TestCase):
    def test_ac_3_ec_1_public_products_have_exact_bounded_product_deep_links(self):
        products = [
            {"product_id": "ai-mini", "title": "Mini", "credits": 20, "price_xtr": 69, "status": "active", "billing_mode": "one_time", "display_order": 10},
            {"product_id": "ai-starter", "title": "Starter", "credits": 50, "price_xtr": 129, "status": "active", "billing_mode": "one_time", "display_order": 20},
            {"product_id": "ai-value", "title": "Value", "credits": 150, "price_xtr": 319, "status": "active", "billing_mode": "one_time", "display_order": 30},
            {"product_id": "ai-monthly", "title": "Monthly", "credits": 100, "price_xtr": 229, "status": "active", "billing_mode": "subscription", "display_order": 2},
            {"product_id": "bad product", "title": "Bad", "credits": 1, "price_xtr": 1, "status": "active", "billing_mode": "one_time", "display_order": 3},
        ]

        visible = miniapp.visible_credit_products(products, locale="en")

        self.assertEqual(
            [
                (
                    row.get("product_id"),
                    row.get("credits"),
                    row.get("price_xtr"),
                    row.get("deep_link_action"),
                )
                for row in visible
            ],
            [
                ("ai-mini", 20, 69, "buy_ai-mini"),
                ("ai-starter", 50, 129, "buy_ai-starter"),
                ("ai-value", 150, 319, "buy_ai-value"),
            ],
        )
        self.assertTrue(
            all(
                re.fullmatch(r"[A-Za-z0-9_-]{1,64}", row["deep_link_action"])
                for row in visible
            )
        )
        rendered = json.dumps(visible, sort_keys=True)
        self.assertNotIn(str(USER_ID), rendered)
        self.assertNotIn("10", json.dumps([row["price_xtr"] for row in visible]))

    def test_ac_3_checkout_state_and_click_use_the_exact_product_action(self):
        required = (
            "button.disabled = !data.features.stars_checkout",
            "product.deep_link_action",
            "openAction(product.deep_link_action)",
            'node("checkout-disabled").hidden = data.features.stars_checkout',
        )
        source = JS_PATH.read_text(encoding="utf-8")
        self.assertEqual([token for token in required if token not in source], [])
        self.assertNotIn('openAction("buy")', source)

    def test_ac_3_ac_4_exact_buy_deep_link_is_bounded_and_reaches_selected_product(self):
        self.assertEqual(
            bot.miniapp_start_action("miniapp_buy_ai-mini"),
            "buy:ai-mini",
        )
        self.assertIsNone(bot.miniapp_start_action("miniapp_buy_../../private"))
        self.assertIsNone(bot.miniapp_start_action("miniapp_buy_" + "x" * 65))

    async def _start_purchase(self, product_id: str):
        products = [
            {
                "product_id": "ai-mini",
                "title": "Mini",
                "description": "20 AI credits",
                "credits": 20,
                "price_xtr": 69,
                "status": "active",
                "billing_mode": "one_time",
            },
            {
                "product_id": "ai-monthly",
                "title": "Monthly",
                "description": "Subscription",
                "credits": 100,
                "price_xtr": 229,
                "status": "active",
                "billing_mode": "subscription",
            },
        ]
        service = MagicMock()
        service.active_products.return_value = products
        service.create_order.return_value = InvoiceOrder(
            order_id="safe-order",
            product_id=product_id,
            title="Selected",
            description="Selected product",
            credits=20,
            amount_xtr=69,
            payload="md1.safe.signed-payload",
        )
        store = MagicMock()
        store.access_profile.return_value = {
            "role": "learner",
            "access_status": "active",
        }
        store.has_consent.return_value = True
        runtime = SimpleNamespace(
            access_status="active",
            role="learner",
            onboarding_completed=True,
            store=store,
            user_id=USER_ID,
        )
        message = SimpleNamespace(reply_text=AsyncMock(), chat_id=USER_ID)
        update = SimpleNamespace(
            message=message,
            effective_message=message,
            effective_user=SimpleNamespace(
                id=USER_ID,
                first_name="Mila",
                language_code="en",
            ),
            effective_chat=SimpleNamespace(id=USER_ID, type="private"),
            callback_query=None,
        )
        context = SimpleNamespace(
            args=[f"miniapp_buy_{product_id}"],
            user_data={"interface_locale": "en"},
            bot=SimpleNamespace(send_invoice=AsyncMock()),
        )
        policies = {
            "cmd_start": ("default", object()),
            "cmd_buy": ("billing", object()),
            "buy_product_cb": ("billing", object()),
        }
        safety = SimpleNamespace(
            enabled=True,
            for_handler=MagicMock(side_effect=lambda name: policies[name]),
        )
        limiter = MagicMock()
        limiter.consume.return_value = SimpleNamespace(
            allowed=True,
            retry_after_seconds=0,
        )

        from contextlib import contextmanager

        @contextmanager
        def runtime_scope(_user):
            token = bot._ACTIVE_RUNTIME.set(runtime)
            try:
                yield runtime
            finally:
                bot._ACTIVE_RUNTIME.reset(token)

        with (
            patch.object(bot, "get_store", return_value=store),
            patch.object(bot, "get_billing_service", return_value=service),
            patch.object(bot, "BOT_ACCESS_MODE", "public"),
            patch.object(bot, "ALLOWED_USER_IDS", set()),
            patch.object(bot, "ADMIN_USER_IDS", set()),
            patch.object(bot, "learner_scope", side_effect=runtime_scope),
            patch.object(bot, "SAFETY_SETTINGS", safety),
            patch.object(bot, "PersistentRateLimiter", return_value=limiter),
            patch.object(
                bot,
                "BILLING_SETTINGS",
                SimpleNamespace(enabled=True, terms_version="terms-v1"),
            ),
            patch.object(
                bot,
                "STARS_PRODUCTION_CANARY_SETTINGS",
                SimpleNamespace(enabled=False),
            ),
            patch.object(bot, "record_product_event"),
            patch.object(bot, "send_billing_products", new=AsyncMock()) as catalog,
        ):
            await bot.cmd_start(update, context)
        return service, context.bot.send_invoice, catalog

    def test_err_3_forged_miniapp_products_never_reach_order_or_invoice(self):
        import asyncio

        valid_service, valid_invoice, valid_catalog = asyncio.run(
            self._start_purchase("ai-mini")
        )
        valid_service.create_order.assert_called_once_with(
            user_id=USER_ID,
            product_id="ai-mini",
        )
        valid_invoice.assert_awaited_once()
        valid_catalog.assert_not_awaited()

        for product_id in ("ai-monthly", "ai-draft", "ai-inactive", "ai-unknown"):
            with self.subTest(product_id=product_id):
                service, invoice, _catalog = asyncio.run(
                    self._start_purchase(product_id)
                )
                service.create_order.assert_not_called()
                invoice.assert_not_awaited()

    async def _terms_resume_flow(self):
        product_id = "ai-mini"
        service = MagicMock()
        service.create_order.return_value = InvoiceOrder(
            order_id="safe-order",
            product_id=product_id,
            title="Mini",
            description="20 AI credits",
            credits=20,
            amount_xtr=69,
            payload="md1.safe.signed-payload",
        )
        store = MagicMock()
        store.has_consent.return_value = False
        store.grant_consent.return_value = True
        context = SimpleNamespace(
            user_data={"interface_locale": "en"},
            bot=SimpleNamespace(send_invoice=AsyncMock()),
        )
        select_update, select_query = callback_update(USER_ID, f"buy:{product_id}")
        accept_update, _accept_query = callback_update(USER_ID, "billing:accept_terms")
        terms = AsyncMock()
        catalog = AsyncMock()
        settings = SimpleNamespace(enabled=True, terms_version="terms-v1")
        with (
            patch.object(bot, "BILLING_SETTINGS", settings),
            patch.object(bot, "get_store", return_value=store),
            patch.object(bot, "get_billing_service", return_value=service),
            patch.object(bot, "send_billing_terms", new=terms),
            patch.object(bot, "send_billing_products", new=catalog),
            patch.object(bot, "record_product_event"),
        ):
            await bot.buy_product_cb.__wrapped__(select_update, context)
            store.has_consent.return_value = True
            await bot.billing_consent_cb.__wrapped__(accept_update, context)
            await bot.billing_consent_cb.__wrapped__(accept_update, context)
        return service, context, terms, catalog, select_query

    def test_ac_4_missing_terms_resume_exact_product_once_and_invoice_exact_amount(self):
        service, context, terms, catalog, select_query = __import__("asyncio").run(
            self._terms_resume_flow()
        )

        terms.assert_awaited_once_with(select_query.message, locale="en")
        service.create_order.assert_called_once_with(
            user_id=USER_ID,
            product_id="ai-mini",
        )
        context.bot.send_invoice.assert_awaited_once()
        invoice = context.bot.send_invoice.await_args.kwargs
        self.assertEqual(invoice["currency"], "XTR")
        self.assertEqual(invoice["prices"][0].amount, 69)
        self.assertNotIn("provider_token", invoice)
        self.assertEqual(catalog.await_count, 1, "second acceptance may open catalog, not repeat invoice")

    def test_err_3_public_canary_conflict_and_fixed_public_economics_fail_closed(self):
        with self.assertRaises(BillingConfigurationError):
            billing.ProductionStarsCanarySettings.from_env(
                {
                    "TELEGRAM_STARS_ENABLED": "true",
                    "STARS_PRODUCTION_CANARY_ENABLED": "true",
                    "STARS_PRODUCTION_CANARY_OWNER_ID": str(USER_ID),
                    "STARS_PRODUCTION_CANARY_PRODUCT_ID": "ai-mini",
                    "STARS_PRODUCTION_CANARY_AMOUNT_XTR": "10",
                }
            )

        candidates = commercial_launch._candidate_products(economics.load_snapshot())
        public = [
            (row["product_id"], row["credits"], row["price_xtr"])
            for row in candidates
            if row["billing_mode"] == "one_time"
        ]
        self.assertEqual(
            public,
            [
                ("ai-mini", 20, 69),
                ("ai-starter", 50, 129),
                ("ai-value", 150, 319),
            ],
        )
        self.assertNotIn(("ai-mini", 20, 10), public)


if __name__ == "__main__":
    unittest.main()
