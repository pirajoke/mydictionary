from __future__ import annotations

import json
import os
from pathlib import Path
import re
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, MagicMock, patch
from urllib.parse import parse_qs, urlsplit
os.environ.setdefault("BOT_TOKEN", "123456:TESTTOKEN_ABCDEFGHIJKLMNOP")
os.environ.setdefault("ALLOWED_USER_ID", "1")
os.environ.setdefault("ALLOW_SQLITE_DEV", "true")
import bot
from mydictionary import miniapp
from mydictionary.admin import create_app
from mydictionary.localization import INTERFACE_LOCALES
from mydictionary.storage import DatabaseStore, User
ROOT = Path(__file__).resolve().parents[1]
HTML = (ROOT / "mydictionary/templates/miniapp.html").read_text(encoding="utf-8")
CSS = (ROOT / "mydictionary/static/miniapp.css").read_text(encoding="utf-8")
JS = (ROOT / "mydictionary/static/miniapp.js").read_text(encoding="utf-8")
MINIAPP_URL = "https://mydictionary.example.test/miniapp"
USER_ID = 791_001
DETAIL_COPY_KEYS = set("""
detail_back help_title help_intro help_step_choose_language help_step_start_lesson
help_step_reveal_rate help_step_review help_step_personal_words help_profile_cta
help_dictionary_cta privacy_title privacy_learning_data privacy_voice_transcripts
privacy_ai_memory privacy_billing_audit privacy_erasure_effect privacy_ai_consent
privacy_voice_consent privacy_mirror_memory privacy_retention privacy_status_granted
privacy_status_not_granted privacy_status_disabled privacy_status_unavailable
privacy_revoke_ai privacy_revoke_voice privacy_erase_learning privacy_confirm_erase
privacy_action_pending privacy_action_success privacy_action_error privacy_action_retry
""".split())
def opening_tag(source: str, element_id: str) -> str:
    match = re.search(
        rf"<[^>]+\bid=[\"']{re.escape(element_id)}[\"'][^>]*>", source
    )
    if match is None:
        raise AssertionError(f"missing element #{element_id}")
    return match.group(0)
def element(source: str, element_id: str) -> str:
    match = re.search(
        rf"<(?P<tag>[a-z][a-z0-9]*)\b[^>]*\bid=[\"']{re.escape(element_id)}"
        rf"[\"'][^>]*>.*?</(?P=tag)>",
        source,
        re.IGNORECASE | re.DOTALL,
    )
    if match is None:
        raise AssertionError(f"missing bounded element #{element_id}")
    return match.group(0)
def bootstrap_store(*, ai_consent: bool, voice_consent: bool) -> MagicMock:
    store = MagicMock()
    store.access_profile.return_value = {
        "role": "learner", "access_status": "active", "privacy_status": "active"
    }
    store.product_profile.return_value = {
        "role": "learner", "active_lang": "en", "active_pack_id": None,
        "daily_word_goal": 10, "native_language": "ru",
    }
    store.load_profile.return_value = {}
    store.load_word_progress.return_value = {}
    store.ai_usage_summary.return_value = {}
    store.get_mirror_preferences.return_value = {}
    store.has_consent.side_effect = lambda _, *, consent_type, **__: {
        "ai_processing": ai_consent,
        "voice_processing": voice_consent,
    }[consent_type]
    return store
def bootstrap(store: MagicMock, **privacy_settings):
    catalog = MagicMock()
    catalog.get.return_value = None
    catalog.compatible_packs.return_value = []
    with patch.object(miniapp, "_read_only_activity_days", return_value=[]):
        return miniapp.build_bootstrap(
            store,
            user_id=USER_ID,
            display_name="Learner",
            locale="en",
            catalog=catalog,
            products=[],
            checkout_enabled=False,
            ai_enabled=privacy_settings.pop("ai_enabled", True),
            voice_enabled=privacy_settings.pop("voice_enabled", True),
            **privacy_settings,
        )
class MiniAppHelpPrivacySurfaceContractTest(unittest.TestCase):
    def test_ac1_ac2_ac3_ac8_internal_views_are_accessible_and_stay_in_app(self):
        shell = element(HTML, "detail-view")
        self.assertIn('role="dialog"', opening_tag(HTML, "detail-view"))
        self.assertIn('aria-labelledby="detail-title"', opening_tag(HTML, "detail-view"))
        self.assertIn("hidden", opening_tag(HTML, "detail-view"))
        self.assertRegex(opening_tag(shell, "detail-back"), r"<button\b[^>]*type=[\"']button")
        self.assertIn('tabindex="-1"', opening_tag(shell, "detail-title"))

        help_view = element(shell, "help-detail")
        privacy_view = element(shell, "privacy-detail")
        for key in (
            "help_step_choose_language", "help_step_start_lesson",
            "help_step_reveal_rate", "help_step_review", "help_step_personal_words",
        ):
            self.assertIn(f'data-i18n="{key}"', help_view)
        self.assertEqual(len(re.findall(r"<li\b", help_view)), 5)
        self.assertNotRegex(help_view, r"/(?:start|help|privacy|learn|review|mywords)\b")
        self.assertIn('data-detail-tab="profile"', help_view)
        self.assertIn('data-detail-tab="words"', help_view)
        for action in ("revoke_ai", "revoke_voice", "erase_learning_data"):
            self.assertIn(f'data-privacy-action="{action}"', privacy_view)
        self.assertIn('id="privacy-action-status"', privacy_view)
        self.assertIn('aria-live="polite"', opening_tag(privacy_view, "privacy-action-status"))

        for element_id, view in (("settings-help", "help"), ("settings-privacy", "privacy")):
            tag = opening_tag(HTML, element_id)
            self.assertIn(f'data-detail-view="{view}"', tag)
            self.assertNotIn("data-settings-action", tag)
        for token in (
            "openDetailView", "closeDetailView", 'event.key === "Escape"',
            'node("detail-title").focus()', "detailReturnFocus", "activateTab",
        ):
            self.assertIn(token, JS)
        self.assertNotRegex(JS, r"openDetailView[\s\S]{0,900}openTelegramLink")
        for token in (
            ".detail-view", "min-height: 44px", ":focus-visible",
            'html[dir="rtl"]', "var(--lexi-orange)", "var(--lexi-teal)",
            "@media (prefers-reduced-motion: reduce)", "@media (max-width:",
        ):
            self.assertIn(token, CSS)

    def test_ac7_all_new_visible_copy_is_complete_in_all_eight_locales(self):
        self.assertEqual(set(miniapp.MINIAPP_COPY), set(INTERFACE_LOCALES))
        for locale, copy in miniapp.MINIAPP_COPY.items():
            with self.subTest(locale=locale):
                self.assertEqual(
                    sorted(key for key in DETAIL_COPY_KEYS if not str(copy.get(key, "")).strip()),
                    [],
                )
        for key in DETAIL_COPY_KEYS:
            values = [miniapp.MINIAPP_COPY[locale][key] for locale in INTERFACE_LOCALES]
            self.assertEqual(len(set(values)), 8, f"{key} silently falls back to one language")

    def test_ec1_direct_view_is_allowlisted_and_applied_only_after_bootstrap(self):
        self.assertRegex(JS, r"(?:Set\(|includes\()[^\n]*(?:help|[\"']help[\"'])[^\n]*privacy")
        self.assertIn('URLSearchParams(window.location.search)', JS)
        self.assertRegex(JS, r"\.get\([\"']view[\"']\)")
        self.assertRegex(JS, r"(?:has|includes)\(requestedView\)")
        render = JS[JS.index("function render("):JS.index("function showError(")]
        self.assertIn("openRequestedDetailView", render)
        self.assertNotRegex(JS, r"(?:eval|innerHTML)\s*\([^)]*requestedView")

    def test_err3_privacy_failure_keeps_view_open_and_reenables_controls(self):
        self.assertIn('"/miniapp/api/privacy-action"', JS)
        self.assertIn('"X-Telegram-Init-Data": webApp.initData', JS)
        self.assertIn("JSON.stringify", JS)
        action = JS[JS.index("async function runPrivacyAction("):]
        action = action[: action.index("\n  function ", 20)]
        for token in (
            "privacyActionPending", "disabled = true", "finally",
            "disabled = false", "privacy_action_error", "privacy_action_retry",
        ):
            self.assertIn(token, action)
        self.assertLess(action.index("if (!response.ok)"), action.index("privacy_action_success"))
        self.assertIn('node("detail-view").hidden = false', action)

    def test_ac5_erasure_keeps_detail_fail_closed_against_back_and_escape(self):
        action = JS[JS.index("async function runPrivacyAction("):]
        action = action[: action.index("\n  function ", 20)]
        self.assertIn("access_erased = true", action)

        close = JS[JS.index("function closeDetailView("):]
        close = close[: close.index("\n  function ", 20)]
        self.assertRegex(close, r"(?:access_erased|accessErased)")
        for fail_closed_state in (
            'node("detail-view").hidden = false',
            'node("app-content").hidden = true',
            'document.querySelector(".bottom-nav").hidden = true',
        ):
            self.assertIn(fail_closed_state, close)
class MiniAppPrivacyBootstrapContractTest(unittest.TestCase):
    def test_ac4_ec2_bootstrap_exposes_truthful_bounded_privacy_state(self):
        store = bootstrap_store(ai_consent=True, voice_consent=False)
        payload = bootstrap(
            store,
            ai_consent_version="ai-v1",
            voice_consent_version="voice-v1",
            mirror_memory_enabled=True,
            mirror_retention_days=7,
            voice_transcript_retention_days=30,
        )
        self.assertEqual(payload["privacy"], {
            "ai_consent": "granted",
            "voice_consent": "not_granted",
            "mirror_memory": "enabled",
            "retention_days": {"mirror_dialogue": 7, "voice_transcripts": 30},
        })
        serialized = json.dumps(payload["privacy"], sort_keys=True)
        self.assertNotIn("ai-v1", serialized)
        self.assertNotIn("voice-v1", serialized)

        unavailable_store = bootstrap_store(ai_consent=True, voice_consent=True)
        unavailable = bootstrap(
            unavailable_store,
            ai_enabled=True,
            voice_enabled=False,
            ai_consent_version="",
            voice_consent_version="",
            mirror_memory_enabled=False,
            mirror_retention_days=7,
            voice_transcript_retention_days=30,
        )["privacy"]
        self.assertEqual(unavailable["ai_consent"], "unavailable")
        self.assertEqual(unavailable["voice_consent"], "disabled")
        self.assertEqual(unavailable["mirror_memory"], "disabled")
        unavailable_store.has_consent.assert_not_called()
class MiniAppPrivacyActionHTTPContractTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="miniapp-privacy-")
        self.store = DatabaseStore(f"sqlite:///{Path(self.temporary.name) / 'privacy.sqlite3'}")
        self.store.ensure_user_id(USER_ID)
        with self.store.Session.begin() as session:
            learner = session.get(User, USER_ID)
            learner.access_status = "active"
            learner.privacy_status = "active"
        for consent_type, version in (("ai_processing", "ai-v1"), ("voice_processing", "voice-v1")):
            self.store.grant_consent(USER_ID, consent_type=consent_type, document_version=version, source="test")
        self.app = create_app({
            "TESTING": True, "SECRET_KEY": "s" * 40,
            "ADMIN_USERNAME": "owner", "ADMIN_PASSWORD": "password",
            "MINIAPP_ENABLED": True, "MINIAPP_PUBLIC_URL": MINIAPP_URL,
            "MINIAPP_BOT_USERNAME": "mydictionary_test_bot",
            "MINIAPP_AUTH_MAX_AGE_SECONDS": 300,
            "BOT_TOKEN_FILE": "/protected/bot-token",
            "AI_TUTOR_ENABLED": True, "VOICE_TUTOR_ENABLED": True,
            "AI_CONSENT_VERSION": "ai-v1", "VOICE_CONSENT_VERSION": "voice-v1",
        }, database_store=self.store)

    def tearDown(self):
        self.store.close()
        self.temporary.cleanup()

    @staticmethod
    def identity():
        return {"user_id": USER_ID, "display_name": "Learner", "language_code": "en"}

    def post(self, body=None, **kwargs):
        headers = kwargs.pop("headers", {"X-Telegram-Init-Data": "signed"})
        if body is not None:
            kwargs["json"] = body
        return self.app.test_client().post(
            "/miniapp/api/privacy-action", headers=headers, **kwargs
        )

    def test_ac5_ec3_allowlisted_actions_are_rate_limited_and_idempotent(self):
        limiter = MagicMock()
        limiter.consume.return_value = SimpleNamespace(allowed=True, retry_after_seconds=0)
        with (
            patch.object(miniapp, "verify_init_data", return_value=self.identity()),
            patch("mydictionary.admin.PersistentRateLimiter", return_value=limiter),
        ):
            responses = [self.post({"action": action})
                         for action in ("revoke_ai", "revoke_ai", "revoke_voice")]
            missing_confirmation = self.post({"action": "erase_learning_data"})
            erased = self.post({"action": "erase_learning_data", "confirm": True})
            erased_again = self.post({"action": "erase_learning_data", "confirm": True})
        self.assertEqual([response.status_code for response in responses], [200, 200, 200])
        self.assertEqual(missing_confirmation.status_code, 400)
        self.assertEqual(erased.status_code, 200)
        self.assertEqual(erased_again.status_code, 200)
        self.assertIs(erased_again.get_json().get("ok"), True)
        self.assertTrue(all(response.get_json().get("ok") is True for response in responses))
        self.assertFalse(self.store.has_consent(USER_ID, consent_type="ai_processing", document_version="ai-v1"))
        self.assertFalse(self.store.has_consent(USER_ID, consent_type="voice_processing", document_version="voice-v1"))
        with self.store.Session() as session:
            self.assertEqual(session.get(User, USER_ID).privacy_status, "erased")
        self.assertGreaterEqual(limiter.consume.call_count, 4)
        self.assertTrue(all(call.kwargs["scope"] == "miniapp_privacy_action" for call in limiter.consume.call_args_list))

    def test_err1_err2_auth_schema_access_and_rate_fail_closed_without_mutation(self):
        self.assertEqual(self.post({"action": "revoke_ai"}, headers={}).status_code, 401)
        self.assertEqual(self.post(
            {"action": "revoke_ai"}, headers={"X-Telegram-Init-Data": "x" * 8193}
        ).status_code, 401)
        invalid = (
            ({"data": "not-json", "content_type": "text/plain"}),
            ({"json": {}}), ({"json": {"action": "unknown"}}),
            ({"json": {"action": "revoke_ai", "extra": True}}),
            ({"json": {"action": "erase_learning_data", "confirm": "true"}}),
        )
        with patch.object(miniapp, "verify_init_data", return_value=self.identity()):
            for request_kwargs in invalid:
                with self.subTest(request_kwargs=request_kwargs):
                    response = self.post(**request_kwargs)
                    self.assertEqual(response.status_code, 400)
            limiter = MagicMock()
            limiter.consume.return_value = SimpleNamespace(allowed=False, retry_after_seconds=17)
            with patch("mydictionary.admin.PersistentRateLimiter", return_value=limiter):
                limited = self.post({"action": "revoke_ai"})
        self.assertEqual(limited.status_code, 429)
        self.assertEqual(limited.headers["Retry-After"], "17")
        self.assertTrue(self.store.has_consent(USER_ID, consent_type="ai_processing", document_version="ai-v1"))

    def test_err1_invalid_and_stale_auth_are_rejected(self):
        for reason in ("invalid", "stale"):
            with self.subTest(reason=reason), patch.object(
                miniapp,
                "verify_init_data",
                side_effect=miniapp.MiniAppAuthenticationError(reason),
            ):
                response = self.post({"action": "revoke_ai"})
                self.assertEqual(response.status_code, 401)
                self.assertEqual(response.get_json(), {"error": "authentication_failed"})
        self.assertTrue(self.store.has_consent(
            USER_ID,
            consent_type="ai_processing",
            document_version="ai-v1",
        ))

    def test_err1_inactive_and_erased_learners_cannot_revoke(self):
        for access_status, privacy_status in (
            ("blocked", "active"),
            ("blocked", "erased"),
        ):
            with self.subTest(
                access_status=access_status,
                privacy_status=privacy_status,
            ):
                with self.store.Session.begin() as session:
                    learner = session.get(User, USER_ID)
                    learner.access_status = access_status
                    learner.privacy_status = privacy_status
                with patch.object(miniapp, "verify_init_data", return_value=self.identity()):
                    response = self.post({"action": "revoke_ai"})
                self.assertEqual(response.status_code, 403)
                self.assertEqual(response.get_json(), {"error": "access_denied"})
                self.assertTrue(self.store.has_consent(
                    USER_ID,
                    consent_type="ai_processing",
                    document_version="ai-v1",
                ))
class TelegramHelpPrivacyEntryContractTest(unittest.IsolatedAsyncioTestCase):
    async def invoke(self, command: str, *, locale: str, chat_type: str, settings):
        message = SimpleNamespace(reply_text=AsyncMock())
        update = SimpleNamespace(
            message=message, effective_message=message,
            effective_user=SimpleNamespace(id=USER_ID, language_code=locale),
            effective_chat=SimpleNamespace(id=USER_ID, type=chat_type),
        )
        context = SimpleNamespace(user_data={"interface_locale": locale}, args=[])
        store = MagicMock()
        store.has_consent.return_value = False
        with patch.object(bot, "MINIAPP_SETTINGS", settings), patch.object(bot, "get_store", return_value=store):
            await getattr(bot, f"cmd_{command}").__wrapped__(update, context)
        call = message.reply_text.await_args
        body = str(call.args[0] if call.args else call.kwargs["text"])
        return body, call.kwargs.get("reply_markup"), store

    async def test_ac6_ac7_private_commands_send_compact_localized_view_ctas(self):
        settings = SimpleNamespace(enabled=True, public_url=MINIAPP_URL)
        localized_bodies = {"help": set(), "privacy": set()}
        for command in ("help", "privacy"):
            for locale in INTERFACE_LOCALES:
                with self.subTest(command=command, locale=locale):
                    body, markup, store = await self.invoke(
                        command, locale=locale, chat_type="private", settings=settings
                    )
                    self.assertTrue(body.strip())
                    self.assertLessEqual(len(body), 240)
                    self.assertNotIn("/", body)
                    self.assertIsNotNone(markup)
                    button = markup.inline_keyboard[0][0]
                    self.assertTrue(button.text.strip())
                    parsed = urlsplit(button.web_app.url)
                    self.assertEqual((parsed.scheme, parsed.netloc, parsed.path, parsed.fragment),
                                     ("https", "mydictionary.example.test", "/miniapp", ""))
                    self.assertEqual(parse_qs(parsed.query), {"view": [command]})
                    self.assertNotIn(str(USER_ID), button.web_app.url)
                    store.has_consent.assert_not_called()
                    localized_bodies[command].add(body)
        self.assertEqual({key: len(values) for key, values in localized_bodies.items()},
                         {"help": 8, "privacy": 8})

    async def test_ac6_group_disabled_and_unconfigured_commands_use_safe_text_fallback(self):
        cases = (
            ("group", SimpleNamespace(enabled=True, public_url=MINIAPP_URL)),
            ("private", SimpleNamespace(enabled=False, public_url="")),
            ("private", SimpleNamespace(enabled=True, public_url="")),
        )
        for command in ("help", "privacy"):
            for chat_type, settings in cases:
                with self.subTest(command=command, chat_type=chat_type, settings=settings):
                    body, markup, _ = await self.invoke(
                        command, locale="fr", chat_type=chat_type, settings=settings
                    )
                    self.assertTrue(body.strip())
                    self.assertIsNone(markup)
                    self.assertNotIn(MINIAPP_URL, body)
                    self.assertNotIn(str(USER_ID), body)
