from __future__ import annotations

import json
import os
from pathlib import Path
import re
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch
from urllib.parse import parse_qs, urlsplit

from sqlalchemy import func, inspect, select, text


os.environ.setdefault("BOT_TOKEN", "123456:TESTTOKEN_ABCDEFGHIJKLMNOP")
os.environ.setdefault("ALLOWED_USER_ID", "1")
os.environ.setdefault("ALLOW_SQLITE_DEV", "true")

import bot
from mydictionary import miniapp
from mydictionary.admin import create_app
from mydictionary.storage import (
    AIWallet,
    AnalyticsEvent,
    BillingCreditLedger,
    DatabaseStore,
    User,
)


ROOT = Path(__file__).resolve().parents[1]
LOCALES = {"en", "fr", "de", "ja", "ar", "zh", "ru", "es"}
BOT_USERNAME = "mydictionary_test_bot"
INVITER_ID = 741_001
STARTER_CREDITS = 40
REFERRAL_REWARD = 5
REFERRAL_CAP = 10
INVITE_URL_RE = re.compile(
    rf"^https://t\.me/{BOT_USERNAME}\?start=ref_([A-Za-z0-9_-]{{16,48}})$"
)
REFERRAL_COPY_KEYS = {
    "referral_title",
    "referral_body",
    "referral_invited",
    "referral_activated",
    "referral_earned",
    "referral_terms",
    "referral_invite",
    "referral_pending",
    "referral_error",
    "referral_retry",
    "referral_share_text",
}


def telegram_user(user_id: int, *, language_code: str = "ru") -> SimpleNamespace:
    return SimpleNamespace(
        id=int(user_id),
        username=f"learner_{user_id}",
        first_name="Learner",
        last_name=None,
        language_code=language_code,
    )


def database_row_counts(store: DatabaseStore) -> dict[str, int]:
    table_names = inspect(store.engine).get_table_names()
    with store.engine.connect() as connection:
        return {
            table_name: int(
                connection.execute(
                    text(f'SELECT COUNT(*) FROM "{table_name}"')
                ).scalar_one()
            )
            for table_name in table_names
        }


class ReferralProgramV1ContractTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="mydictionary-referral-")
        self.store = DatabaseStore(
            f"sqlite:///{Path(self.temporary.name) / 'referral.sqlite3'}"
        )
        self.activate(INVITER_ID)

    def tearDown(self) -> None:
        self.store.close()
        self.temporary.cleanup()

    def activate(self, user_id: int, *, privacy_status: str = "active") -> None:
        self.store.ensure_user(telegram_user(user_id))
        with self.store.Session.begin() as session:
            learner = session.get(User, int(user_id))
            learner.access_status = "active"
            learner.privacy_status = privacy_status

    def app(self):
        return create_app(
            {
                "TESTING": True,
                "SECRET_KEY": "s" * 40,
                "ADMIN_USERNAME": "owner",
                "ADMIN_PASSWORD": "password",
                "MINIAPP_ENABLED": True,
                "MINIAPP_PUBLIC_URL": "https://mydictionary.example.test/miniapp",
                "MINIAPP_BOT_USERNAME": BOT_USERNAME,
                "MINIAPP_AUTH_MAX_AGE_SECONDS": 300,
                "BOT_TOKEN_FILE": "/protected/bot-token",
                "AI_INITIAL_CREDITS": STARTER_CREDITS,
                "TELEGRAM_STARS_ENABLED": False,
            },
            database_store=self.store,
        )

    @staticmethod
    def verified_user(user_id: int) -> dict[str, object]:
        return {
            "user_id": int(user_id),
            "display_name": "Learner",
            "language_code": "ru",
        }

    def issue_invite(self, user_id: int = INVITER_ID) -> tuple[str, str]:
        client = self.app().test_client()
        with patch.object(
            miniapp,
            "verify_init_data",
            return_value=self.verified_user(user_id),
        ):
            response = client.post(
                "/miniapp/api/referral-invite",
                headers={"X-Telegram-Init-Data": "signed"},
            )
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        self.assertEqual(response.headers["Cache-Control"], "no-store")
        self.assertEqual(set(response.get_json()), {"invite_url"})
        invite_url = response.get_json()["invite_url"]
        match = INVITE_URL_RE.fullmatch(invite_url)
        self.assertIsNotNone(match, invite_url)
        return invite_url, match.group(1)

    async def start(
        self,
        user_id: int,
        payload: str,
        *,
        access_mode: str = "public",
    ) -> SimpleNamespace:
        message = SimpleNamespace(reply_text=AsyncMock(), reply_photo=AsyncMock())
        update = SimpleNamespace(
            message=message,
            effective_message=message,
            effective_user=telegram_user(user_id),
            callback_query=None,
        )
        context = SimpleNamespace(args=[payload], user_data={})
        with (
            patch.object(bot, "_STORE", self.store),
            patch.object(bot, "BOT_ACCESS_MODE", access_mode),
            patch.object(bot, "ALLOWED_USER_IDS", set()),
            patch.object(bot, "ADMIN_USER_IDS", set()),
            patch.object(bot, "LEGACY_USER_ID", None),
        ):
            await bot.cmd_start(update, context)
        self.assertTrue(
            message.reply_text.await_count or message.reply_photo.await_count,
            "referral handling must not break /start or onboarding",
        )
        return message

    async def test_ac01_opaque_invite_is_stable_and_uses_validated_bot_username(self):
        with self.store.engine.connect() as connection:
            revision = connection.execute(
                text("select version_num from alembic_version")
            ).scalar_one()
        self.assertEqual(revision, "0019_referral_program_v1")

        first_url, first_code = self.issue_invite()
        second_url, second_code = self.issue_invite()
        self.assertEqual(first_url, second_url)
        self.assertEqual(first_code, second_code)
        self.assertNotIn(str(INVITER_ID), first_code)
        self.assertNotEqual(first_code, str(INVITER_ID))
        self.assertLessEqual(len(f"ref_{first_code}"), 64)

        parsed = urlsplit(first_url)
        self.assertEqual(parsed.scheme, "https")
        self.assertEqual(parsed.netloc, "t.me")
        self.assertEqual(parsed.path, f"/{BOT_USERNAME}")
        self.assertEqual(parse_qs(parsed.query), {"start": [f"ref_{first_code}"]})

    async def test_ac02_new_and_waitlisted_learners_are_attributed_once_without_token_analytics(self):
        _, code = self.issue_invite()
        invitee_id = 741_101
        with patch.object(bot, "logger") as runtime_logger:
            await self.start(invitee_id, f"ref_{code}")

        profile = self.store.product_profile(invitee_id)
        self.assertEqual(profile["acquisition_source"], "referral")
        self.assertEqual(
            self.store.referral_summary(INVITER_ID),
            {
                "invited": 1,
                "activated": 0,
                "earned_credits": 0,
                "reward_credits": REFERRAL_REWARD,
                "reward_cap": REFERRAL_CAP,
            },
        )
        with self.store.Session() as session:
            events = session.execute(
                select(AnalyticsEvent).where(
                    AnalyticsEvent.telegram_user_id == invitee_id
                )
            ).scalars().all()
        start_events = [row for row in events if row.event_name == "start_received"]
        self.assertEqual(len(start_events), 1)
        self.assertEqual(start_events[0].source, "referral")
        self.assertNotIn(code, json.dumps([
            {
                "event": row.event_name,
                "source": row.source,
                "session": row.session_id,
                "properties": row.properties_json,
            }
            for row in events
        ], sort_keys=True))
        self.assertNotIn(code, repr(runtime_logger.mock_calls))

        waitlisted_id = 741_102
        await self.start(waitlisted_id, f"ref_{code}", access_mode="pilot")
        waitlisted = self.store.product_profile(waitlisted_id)
        self.assertEqual(waitlisted["access_status"], "pending")
        self.assertEqual(waitlisted["acquisition_source"], "referral")
        self.assertEqual(self.store.referral_summary(INVITER_ID)["invited"], 2)
        self.assertEqual(self.store.referral_summary(INVITER_ID)["activated"], 0)

    async def test_ac03_existing_self_duplicate_inactive_and_malformed_referrals_are_ignored(self):
        _, first_code = self.issue_invite()
        second_inviter = 741_002
        self.activate(second_inviter)
        _, second_code = self.issue_invite(second_inviter)

        await self.start(INVITER_ID, f"ref_{first_code}")
        existing_id = 741_201
        self.activate(existing_id)
        await self.start(existing_id, f"ref_{first_code}")
        self.assertEqual(self.store.referral_summary(INVITER_ID)["invited"], 0)

        once_id = 741_202
        await self.start(once_id, f"ref_{first_code}")
        await self.start(once_id, f"ref_{second_code}")
        self.assertEqual(self.store.referral_summary(INVITER_ID)["invited"], 1)
        self.assertEqual(self.store.referral_summary(second_inviter)["invited"], 0)

        malformed = (
            "ref_",
            "ref_a",
            "ref_unknownunknown12",
            "ref_bad+token+value",
            "ref_приглашение",
            "ref_" + "a" * 80,
        )
        for offset, payload in enumerate(malformed, start=1):
            with self.subTest(payload=payload[:20]):
                candidate_id = 741_300 + offset
                await self.start(candidate_id, payload)
                self.assertNotEqual(
                    self.store.product_profile(candidate_id)["acquisition_source"],
                    "referral",
                )
        self.assertEqual(self.store.referral_summary(INVITER_ID)["invited"], 1)

        inactive_inviter = 741_003
        self.activate(inactive_inviter)
        _, inactive_code = self.issue_invite(inactive_inviter)
        with self.store.Session.begin() as session:
            inviter = session.get(User, inactive_inviter)
            inviter.access_status = "blocked"
        blocked_invitee = 741_401
        await self.start(blocked_invitee, f"ref_{inactive_code}")
        self.assertNotEqual(
            self.store.product_profile(blocked_invitee)["acquisition_source"],
            "referral",
        )

        erased_inviter = 741_004
        self.activate(erased_inviter)
        _, erased_code = self.issue_invite(erased_inviter)
        with self.store.Session.begin() as session:
            inviter = session.get(User, erased_inviter)
            inviter.privacy_status = "erased"
        erased_invitee = 741_402
        await self.start(erased_invitee, f"ref_{erased_code}")
        self.assertNotEqual(
            self.store.product_profile(erased_invitee)["acquisition_source"],
            "referral",
        )

    async def test_ac04_ac05_completion_rewards_once_and_preserves_the_starter_wallet(self):
        _, code = self.issue_invite()
        invitee_id = 741_501
        await self.start(invitee_id, f"ref_{code}")
        with self.store.Session() as session:
            self.assertIsNone(session.get(AIWallet, INVITER_ID))

        for _ in range(2):
            self.store.update_product_profile(
                invitee_id,
                native_language="ru",
                learning_goal="basics",
                daily_word_goal=5,
                complete_onboarding=True,
                initial_credits=STARTER_CREDITS,
            )

        summary = self.store.referral_summary(INVITER_ID)
        self.assertEqual(summary["activated"], 1)
        self.assertEqual(summary["earned_credits"], REFERRAL_REWARD)
        self.assertEqual(
            self.store.ai_usage_summary(INVITER_ID)["available_credits"],
            STARTER_CREDITS + REFERRAL_REWARD,
        )
        with self.store.Session() as session:
            reward_rows = session.execute(
                select(BillingCreditLedger).where(
                    BillingCreditLedger.telegram_user_id == INVITER_ID,
                    BillingCreditLedger.entry_type == "referral_reward",
                )
            ).scalars().all()
        self.assertEqual(len(reward_rows), 1)
        reward = reward_rows[0]
        self.assertEqual(reward.delta, REFERRAL_REWARD)
        self.assertEqual(reward.balance_after, STARTER_CREDITS + REFERRAL_REWARD)
        self.assertEqual(reward.reference_type, "referral")
        self.assertTrue(reward.idempotency_key.startswith("referral:"))
        for private_identifier in (str(INVITER_ID), str(invitee_id)):
            self.assertNotIn(private_identifier, reward.idempotency_key)
            self.assertNotIn(private_identifier, str(reward.reference_id or ""))

    async def test_ac04_eleventh_activation_is_recorded_but_reward_is_capped(self):
        _, code = self.issue_invite()
        for offset in range(REFERRAL_CAP + 1):
            invitee_id = 742_000 + offset
            await self.start(invitee_id, f"ref_{code}")
            self.store.update_product_profile(
                invitee_id,
                complete_onboarding=True,
                initial_credits=STARTER_CREDITS,
            )

        summary = self.store.referral_summary(INVITER_ID)
        self.assertEqual(summary["invited"], REFERRAL_CAP + 1)
        self.assertEqual(summary["activated"], REFERRAL_CAP + 1)
        self.assertEqual(summary["earned_credits"], REFERRAL_CAP * REFERRAL_REWARD)
        with self.store.Session() as session:
            reward_count = session.execute(
                select(func.count(BillingCreditLedger.entry_id)).where(
                    BillingCreditLedger.telegram_user_id == INVITER_ID,
                    BillingCreditLedger.entry_type == "referral_reward",
                )
            ).scalar_one()
        self.assertEqual(reward_count, REFERRAL_CAP)
        self.assertEqual(
            self.store.ai_usage_summary(INVITER_ID)["available_credits"],
            STARTER_CREDITS + REFERRAL_CAP * REFERRAL_REWARD,
        )

    async def test_ac06_bootstrap_returns_private_aggregates_and_is_read_only(self):
        _, code = self.issue_invite()
        invitee_id = 741_601
        await self.start(invitee_id, f"ref_{code}")
        self.store.update_product_profile(
            invitee_id,
            complete_onboarding=True,
            initial_credits=STARTER_CREDITS,
        )
        before = database_row_counts(self.store)

        payload = miniapp.build_bootstrap(
            self.store,
            user_id=INVITER_ID,
            display_name="Inviter",
            locale="ru",
            catalog=bot.CATALOG,
            products=[],
            checkout_enabled=False,
            ai_enabled=True,
            voice_enabled=False,
            initial_credits=STARTER_CREDITS,
        )

        self.assertEqual(
            payload["referrals"],
            {
                "invited": 1,
                "activated": 1,
                "earned_credits": REFERRAL_REWARD,
                "reward_credits": REFERRAL_REWARD,
                "reward_cap": REFERRAL_CAP,
            },
        )
        self.assertEqual(database_row_counts(self.store), before)
        serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        self.assertNotIn(code, serialized)
        for forbidden_key in (
            "inviter_id",
            "invitee_id",
            "telegram_user_id",
            "invite_code",
            "username",
        ):
            self.assertNotIn(f'"{forbidden_key}"', serialized)

    async def test_ac08_endpoint_fails_closed_for_auth_access_and_database_errors(self):
        client = self.app().test_client()
        unauthenticated = client.post("/miniapp/api/referral-invite")
        self.assertEqual(unauthenticated.status_code, 401)
        self.assertEqual(
            unauthenticated.get_json(), {"error": "authentication_failed"}
        )

        blocked_id = 741_701
        self.activate(blocked_id)
        with self.store.Session.begin() as session:
            session.get(User, blocked_id).access_status = "blocked"
        with patch.object(
            miniapp,
            "verify_init_data",
            return_value=self.verified_user(blocked_id),
        ):
            denied = client.post(
                "/miniapp/api/referral-invite",
                headers={"X-Telegram-Init-Data": "signed"},
            )
        self.assertEqual(denied.status_code, 403)
        self.assertEqual(denied.get_json(), {"error": "access_denied"})

        with (
            patch.object(
                miniapp,
                "verify_init_data",
                return_value=self.verified_user(INVITER_ID),
            ),
            patch.object(
                self.store,
                "Session",
                side_effect=RuntimeError("PRIVATE database url and invite token"),
            ),
        ):
            unavailable = client.post(
                "/miniapp/api/referral-invite",
                headers={"X-Telegram-Init-Data": "signed"},
            )
        self.assertEqual(unavailable.status_code, 503)
        self.assertEqual(
            unavailable.get_json(), {"error": "temporarily_unavailable"}
        )
        self.assertNotIn("PRIVATE", unavailable.get_data(as_text=True))
        self.assertNotIn("invite token", unavailable.get_data(as_text=True))


class ReferralMiniAppSurfaceContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.html = (ROOT / "mydictionary/templates/miniapp.html").read_text(
            encoding="utf-8"
        )
        cls.css = (ROOT / "mydictionary/static/miniapp.css").read_text(
            encoding="utf-8"
        )
        cls.js = (ROOT / "mydictionary/static/miniapp.js").read_text(
            encoding="utf-8"
        )

    def test_ac07_all_locales_and_accessible_dashboard_surface_are_complete(self):
        self.assertEqual(set(miniapp.MINIAPP_COPY), LOCALES)
        for locale, copy in miniapp.MINIAPP_COPY.items():
            with self.subTest(locale=locale):
                self.assertEqual(
                    sorted(key for key in REFERRAL_COPY_KEYS if not str(copy.get(key, "")).strip()),
                    [],
                )

        card = re.search(
            r'<section\b(?=[^>]*\bid=["\']referral-card["\'])[^>]*>.*?</section>',
            self.html,
            re.IGNORECASE | re.DOTALL,
        )
        self.assertIsNotNone(card)
        surface = card.group(0)
        self.assertIn('aria-labelledby="referral-title"', surface)
        self.assertIn('id="referral-invited"', surface)
        self.assertIn('id="referral-activated"', surface)
        self.assertIn('id="referral-earned"', surface)
        self.assertRegex(
            surface,
            r'<button\b(?=[^>]*\bid=["\']referral-invite["\'])'
            r'(?=[^>]*\btype=["\']button["\'])'
            r'(?=[^>]*\bdata-i18n=["\']referral_invite["\'])[^>]*>',
        )
        self.assertRegex(
            surface,
            r'<[^>]+\bid=["\']referral-status["\'][^>]+aria-live=["\']polite["\']',
        )

        self.assertIn(".referral-card", self.css)
        self.assertRegex(
            self.css,
            r"\.referral-invite-button\s*\{[^}]*min-height\s*:\s*44px",
        )
        self.assertIn("var(--dashboard-surface)", self.css)
        self.assertIn("var(--dashboard-accent)", self.css)
        self.assertIn(":focus-visible", self.css)
        self.assertRegex(self.css, r"(?:html\[dir=[\"']rtl[\"']|:dir\(rtl\))")
        self.assertIn("@media (prefers-reduced-motion: reduce)", self.css)

    def test_ac07_ac08_frontend_shares_only_issued_link_and_recovers_for_retry(self):
        required_tokens = (
            "/miniapp/api/referral-invite",
            "referralInvitePending",
            'node("referral-invite")',
            'node("referral-status")',
            "invite_url",
            "referral_pending",
            "referral_error",
            "referral_retry",
            'method: "POST"',
            '"X-Telegram-Init-Data": webApp.initData',
            "openTelegramLink",
            "https://t.me/share/url?url=",
            "encodeURIComponent",
            'setAttribute("aria-busy", "true")',
            'removeAttribute("aria-busy")',
            "disabled = true",
            "disabled = false",
        )
        self.assertEqual(
            [token for token in required_tokens if token not in self.js],
            [],
        )
        self.assertRegex(
            self.js,
            r"if\s*\(referralInvitePending(?:\s*\|\||\s*\))",
        )
        self.assertRegex(
            self.js,
            r"https://t\.me/share/url\?url=\$\{encodeURIComponent\([^)]*invite_url",
        )
        self.assertNotIn("window.location", self.js)


if __name__ == "__main__":
    unittest.main()
