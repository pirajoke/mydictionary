from __future__ import annotations

from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
HTML_PATH = ROOT / "mydictionary/templates/miniapp.html"
CSS_PATH = ROOT / "mydictionary/static/miniapp.css"
JS_PATH = ROOT / "mydictionary/static/miniapp.js"

TABS = ("profile", "words", "credits", "languages", "settings")


def opening_tag(source: str, element_id: str) -> str:
    match = re.search(
        rf"<[^>]+\bid=[\"']{re.escape(element_id)}[\"'][^>]*>",
        source,
        re.IGNORECASE,
    )
    if match is None:
        raise AssertionError(f"missing element #{element_id}")
    return match.group(0)


def has_class(tag: str, class_name: str) -> bool:
    match = re.search(r"\bclass=[\"']([^\"']*)[\"']", tag, re.IGNORECASE)
    return bool(match and class_name in match.group(1).split())


class MiniAppDashboardDesignV1ContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.html = HTML_PATH.read_text(encoding="utf-8")
        cls.css = CSS_PATH.read_text(encoding="utf-8")
        cls.js = JS_PATH.read_text(encoding="utf-8")
        cls.combined = f"{cls.html}\n{cls.css}\n{cls.js}"

    def test_ac1_all_five_tabs_use_one_compact_dashboard_shell(self):
        app_content = opening_tag(self.html, "app-content")
        violations: list[str] = []
        if not has_class(app_content, "dashboard"):
            violations.append("#app-content:dashboard")

        for tab in TABS:
            panel = opening_tag(self.html, f"panel-{tab}")
            if not has_class(panel, "dashboard-panel"):
                violations.append(f"#panel-{tab}:dashboard-panel")
            if not re.search(
                rf'<header(?=[^>]*\bclass=["\'][^"\']*\bdashboard-header\b)[^>]*>'
                rf'.*?data-i18n=["\']{tab}["\']',
                self.html[self.html.index(panel) :],
                re.IGNORECASE | re.DOTALL,
            ):
                violations.append(f"#panel-{tab}:dashboard-header")

        for primitive in (
            ".dashboard",
            ".dashboard-panel",
            ".dashboard-header",
            ".dashboard-section",
            ".dashboard-list",
            ".dashboard-row",
            ".dashboard-metric",
            ".dashboard-action",
            ".dashboard-state",
        ):
            if primitive not in self.combined:
                violations.append(f"primitive:{primitive}")

        self.assertEqual(violations, [])

    def test_ac2_to_ac6_every_tab_keeps_its_product_content_and_controls(self):
        required_ids = {
            # Profile: identity, balance, actions, streak/calendar and detail metrics.
            "display-name",
            "profile-photo",
            "profile-avatar-fallback",
            "profile-language",
            "profile-credit-balance",
            "streak-count",
            "best-streak",
            "calendar-previous",
            "calendar-next",
            "calendar-grid",
            "profile-metrics",
            # My words: summary, rows and teaching empty state.
            "word-summary",
            "word-list",
            "empty-words",
            # Credits: totals, policy, packs and checkout state.
            "wallet-available",
            "credit-summary",
            "credit-contract",
            "product-list",
            "checkout-disabled",
            # Languages: current, switch list and fallback action.
            "language-current",
            "language-list",
            # Settings: learning, Tutor, features and bot language status.
            "settings-learning",
            "settings-tutor",
            "settings-features",
        }
        missing_or_duplicated = sorted(
            element_id
            for element_id in required_ids
            if len(
                re.findall(
                    rf"\bid=[\"']{re.escape(element_id)}[\"']",
                    self.combined,
                )
            )
            != 1
        )
        self.assertEqual(missing_or_duplicated, [])

        data_contracts = (
            "progress.today_xp",
            "progress.learned_words",
            "data.profile.daily_word_goal",
            "data.credits.available",
            "data.credits.reserved",
            "data.credits.spent",
            "data.products.forEach",
            "data.languages.filter",
            "language.word_count",
            "language.current",
            "copy.setting_interface_language",
            "data.features.ai",
            "data.features.voice",
        )
        self.assertEqual(
            [contract for contract in data_contracts if contract not in self.js],
            [],
        )

    def test_ac7_theme_tokens_are_telegram_adaptive_with_safe_light_fallback(self):
        theme_sources = {
            "--dashboard-bg": "--tg-theme-bg-color",
            "--dashboard-surface": "--tg-theme-secondary-bg-color",
            "--dashboard-text": "--tg-theme-text-color",
            "--dashboard-muted": "--tg-theme-hint-color",
            "--dashboard-line": "--tg-theme-section-separator-color",
            "--dashboard-accent": "--tg-theme-button-color",
            "--dashboard-accent-text": "--tg-theme-button-text-color",
        }
        violations = []
        for token, telegram_source in theme_sources.items():
            declaration = re.search(
                rf"{re.escape(token)}\s*:\s*([^;]+);",
                self.css,
            )
            if declaration is None or telegram_source not in declaration.group(1):
                violations.append(f"{token}->{telegram_source}")

        for token in (
            "--dashboard-radius",
            "--dashboard-gap",
            "--dashboard-row-height",
        ):
            if not re.search(rf"{re.escape(token)}\s*:\s*[^;]+;", self.css):
                violations.append(token)

        if "@media (prefers-color-scheme: light)" not in self.css:
            violations.append("light-fallback")
        if "color-scheme: light dark" not in self.css:
            violations.append("light-dark-scheme")
        self.assertEqual(violations, [])

    def test_ac7_ec2_responsive_rtl_focus_motion_and_touch_contracts_remain(self):
        required_css = (
            "min-width: 320px",
            "width: min(100%, 720px)",
            "min-height: 44px",
            ":focus-visible",
            "env(safe-area-inset-top)",
            "env(safe-area-inset-right)",
            "env(safe-area-inset-bottom)",
            "env(safe-area-inset-left)",
            "@media (max-width: 359px)",
            "@media (min-width: 560px)",
            "@media (prefers-reduced-motion: reduce)",
            "overflow-wrap: anywhere",
        )
        violations = [item for item in required_css if item not in self.css]
        if not re.search(r"overflow-x\s*:\s*(?:hidden|clip)", self.css):
            violations.append("horizontal-overflow-guard")
        if 'document.documentElement.dir = "rtl"' not in self.js:
            violations.append("runtime-rtl")
        if "viewport-fit=cover" not in self.html:
            violations.append("viewport-safe-area")
        if "text-overflow: ellipsis" in self.css:
            violations.append("clipped-navigation-label")
        self.assertEqual(violations, [])

    def test_err1_states_share_one_accessible_dashboard_vocabulary(self):
        static_states = {
            "loading-state": ("loading", "status"),
            "error-state": ("error", "alert"),
            "empty-words": ("empty", "status"),
            "checkout-disabled": ("disabled", "status"),
        }
        violations = []
        for element_id, (state, role) in static_states.items():
            tag = opening_tag(self.html, element_id)
            if not has_class(tag, "dashboard-state"):
                violations.append(f"#{element_id}:dashboard-state")
            if f'data-ui-state="{state}"' not in tag:
                violations.append(f"#{element_id}:data-ui-state={state}")
            if f'role="{role}"' not in tag:
                violations.append(f"#{element_id}:role={role}")

        # Language and bot-locale mutations render their pending/error status in JS.
        for function_name in ("languageSwitchStatus", "localeRetryStatus"):
            start = self.js.find(f"function {function_name}")
            body = self.js[start : start + 1_400] if start >= 0 else ""
            if "dashboard-state" not in body:
                violations.append(f"{function_name}:dashboard-state")
            if 'setAttribute("role", "status")' not in body:
                violations.append(f"{function_name}:role=status")

        for state in ("loading", "error", "empty", "disabled", "pending"):
            if not re.search(
                rf"\.dashboard-state(?:\[[^]]*{state}[^]]*\]|\.{state}\b)",
                self.css,
            ):
                violations.append(f"state-style:{state}")
        self.assertEqual(violations, [])

    def test_ec1_existing_ids_actions_tabs_and_aria_are_preserved(self):
        for tab in TABS:
            tab_tag = opening_tag(self.html, f"tab-{tab}")
            panel_tag = opening_tag(self.html, f"panel-{tab}")
            self.assertIn('role="tab"', tab_tag)
            self.assertIn(f'aria-controls="panel-{tab}"', tab_tag)
            self.assertIn(f'data-tab="{tab}"', tab_tag)
            self.assertIn('role="tabpanel"', panel_tag)
            self.assertIn(f'aria-labelledby="tab-{tab}"', panel_tag)
            self.assertIn(f'data-panel="{tab}"', panel_tag)

        self.assertEqual(
            set(re.findall(r'data-action=["\']([^"\']+)["\']', self.html)),
            {"learn", "share", "ai", "lang", "settings", "privacy"},
        )
        self.assertIn('aria-live="polite"', self.html)
        for key in ('"ArrowLeft"', '"ArrowRight"', '"Home"', '"End"'):
            self.assertIn(key, self.js)

    def test_err2_redesign_adds_no_network_or_product_behavior(self):
        fetch_targets = set(
            re.findall(r"fetch\(\s*[\"']([^\"']+)[\"']", self.js)
        )
        self.assertEqual(
            fetch_targets,
            {
                "/miniapp/api/bootstrap",
                "/miniapp/api/active-pack",
                "/miniapp/api/interface-locale",
            },
        )
        self.assertNotRegex(
            self.combined.casefold(),
            r"lottery|ticket exchange|daily reward|unlimited access|subscription",
        )
        self.assertNotRegex(
            self.html,
            r'<script(?![^>]+(?:telegram-web-app\.js|miniapp\.js))[^>]+src=',
        )


if __name__ == "__main__":
    unittest.main()
