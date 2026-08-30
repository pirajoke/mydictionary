from __future__ import annotations

import ast
from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
HTML_PATH = ROOT / "mydictionary/templates/miniapp.html"
CSS_PATH = ROOT / "mydictionary/static/miniapp.css"
JS_PATH = ROOT / "mydictionary/static/miniapp.js"
MINIAPP_PY_PATH = ROOT / "mydictionary/miniapp.py"

TABS = ("profile", "words", "credits", "languages", "settings")
PRESERVED_PROFILE_IDS = {
    "panel-profile",
    "profile-label",
    "profile-photo",
    "profile-avatar-fallback",
    "display-name",
    "profile-language",
    "profile-credit-balance",
    "streak-count",
    "best-streak",
    "calendar-title",
    "calendar-month",
    "calendar-previous",
    "calendar-next",
    "calendar-grid",
    "profile-metrics",
}
EXISTING_GAME_COPY_KEYS = {
    "profile",
    "metric_level",
    "metric_xp",
    "metric_streak",
    "metric_accuracy",
    "metric_learned_words",
    "metric_today_xp",
    "metric_daily_goal",
    "metric_best_streak",
    "metric_sessions",
    "metric_tracked_words",
    "daily_quest",
    "continue_lesson",
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


def element_region(source: str, element_id: str, tag: str) -> str:
    match = re.search(
        rf"<{tag}\b(?=[^>]*\bid=[\"']{re.escape(element_id)}[\"'])[^>]*>.*?</{tag}>",
        source,
        re.IGNORECASE | re.DOTALL,
    )
    if match is None:
        raise AssertionError(f"missing <{tag}> region #{element_id}")
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


class MiniAppProfileGameV1ContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.html = HTML_PATH.read_text(encoding="utf-8")
        cls.css = CSS_PATH.read_text(encoding="utf-8")
        cls.js = JS_PATH.read_text(encoding="utf-8")
        cls.miniapp_py = MINIAPP_PY_PATH.read_text(encoding="utf-8")
        render_start = cls.js.find("function render(data)")
        if render_start < 0:
            raise AssertionError("missing public Mini App render(data) function")
        cls.render = cls.js[render_start:]

    def test_ac1_one_text_accessible_level_xp_game_surface_uses_real_values(self):
        surface = element_region(self.html, "profile-game-progress", "section")
        self.assertEqual(self.html.count('id="profile-game-progress"'), 1)
        self.assertIn('aria-labelledby="profile-game-title"', opening_tag(self.html, "profile-game-progress"))

        for element_id, copy_key, binding in (
            ("profile-level", "metric_level", r'text\(node\("profile-level"\),\s*progress\.level\)'),
            ("profile-xp", "metric_xp", r'text\(node\("profile-xp"\),\s*progress\.xp\)'),
        ):
            self.assertEqual(surface.count(f'id="{element_id}"'), 1)
            self.assertIn(f'data-i18n="{copy_key}"', surface)
            self.assertRegex(self.render, binding)

        progress_style = css_rule(self.css, ".profile-game-progress")
        self.assertRegex(progress_style, r"var\(--dashboard-(?:accent|surface|elevated|soft-accent|text)\)")
        for invented_contract in (
            "next_level",
            "nextLevel",
            "xp_to_next",
            "xpToNext",
            "progress_percent",
            "progressPercent",
        ):
            self.assertNotIn(invented_contract, f"{surface}\n{self.render}")

    def test_ac2_exactly_three_visible_real_achievements(self):
        strip = element_region(self.html, "profile-achievements", "section")
        self.assertIn('role="list"', opening_tag(self.html, "profile-achievements"))
        cards = re.findall(
            r'<[^>]+\bclass=["\'][^"\']*\bprofile-achievement\b[^"\']*["\'][^>]*>',
            strip,
            re.IGNORECASE,
        )
        self.assertEqual(len(cards), 3)
        self.assertTrue(all('role="listitem"' in card for card in cards))

        bindings = {
            "achievement-streak-value": r'text\(node\("achievement-streak-value"\),\s*progress\.streak\)',
            "achievement-accuracy-value": (
                r'text\(node\("achievement-accuracy-value"\),\s*'
                r'`\$\{progress\.accuracy\.correct\}/\$\{progress\.accuracy\.total\}`\)'
            ),
            "achievement-learned-value": r'text\(node\("achievement-learned-value"\),\s*progress\.learned_words\)',
        }
        for element_id, binding in bindings.items():
            self.assertEqual(strip.count(f'id="{element_id}"'), 1)
            self.assertRegex(self.render, binding)

        achievement_style = css_rule(self.css, ".profile-achievements")
        self.assertRegex(achievement_style, r"repeat\(3,\s*minmax\(0,\s*1fr\)\)")

    def test_ac2_ac4_best_streak_cannot_be_a_fourth_or_nested_achievement(self):
        strip = element_region(self.html, "profile-achievements", "section")
        self.assertNotRegex(
            strip,
            r'\bid=["\']best-streak["\']|'
            r'\bdata-i18n=["\'](?:best_streak_short|metric_best_streak)["\']',
        )

        details = re.search(
            r'<details\b(?=[^>]*\bclass=["\'][^"\']*\bprogress-details\b)[^>]*>'
            r'.*?</details>',
            self.html,
            re.IGNORECASE | re.DOTALL,
        )
        self.assertIsNotNone(details)
        self.assertEqual(len(re.findall(r'\bid=["\']best-streak["\']', self.html)), 1)
        self.assertRegex(details.group(0), r'\bid=["\']best-streak["\']')

        metric_render = re.search(
            r'node\("profile-metrics"\)\.replaceChildren\((.*?)\n\s*\);',
            self.render,
            re.DOTALL,
        )
        self.assertIsNotNone(metric_render)
        self.assertIn("metric(copy.metric_best_streak, progress.best_streak)", metric_render.group(1))

    def test_ac3_daily_quest_uses_real_goal_today_xp_and_existing_learn_action(self):
        quest = element_region(self.html, "daily-quest", "section")
        self.assertIn('aria-labelledby="daily-quest-title"', opening_tag(self.html, "daily-quest"))
        self.assertIn('id="daily-quest-today-xp"', quest)
        self.assertIn('data-i18n="metric_today_xp"', quest)
        self.assertIn('id="daily-quest-goal"', quest)
        self.assertIn('data-i18n="metric_daily_goal"', quest)
        self.assertRegex(
            quest,
            r'<button\b(?=[^>]*\bdata-action=["\']learn["\'])'
            r'(?=[^>]*\bdata-i18n=["\']continue_lesson["\'])[^>]*>',
        )
        self.assertRegex(
            self.render,
            r'text\(node\("daily-quest-today-xp"\),\s*progress\.today_xp\)',
        )
        self.assertRegex(
            self.render,
            r'text\(node\("daily-quest-goal"\),\s*data\.profile\.daily_word_goal\)',
        )

    def test_ac3_ec2_daily_quest_heading_has_distinct_copy_in_all_eight_locales(self):
        quest = element_region(self.html, "daily-quest", "section")
        title_tag = opening_tag(quest, "daily-quest-title")
        violations = []
        if 'data-i18n="daily_quest"' not in title_tag:
            violations.append("template:#daily-quest-title->daily_quest")
        if not re.search(
            r'<button\b(?=[^>]*\bdata-action=["\']learn["\'])'
            r'(?=[^>]*\bdata-i18n=["\']continue_lesson["\'])[^>]*>',
            quest,
        ):
            violations.append("template:learn-cta->continue_lesson")

        copy_node = next(
            (
                statement.value
                for statement in ast.parse(self.miniapp_py).body
                if isinstance(statement, ast.AnnAssign)
                and isinstance(statement.target, ast.Name)
                and statement.target.id == "MINIAPP_COPY"
            ),
            None,
        )
        self.assertIsNotNone(copy_node, "missing MINIAPP_COPY localization contract")
        copy_by_locale = ast.literal_eval(copy_node)
        self.assertEqual(set(copy_by_locale), {"en", "fr", "de", "ja", "ar", "zh", "ru", "es"})
        for locale, copy in copy_by_locale.items():
            heading = str(copy.get("daily_quest", "")).strip()
            if not heading:
                violations.append(f"{locale}:missing-daily_quest")
            elif heading.casefold() == str(copy.get("continue_lesson", "")).strip().casefold():
                violations.append(f"{locale}:daily_quest-duplicates-continue_lesson")

        self.assertEqual(violations, [])

    def test_ac4_details_are_collapsed_and_have_at_most_four_nonduplicated_metrics(self):
        details_tag = re.search(
            r'<details\b(?=[^>]*\bclass=["\'][^"\']*\bprogress-details\b)[^>]*>',
            self.html,
            re.IGNORECASE,
        )
        self.assertIsNotNone(details_tag)
        self.assertNotRegex(details_tag.group(0), r"\sopen(?:\s|=|>)")

        metric_render = re.search(
            r'node\("profile-metrics"\)\.replaceChildren\((.*?)\n\s*\);',
            self.render,
            re.DOTALL,
        )
        self.assertIsNotNone(metric_render)
        metric_calls = re.findall(r"\bmetric\(([^\n]+)", metric_render.group(1))
        self.assertLessEqual(len(metric_calls), 4)
        self.assertEqual(len(metric_calls), len(set(metric_calls)))

        duplicated_primary_values = {
            "copy.metric_level",
            "copy.metric_xp",
            "copy.metric_streak",
            "copy.metric_accuracy",
            "copy.metric_today_xp",
            "copy.metric_daily_goal",
            "copy.metric_learned_words",
            "copy.metric_ai_credits",
        }
        self.assertEqual(
            sorted(
                value
                for value in duplicated_primary_values
                if value in metric_render.group(1)
            ),
            [],
        )

    def test_ac5_existing_profile_tabs_actions_and_api_targets_are_preserved(self):
        missing_or_duplicated = sorted(
            element_id
            for element_id in PRESERVED_PROFILE_IDS
            if len(re.findall(rf'\bid=["\']{re.escape(element_id)}["\']', self.html)) != 1
        )
        self.assertEqual(missing_or_duplicated, [])

        for tab in TABS:
            tab_tag = opening_tag(self.html, f"tab-{tab}")
            panel_tag = opening_tag(self.html, f"panel-{tab}")
            self.assertIn('role="tab"', tab_tag)
            self.assertIn(f'aria-controls="panel-{tab}"', tab_tag)
            self.assertIn(f'data-tab="{tab}"', tab_tag)
            self.assertIn('role="tabpanel"', panel_tag)
            self.assertIn(f'aria-labelledby="tab-{tab}"', panel_tag)

        self.assertEqual(
            set(re.findall(r'data-action=["\']([^"\']+)["\']', self.html)),
            {"learn", "share", "ai", "lang", "settings", "privacy"},
        )
        self.assertEqual(
            set(re.findall(r'fetch\(\s*["\']([^"\']+)["\']', self.js)),
            {
                "/miniapp/api/bootstrap",
                "/miniapp/api/active-pack",
                "/miniapp/api/interface-locale",
            },
        )

    def test_ec1_ec2_game_ui_is_320px_rtl_accessible_and_motion_safe(self):
        profile = element_region(self.html, "panel-profile", "section")
        new_ui = "\n".join(
            element_region(self.html, element_id, "section")
            for element_id in ("profile-game-progress", "profile-achievements", "daily-quest")
        )
        new_copy_keys = set(re.findall(r'data-i18n=["\']([^"\']+)["\']', new_ui))
        self.assertEqual(new_copy_keys - EXISTING_GAME_COPY_KEYS, set())

        decorative_icons = re.findall(
            r'<span\b(?=[^>]*\bclass=["\'][^"\']*\b(?:game|achievement|quest)-icon\b[^"\']*["\'])[^>]*>',
            new_ui,
            re.IGNORECASE,
        )
        self.assertGreaterEqual(len(decorative_icons), 3)
        self.assertTrue(all('aria-hidden="true"' in icon for icon in decorative_icons))
        self.assertNotRegex(profile, r'<(?:button|summary)\b[^>]*tabindex=["\']-1["\']')

        required_css = (
            "min-width: 320px",
            "min-height: 44px",
            ":focus-visible",
            "@media (max-width: 359px)",
            "@media (prefers-reduced-motion: reduce)",
            "animation-duration: .001ms",
        )
        self.assertEqual([token for token in required_css if token not in self.css], [])
        self.assertRegex(self.css, r"overflow-x\s*:\s*(?:hidden|clip)")
        self.assertIn('document.documentElement.dir = "rtl"', self.js)
        self.assertRegex(css_rule(self.css, ".calendar-grid"), r"direction\s*:\s*ltr")

    def test_err1_zero_values_remain_visible_and_honest(self):
        self.assertIn(
            'const text = (element, value) => { element.textContent = String(value ?? ""); };',
            self.js,
        )
        honest_bindings = (
            r'text\(node\("profile-level"\),\s*progress\.level\)',
            r'text\(node\("profile-xp"\),\s*progress\.xp\)',
            r'text\(node\("achievement-streak-value"\),\s*progress\.streak\)',
            r'text\(node\("achievement-accuracy-value"\),\s*`\$\{progress\.accuracy\.correct\}/\$\{progress\.accuracy\.total\}`\)',
            r'text\(node\("achievement-learned-value"\),\s*progress\.learned_words\)',
            r'text\(node\("daily-quest-today-xp"\),\s*progress\.today_xp\)',
            r'text\(node\("daily-quest-goal"\),\s*data\.profile\.daily_word_goal\)',
        )
        self.assertEqual(
            [binding for binding in honest_bindings if re.search(binding, self.render) is None],
            [],
        )
        for surface_id in ("profile-game-progress", "profile-achievements", "daily-quest"):
            self.assertNotIn("hidden", opening_tag(self.html, surface_id))


if __name__ == "__main__":
    unittest.main()
