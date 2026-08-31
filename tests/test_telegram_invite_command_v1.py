from __future__ import annotations

import inspect
import os
from pathlib import Path
import re
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import AsyncMock, MagicMock, patch
from urllib.parse import parse_qs, quote, urlsplit


os.environ.setdefault("BOT_TOKEN", "123456:TESTTOKEN_ABCDEFGHIJKLMNOP")
os.environ.setdefault("ALLOWED_USER_ID", "1")
os.environ.setdefault("ALLOW_SQLITE_DEV", "true")

import bot
from mydictionary.localization import INTERFACE_LOCALES, translate
from mydictionary.miniapp import MINIAPP_COPY
from mydictionary.storage import (
    DatabaseStore,
    REFERRAL_REWARD_CAP,
    REFERRAL_REWARD_CREDITS,
    User,
)


ROOT = Path(__file__).resolve().parents[1]
BOT_USERNAME = "mydictionary_test_bot"
USER_ID = 781_001
OPAQUE_CODE = "AbCdEfGhIjKlMnOpQrStUvWx"
INVITE_COPY_KEYS = (
    "command_invite",
    "invite_offer",
    "invite_continue",
    "invite_share_text",
    "invite_unavailable",
)
OFFER_MARKERS = {
    "en": ("you earn", "completes onboarding"),
    "fr": ("vous gagnez", "termine"),
    "de": ("du erhältst", "abgeschlossen"),
    "ja": ("獲得", "完了"),
    "ar": ("تحصل", "إكمال"),
    "zh": ("你", "完成"),
    "ru": ("вы получите", "заверш"),
    "es": ("obtienes", "completa"),
}
FORBIDDEN_CLAIMS = (
    "unlimited",
    "illimité",
    "unbegrenzt",
    "無制限",
    "غير محدود",
    "无限",
    "безлимит",
    "ilimitad",
    "gift subscription",
    "abonnement cadeau",
    "geschenkabo",
    "ギフト",
    "اشتراك هدية",
    "赠送订阅",
    "подарочн",
    "suscripción de regalo",
    "telegram stars",
    "xtr",
    "cash",
    "espèces",
    "bargeld",
    "現金",
    "نقد",
    "现金",
    "налич",
    "efectivo",
)
FORBIDDEN_INVITEE_REWARDS = (
    "friend earns",
    "friend gets",
    "they earn",
    "they get",
    "ami reçoit",
    "ami gagne",
    "freund erhält",
    "友達も獲得",
    "يحصل الصديق",
    "好友也获得",
    "друг получит",
    "приглашённый получит",
    "amigo recibe",
    "amigo gana",
)


def telegram_user(
    user_id: int = USER_ID,
    *,
    language_code: str = "en",
) -> SimpleNamespace:
    return SimpleNamespace(
        id=int(user_id),
        username=None,
        first_name="Learner",
        last_name=None,
        language_code=language_code,
    )


def command_update(
    *,
    locale: str = "en",
    chat_type: str = "private",
) -> tuple[SimpleNamespace, SimpleNamespace, SimpleNamespace]:
    message = SimpleNamespace(reply_text=AsyncMock())
    update = SimpleNamespace(
        message=message,
        effective_message=message,
        effective_user=telegram_user(language_code=locale),
        effective_chat=SimpleNamespace(id=USER_ID, type=chat_type),
    )
    context = SimpleNamespace(user_data={"interface_locale": locale}, args=[])
    return update, context, message


def reply_payload(message: SimpleNamespace) -> tuple[str, object | None]:
    call = message.reply_text.await_args
    if call.args:
        body = str(call.args[0])
    else:
        body = str(call.kwargs.get("text") or "")
    return body, call.kwargs.get("reply_markup")


def personal_deep_link(code: str = OPAQUE_CODE) -> str:
    return f"https://t.me/{BOT_USERNAME}?start=ref_{code}"


def native_share_url(share_text: str, code: str = OPAQUE_CODE) -> str:
    return (
        "https://t.me/share/url?"
        f"url={quote(personal_deep_link(code), safe='')}"
        f"&text={quote(share_text, safe='')}"
    )


class TelegramInviteCommandV1ContractTest(unittest.IsolatedAsyncioTestCase):
    def require_handler(self):
        handler = getattr(bot, "cmd_invite", None)
        self.assertIsNotNone(handler, "missing /invite command handler")
        self.assertTrue(callable(handler), "/invite handler must be callable")
        self.assertTrue(
            hasattr(handler, "__wrapped__"),
            "/invite must use the existing authenticated command boundary",
        )
        return handler

    def localized(self, key: str, locale: str) -> str:
        try:
            return translate(key, locale)
        except KeyError:
            self.fail(f"{locale} missing localized Telegram invite key {key}")

    async def invoke_wrapped(
        self,
        *,
        locale: str = "en",
        chat_type: str = "private",
        store=None,
        settings=None,
    ) -> tuple[SimpleNamespace, object]:
        handler = self.require_handler()
        selected_store = store or MagicMock()
        update, context, message = command_update(
            locale=locale,
            chat_type=chat_type,
        )
        runtime = SimpleNamespace(
            user_id=USER_ID,
            store=selected_store,
            progress={},
            interface_locale=locale,
            role="learner",
            access_status="active",
            onboarding_completed=True,
        )
        token = bot._ACTIVE_RUNTIME.set(runtime)
        try:
            with (
                patch.object(bot, "get_store", return_value=selected_store),
                patch.object(
                    bot,
                    "MINIAPP_SETTINGS",
                    settings
                    or SimpleNamespace(enabled=True, bot_username=BOT_USERNAME),
                ),
            ):
                await handler.__wrapped__(update, context)
        finally:
            bot._ACTIVE_RUNTIME.reset(token)
        return message, selected_store

    def test_ac1_command_is_registered_and_private_menu_is_localized_when_enabled(self):
        source = inspect.getsource(bot.manual_polling)
        self.assertIn('CommandHandler("invite", cmd_invite)', source)

        for locale in INTERFACE_LOCALES:
            with self.subTest(locale=locale):
                expected = self.localized("command_invite", locale)
                enabled = {
                    command.command: command.description
                    for command in bot.build_bot_commands(
                        ai_enabled=False,
                        miniapp_enabled=True,
                        locale=locale,
                    )
                }
                disabled = {
                    command.command: command.description
                    for command in bot.build_bot_commands(
                        ai_enabled=False,
                        miniapp_enabled=False,
                        locale=locale,
                    )
                }
                self.assertEqual(enabled.get("invite"), expected)
                self.assertNotIn("invite", disabled)

    def test_ac2_honest_offer_copy_is_complete_in_all_eight_locales(self):
        self.assertEqual(set(INTERFACE_LOCALES), set(OFFER_MARKERS))
        copy_by_key: dict[str, list[str]] = {key: [] for key in INVITE_COPY_KEYS}
        for locale in INTERFACE_LOCALES:
            with self.subTest(locale=locale):
                translated = {
                    key: self.localized(key, locale).strip()
                    for key in INVITE_COPY_KEYS
                }
                self.assertEqual(
                    sorted(key for key, value in translated.items() if not value),
                    [],
                )
                for key, value in translated.items():
                    copy_by_key[key].append(value)

                offer = translated["invite_offer"].casefold()
                self.assertIn("5", offer)
                self.assertIn("10", offer)
                for marker in OFFER_MARKERS[locale]:
                    self.assertIn(marker.casefold(), offer)
                self.assertEqual(
                    [claim for claim in FORBIDDEN_CLAIMS if claim.casefold() in offer],
                    [],
                )
                self.assertEqual(
                    [
                        claim
                        for claim in FORBIDDEN_INVITEE_REWARDS
                        if claim.casefold() in offer
                    ],
                    [],
                )

        for key, values in copy_by_key.items():
            with self.subTest(localized_key=key):
                self.assertEqual(
                    len(set(values)),
                    len(INTERFACE_LOCALES),
                    f"{key} must not silently fall back to one language",
                )

    async def test_ac2_ac3_each_locale_sends_one_exact_native_share_url_button(self):
        store = MagicMock()
        store.issue_referral_code.return_value = OPAQUE_CODE
        for locale in INTERFACE_LOCALES:
            with self.subTest(locale=locale):
                expected_offer = self.localized("invite_offer", locale)
                expected_continue = self.localized("invite_continue", locale)
                expected_share_text = self.localized("invite_share_text", locale)
                message, _ = await self.invoke_wrapped(
                    locale=locale,
                    store=store,
                )
                message.reply_text.assert_awaited_once()
                body, markup = reply_payload(message)
                self.assertEqual(body, expected_offer)
                self.assertIsNotNone(markup)
                self.assertEqual(len(markup.inline_keyboard), 1)
                self.assertEqual(len(markup.inline_keyboard[0]), 1)
                button = markup.inline_keyboard[0][0]
                self.assertEqual(button.text, expected_continue)
                self.assertEqual(
                    button.url,
                    native_share_url(expected_share_text),
                )

                parsed = urlsplit(button.url)
                self.assertEqual(
                    (parsed.scheme, parsed.netloc, parsed.path, parsed.fragment),
                    ("https", "t.me", "/share/url", ""),
                )
                self.assertIsNone(parsed.username)
                self.assertIsNone(parsed.password)
                self.assertIsNone(parsed.port)
                self.assertEqual(
                    parse_qs(
                        parsed.query,
                        keep_blank_values=True,
                        strict_parsing=True,
                    ),
                    {
                        "url": [personal_deep_link()],
                        "text": [expected_share_text],
                    },
                )
                store.issue_referral_code.reset_mock()

    async def test_ac4_active_onboarded_learner_reuses_one_stable_private_code(self):
        handler = self.require_handler()
        with tempfile.TemporaryDirectory(prefix="telegram-invite-") as raw:
            store = DatabaseStore(f"sqlite:///{Path(raw) / 'invite.sqlite3'}")
            try:
                store.ensure_user(telegram_user())
                with store.Session.begin() as session:
                    learner = session.get(User, USER_ID)
                    learner.access_status = "active"
                    learner.privacy_status = "active"
                store.update_product_profile(
                    USER_ID,
                    native_language="en",
                    learning_goal="travel",
                    daily_word_goal=10,
                    complete_onboarding=True,
                )

                settings = SimpleNamespace(enabled=True, bot_username=BOT_USERNAME)
                urls = []
                with (
                    patch.object(bot, "get_store", return_value=store),
                    patch.object(bot, "MINIAPP_SETTINGS", settings),
                    patch.object(bot, "BOT_ACCESS_MODE", "public"),
                    patch.object(bot, "ALLOWED_USER_IDS", set()),
                    patch.object(bot, "ADMIN_USER_IDS", set()),
                    patch.object(bot, "SAFETY_SETTINGS", SimpleNamespace(enabled=False)),
                    patch.object(
                        store,
                        "issue_referral_code",
                        wraps=store.issue_referral_code,
                    ) as issue_code,
                ):
                    for _ in range(2):
                        update, context, message = command_update(locale="en")
                        await handler(update, context)
                        body, markup = reply_payload(message)
                        urls.append(markup.inline_keyboard[0][0].url)
                        serialized = f"{body}\n{markup!r}\n{urls[-1]}"
                        self.assertNotIn(str(USER_ID), serialized)
                    self.assertEqual(issue_code.call_args_list[0].args, (USER_ID,))
                    self.assertEqual(issue_code.call_args_list[1].args, (USER_ID,))

                self.assertEqual(urls[0], urls[1])
                deep_link = parse_qs(urlsplit(urls[0]).query)["url"][0]
                match = re.fullmatch(
                    rf"https://t\.me/{BOT_USERNAME}\?start=ref_([A-Za-z0-9_-]{{16,48}})",
                    deep_link,
                )
                self.assertIsNotNone(match, deep_link)
                self.assertNotIn(str(USER_ID), match.group(1))
            finally:
                store.close()

    async def test_ec1_group_chat_reuses_private_guidance_without_issuing_a_code(self):
        store = MagicMock()
        message, _ = await self.invoke_wrapped(
            locale="fr",
            chat_type="group",
            store=store,
        )
        body, markup = reply_payload(message)
        self.assertEqual(body, translate("miniapp_private_only", "fr"))
        self.assertIsNone(markup)
        self.assertNotIn("https://", body)
        store.issue_referral_code.assert_not_called()

    async def test_err1_disabled_or_invalid_configuration_fails_closed(self):
        invalid_settings = (
            SimpleNamespace(enabled=False, bot_username=BOT_USERNAME),
            SimpleNamespace(enabled=True, bot_username=""),
            SimpleNamespace(enabled=True, bot_username="bad/name"),
            SimpleNamespace(enabled=True, bot_username="x" * 33),
        )
        for settings in invalid_settings:
            with self.subTest(settings=settings):
                store = MagicMock()
                message, _ = await self.invoke_wrapped(
                    locale="ru",
                    store=store,
                    settings=settings,
                )
                body, markup = reply_payload(message)
                self.assertEqual(body, self.localized("invite_unavailable", "ru"))
                self.assertIsNone(markup)
                if settings.bot_username:
                    self.assertNotIn(str(settings.bot_username), body)
                store.issue_referral_code.assert_not_called()

    async def test_err2_storage_failure_is_generic_and_logging_is_privacy_safe(self):
        handler = self.require_handler()
        store = MagicMock()
        sensitive_message = (
            f"postgresql://private-user:private-password@db.invalid/data "
            f"credential=PRIVATE invite={OPAQUE_CODE} user={USER_ID}"
        )
        store.issue_referral_code.side_effect = RuntimeError(sensitive_message)
        update, context, message = command_update(locale="de")
        runtime = SimpleNamespace(
            user_id=USER_ID,
            store=store,
            progress={},
            interface_locale="de",
            role="learner",
            access_status="active",
            onboarding_completed=True,
        )
        token = bot._ACTIVE_RUNTIME.set(runtime)
        try:
            with (
                patch.object(bot, "get_store", return_value=store),
                patch.object(
                    bot,
                    "MINIAPP_SETTINGS",
                    SimpleNamespace(enabled=True, bot_username=BOT_USERNAME),
                ),
                self.assertLogs("bot", level="WARNING") as captured,
            ):
                await handler.__wrapped__(update, context)
        finally:
            bot._ACTIVE_RUNTIME.reset(token)

        body, markup = reply_payload(message)
        self.assertEqual(body, self.localized("invite_unavailable", "de"))
        self.assertIsNone(markup)
        log_text = "\n".join(captured.output)
        self.assertIn("RuntimeError", log_text)
        for private_value in (
            str(USER_ID),
            OPAQUE_CODE,
            "postgresql://",
            "private-user",
            "private-password",
            "credential",
            "PRIVATE",
            sensitive_message,
        ):
            with self.subTest(private_value=private_value):
                self.assertNotIn(private_value, log_text)

    def test_ac5_existing_miniapp_referral_and_economics_contract_is_preserved(self):
        html = (ROOT / "mydictionary/templates/miniapp.html").read_text(
            encoding="utf-8"
        )
        js = (ROOT / "mydictionary/static/miniapp.js").read_text(
            encoding="utf-8"
        )
        admin_source = (ROOT / "mydictionary/admin.py").read_text(
            encoding="utf-8"
        )
        storage_source = inspect.getsource(DatabaseStore.capture_referral_attribution)

        self.assertEqual(REFERRAL_REWARD_CREDITS, 5)
        self.assertEqual(REFERRAL_REWARD_CAP, 10)
        self.assertEqual(html.count("data-referral-invite"), 2)
        self.assertIn('id="referral-invite"', html)
        self.assertIn('id="settings-invite"', html)
        for token in (
            'document.querySelectorAll("[data-referral-invite]")',
            '"/miniapp/api/referral-invite"',
            "validReferralInviteUrl(result.invite_url)",
            "webApp.openTelegramLink(shareUrl)",
        ):
            self.assertIn(token, js)
        for token in (
            '@app.post("/miniapp/api/referral-invite")',
            'request.headers.get("X-Telegram-Init-Data")',
            "verify_init_data(",
            "require_active_learner(",
            "store.issue_referral_code(",
        ):
            self.assertIn(token, admin_source)
        self.assertIn('inviter.access_status != "active"', storage_source)
        self.assertIn('inviter.privacy_status != "active"', storage_source)
        for locale, copy in MINIAPP_COPY.items():
            with self.subTest(locale=locale):
                self.assertIn("5", copy["referral_body"])
                self.assertIn("10", copy["referral_terms"])


if __name__ == "__main__":
    unittest.main()
