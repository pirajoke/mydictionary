from __future__ import annotations

import os
from pathlib import Path
import re
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, MagicMock, patch


os.environ.setdefault("BOT_TOKEN", "123456:TESTTOKEN_ABCDEFGHIJKLMNOP")
os.environ.setdefault("ALLOWED_USER_ID", "1")
os.environ.setdefault("ALLOW_SQLITE_DEV", "true")

import bot
from mydictionary.miniapp import MINIAPP_COPY


ROOT = Path(__file__).resolve().parents[1]
HTML_PATH = ROOT / "mydictionary/templates/miniapp.html"
CSS_PATH = ROOT / "mydictionary/static/miniapp.css"
JS_PATH = ROOT / "mydictionary/static/miniapp.js"
LOCALES = {"en", "fr", "de", "ja", "ar", "zh", "ru", "es"}
NEW_COPY_KEYS = {
    "settings_credit_cta",
    "settings_dictionary",
    "settings_learning_plan",
    "settings_tutor_preferences",
    "settings_help",
}
SETTINGS_ACTIONS = {
    "settings-invite": "invite",
    "settings-dictionary": "lang",
    "settings-learning-plan": "settings",
    "settings-ai-tutor": "ai",
    "settings-tutor-preferences": "settings",
    "settings-help": "help",
    "settings-privacy": "privacy",
}


def opening_tag(source: str, element_id: str) -> str:
    match = re.search(
        rf"<[^>]+\bid=[\"']{re.escape(element_id)}[\"'][^>]*>",
        source,
        re.IGNORECASE,
    )
    if match is None:
        raise AssertionError(f"missing element #{element_id}")
    return match.group(0)


def css_rule(source: str, selector: str) -> str:
    match = re.search(
        rf"{re.escape(selector)}\s*\{{([^}}]*)\}}",
        source,
        re.IGNORECASE | re.DOTALL,
    )
    if match is None:
        raise AssertionError(f"missing CSS rule {selector}")
    return match.group(1)


def javascript_function(source: str, function_name: str) -> str:
    start = source.find(f"function {function_name}(")
    if start < 0:
        raise AssertionError(f"missing JavaScript function {function_name}")
    next_function = source.find("\n  function ", start + 1)
    if next_function < 0:
        next_function = len(source)
    return source[start:next_function]


class MiniAppSettingsHubV1SurfaceContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.html = HTML_PATH.read_text(encoding="utf-8")
        cls.css = CSS_PATH.read_text(encoding="utf-8")
        cls.js = JS_PATH.read_text(encoding="utf-8")
        start = cls.html.find('<section id="panel-settings"')
        end = cls.html.find('<nav class="bottom-nav"', start)
        if start < 0 or end < 0:
            raise AssertionError("missing bounded Settings panel")
        cls.settings_panel = cls.html[start:end]

    def test_ac1_ec2_actionable_hierarchy_uses_real_workflows_and_honest_credit_cta(self):
        cta = opening_tag(self.settings_panel, "settings-credit-cta")
        self.assertRegex(cta, r"<button\b")
        self.assertIn('type="button"', cta)
        self.assertIn('data-settings-target="credits"', cta)
        self.assertIn('aria-describedby="settings-credit-balance"', cta)
        self.assertNotIn("disabled", cta)
        self.assertIn('id="settings-credit-balance"', self.settings_panel)

        for element_id, action in SETTINGS_ACTIONS.items():
            with self.subTest(element_id=element_id):
                tag = opening_tag(self.settings_panel, element_id)
                self.assertRegex(tag, r"<button\b")
                self.assertIn('type="button"', tag)
                self.assertIn(f'data-settings-action="{action}"', tag)

        for group_id in (
            "settings-account-group",
            "settings-learning-group",
            "settings-tutor-group",
            "settings-support-group",
        ):
            self.assertIn(f'id="{group_id}"', self.settings_panel)

        self.assertRegex(
            self.js,
            r'node\("settings-credit-cta"\)\.addEventListener\('
            r'"click",\s*\(\)\s*=>\s*activateTab\(node\("tab-credits"\)\)\)',
        )
        unsupported = (
            "unlimited",
            "gift subscription",
            "voice speed",
            "change voice",
            "choose topics",
        )
        lowered = self.settings_panel.casefold()
        self.assertEqual([term for term in unsupported if term in lowered], [])

    def test_ac2_ec1_current_context_is_direct_bounded_and_zero_safe(self):
        for element_id in (
            "settings-credit-balance",
            "settings-dictionary-value",
            "settings-learning-plan-value",
            "settings-ai-tutor-value",
            "settings-tutor-preferences-value",
        ):
            self.assertIn(f'id="{element_id}"', self.settings_panel)

        required_bindings = (
            r'text\(node\("settings-credit-balance"\),\s*data\.credits\.available\)',
            r'node\("settings-dictionary-value"\)',
            r'data\.settings\.daily_goal',
            r'data\.settings\.learning_goal',
            r'data\.settings\.mirror_style',
            r'data\.settings\.mirror_depth',
            r'data\.settings\.mirror_level',
            r'copy\.setting_unknown',
            r'node\("settings-ai-tutor"\)\.disabled\s*=\s*!data\.features\.ai',
            r'data\.features\.ai\s*\?\s*copy\.feature_enabled\s*:\s*copy\.feature_disabled',
        )
        self.assertEqual(
            [pattern for pattern in required_bindings if not re.search(pattern, self.js)],
            [],
        )
        self.assertNotRegex(
            self.js,
            r'data\.credits\.available\s*\|\|\s*["\']',
            "zero credits must not be replaced by a truthy fallback",
        )

        row_copy = css_rule(self.css, ".settings-row-copy")
        row_value = css_rule(self.css, ".settings-row-value")
        self.assertRegex(row_copy, r"min-width\s*:\s*0")
        self.assertRegex(row_value, r"overflow-wrap\s*:\s*anywhere")

    def test_ac3_err1_referral_entry_points_share_one_fail_closed_state_machine(self):
        credits_invite = opening_tag(self.html, "referral-invite")
        settings_invite = opening_tag(self.settings_panel, "settings-invite")
        self.assertIn("data-referral-invite", credits_invite)
        self.assertIn("data-referral-invite", settings_invite)
        self.assertIn('id="settings-invite-status"', self.settings_panel)
        settings_status = opening_tag(self.settings_panel, "settings-invite-status")
        self.assertIn("data-referral-status", settings_status)
        self.assertIn('aria-live="polite"', settings_status)

        invite = javascript_function(self.js, "issueReferralInvite")
        required_tokens = (
            'document.querySelectorAll("[data-referral-invite]")',
            'document.querySelectorAll("[data-referral-status]")',
            "referralInvitePending",
            "!webApp",
            "!webApp.initData",
            "validReferralInviteUrl(result.invite_url)",
            "copy.referral_pending",
            "copy.referral_error",
            "copy.referral_retry",
            "disabled = true",
            "disabled = false",
            'setAttribute("aria-busy", "true")',
            'removeAttribute("aria-busy")',
            "webApp.openTelegramLink(shareUrl)",
        )
        self.assertEqual([token for token in required_tokens if token not in invite], [])
        self.assertLess(
            invite.index("validReferralInviteUrl(result.invite_url)"),
            invite.index("webApp.openTelegramLink(shareUrl)"),
        )
        self.assertRegex(
            self.js,
            r'document\.querySelectorAll\("\[data-referral-invite\]"\)'
            r'\.forEach\(\([^)]*\)\s*=>\s*[^;]*addEventListener\('
            r'"click",\s*issueReferralInvite\)',
        )

    def test_ac5_localized_labels_and_inline_locale_control_are_complete(self):
        self.assertEqual(set(MINIAPP_COPY), LOCALES)
        required = NEW_COPY_KEYS | {
            "referral_invite",
            "ai_tutor",
            "privacy",
            "setting_interface_language",
            "feature_enabled",
            "feature_disabled",
            "setting_unknown",
        }
        for locale, copy in MINIAPP_COPY.items():
            with self.subTest(locale=locale):
                self.assertEqual(
                    sorted(key for key in required if not str(copy.get(key, "")).strip()),
                    [],
                )

        for key in NEW_COPY_KEYS | {"referral_invite", "ai_tutor", "privacy"}:
            self.assertIn(f'data-i18n="{key}"', self.settings_panel)
        for token in (
            'id="settings-interface-locale"',
            'id = "interface-locale-select"',
            '"/miniapp/api/interface-locale"',
            "switchInterfaceLocale(select.value, select, status, copy)",
        ):
            self.assertIn(token, f"{self.settings_panel}\n{self.js}")

    def test_ac5_inline_locale_control_receives_authenticated_bootstrap_data(self):
        self.assertIn(
            "function addInterfaceLocaleSetting(container, data, copy)",
            self.js,
        )
        self.assertIn(
            'addInterfaceLocaleSetting(node("settings-interface-locale-control"), data, copy)',
            self.js,
        )

    def test_ac6_reference_inspired_icons_targets_themes_rtl_and_motion_are_local(self):
        row_tags = [
            opening_tag(self.settings_panel, element_id)
            for element_id in SETTINGS_ACTIONS
        ]
        self.assertTrue(all('class="settings-hub-row' in tag for tag in row_tags))
        icons = re.findall(
            r'<svg\b(?=[^>]*\bclass=["\'][^"\']*\bsettings-row-icon\b[^"\']*["\'])[^>]*>',
            self.settings_panel,
            re.IGNORECASE,
        )
        chevrons = re.findall(
            r'<svg\b(?=[^>]*\bclass=["\'][^"\']*\bsettings-chevron\b[^"\']*["\'])[^>]*>',
            self.settings_panel,
            re.IGNORECASE,
        )
        self.assertGreaterEqual(len(icons), len(SETTINGS_ACTIONS))
        self.assertEqual(len(chevrons), len(SETTINGS_ACTIONS))
        self.assertTrue(
            all('aria-hidden="true"' in tag and 'focusable="false"' in tag for tag in icons + chevrons)
        )
        self.assertGreaterEqual(
            len(set(re.findall(r"settings-tile--[a-z]+", self.settings_panel))),
            4,
        )

        row_style = css_rule(self.css, ".settings-hub-row")
        tile_style = css_rule(self.css, ".settings-icon-tile")
        self.assertRegex(row_style, r"min-height\s*:\s*(?:44px|var\(--dashboard-row-height\))")
        self.assertRegex(row_style, r"grid-template-columns\s*:\s*auto\s+minmax\(0,\s*1fr\)\s+auto")
        self.assertIn("var(--dashboard", f"{row_style}\n{tile_style}")
        for token in (
            ".settings-hub-row:focus-visible",
            'html[dir="rtl"] .settings-chevron',
            "@media (max-width: 359px)",
            "@media (prefers-reduced-motion: reduce)",
            "min-width: 320px",
        ):
            self.assertIn(token, self.css)
        settings_art = re.findall(r'<img\b[^>]*class="section-art"[^>]*>', self.settings_panel)
        self.assertEqual(len(settings_art), 1)
        self.assertIn("lexi-section-settings-v1.webp", settings_art[0])
        self.assertIn('alt=""', settings_art[0])
        self.assertIn('loading="lazy"', settings_art[0])
        self.assertNotRegex(self.settings_panel, r'https?://')

    def test_err2_external_actions_require_telegram_bridge_and_bot_username(self):
        action_link = javascript_function(self.js, "actionLink")
        open_action = javascript_function(self.js, "openAction")
        self.assertIn("if (!payload || !botUsername) return \"\";", action_link)
        self.assertRegex(
            open_action,
            r'if\s*\(!webApp\s*\|\|\s*!botUsername\)\s*return;',
        )
        self.assertIn("const url = actionLink(action);", open_action)
        self.assertIn("if (url) webApp.openTelegramLink(url);", open_action)
        self.assertNotIn("window.location", self.js)


class MiniAppSettingsHubV1BotContractTest(unittest.IsolatedAsyncioTestCase):
    def test_ac4_help_and_settings_are_allowlisted_while_unknown_actions_are_rejected(self):
        for action in ("learn", "continue", "ai", "buy", "lang", "settings", "privacy", "help"):
            with self.subTest(action=action):
                self.assertEqual(
                    bot.miniapp_start_action(f"miniapp_{action}"),
                    action,
                )
        for payload in ("miniapp_unknown", "miniapp_", "unknown", None):
            with self.subTest(payload=payload):
                self.assertIsNone(bot.miniapp_start_action(payload))

    async def test_ac4_help_and_settings_route_explicitly_and_unknown_never_falls_through(self):
        message = SimpleNamespace(reply_text=AsyncMock())
        update = SimpleNamespace(
            message=message,
            effective_message=message,
            effective_user=SimpleNamespace(id=7001, language_code="en"),
        )
        context = SimpleNamespace(args=["preserve"], user_data={})
        runtime = SimpleNamespace(
            role="admin",
            user_id=7001,
            store=MagicMock(),
            interface_locale="en",
        )
        runtime.store.product_profile.return_value = {"daily_word_goal": 10}
        runtime.store.get_mirror_preferences.side_effect = ValueError("not configured")
        active_token = bot._ACTIVE_RUNTIME.set(runtime)
        try:
            with (
                patch.object(bot, "active_content_pack", return_value=object()),
                patch.object(bot, "settings_text", return_value="settings"),
                patch.object(bot, "settings_keyboard", return_value=object()),
                patch.object(
                    bot,
                    "AdminStore",
                    return_value=SimpleNamespace(
                        get_mirror_control_plane=lambda: {}
                    ),
                ),
            ):
                for action, handler_name in (("help", "cmd_help"), ("settings", "cmd_settings")):
                    handler = SimpleNamespace(__wrapped__=AsyncMock())
                    with self.subTest(action=action), patch.object(
                        bot, handler_name, handler, create=True
                    ):
                        await bot.route_miniapp_start_action(action, update, context)
                        handler.__wrapped__.assert_awaited_once_with(update, context)
                        self.assertEqual(context.args, ["preserve"])

                message.reply_text.reset_mock()
                await bot.route_miniapp_start_action("unknown", update, context)
                message.reply_text.assert_not_awaited()
                self.assertEqual(context.args, ["preserve"])
        finally:
            bot._ACTIVE_RUNTIME.reset(active_token)


if __name__ == "__main__":
    unittest.main()
