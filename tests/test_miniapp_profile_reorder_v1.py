from __future__ import annotations

from html.parser import HTMLParser
from pathlib import Path
import re
import unittest

from mydictionary.miniapp import MINIAPP_COPY


ROOT = Path(__file__).resolve().parents[1]
HTML_PATH = ROOT / "mydictionary/templates/miniapp.html"
CSS_PATH = ROOT / "mydictionary/static/miniapp.css"
JS_PATH = ROOT / "mydictionary/static/miniapp.js"
LOCALES = {"en", "fr", "de", "ja", "ar", "zh", "ru", "es"}
EXPECTED_PROFILE_BLOCKS = (
    ("header", None, "section-hero", None),
    ("section", None, "streak-card", None),
    ("div", None, "profile-identity", None),
    ("section", "daily-quest", "daily-quest", None),
    ("section", "profile-game-progress", "profile-game-progress", None),
    ("section", "profile-achievements", "profile-achievements", None),
    ("details", None, "progress-details", None),
)


class Element:
    def __init__(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.tag = tag
        self.attrs = {key: value or "" for key, value in attrs}
        self.children: list[Element] = []
        self.parent: Element | None = None

    def descendants(self):
        for child in self.children:
            yield child
            yield from child.descendants()


class MiniAppDomParser(HTMLParser):
    _VOID_TAGS = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.root = Element("document", [])
        self.stack = [self.root]

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        element = Element(tag, attrs)
        element.parent = self.stack[-1]
        self.stack[-1].children.append(element)
        if tag not in self._VOID_TAGS:
            self.stack.append(element)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        if tag not in self._VOID_TAGS:
            self.stack.pop()

    def handle_endtag(self, tag: str) -> None:
        for index in range(len(self.stack) - 1, 0, -1):
            if self.stack[index].tag == tag:
                del self.stack[index:]
                return


def parse_dom(source: str) -> Element:
    parser = MiniAppDomParser()
    parser.feed(source)
    return parser.root


def find_by_id(root: Element, element_id: str) -> Element:
    matches = [element for element in root.descendants() if element.attrs.get("id") == element_id]
    if len(matches) != 1:
        raise AssertionError(f"expected one #{element_id}, found {len(matches)}")
    return matches[0]


def has_class(element: Element, class_name: str) -> bool:
    return class_name in element.attrs.get("class", "").split()


def find_descendant(root: Element, *, element_id: str | None = None, class_name: str | None = None) -> Element:
    matches = [
        element
        for element in root.descendants()
        if (element_id is None or element.attrs.get("id") == element_id)
        and (class_name is None or has_class(element, class_name))
    ]
    if len(matches) != 1:
        target = f"#{element_id}" if element_id else f".{class_name}"
        raise AssertionError(f"expected one descendant {target}, found {len(matches)}")
    return matches[0]


def javascript_function(source: str, function_name: str) -> str:
    start = source.find(f"function {function_name}(")
    if start < 0:
        raise AssertionError(f"missing JavaScript function {function_name}")
    next_function = source.find("\n  function ", start + 1)
    if next_function < 0:
        next_function = len(source)
    return source[start:next_function]


def css_rule(source: str, selector: str) -> str:
    match = re.search(
        rf"{re.escape(selector)}\s*\{{([^}}]*)\}}",
        source,
        re.IGNORECASE | re.DOTALL,
    )
    if match is None:
        raise AssertionError(f"missing CSS rule {selector}")
    return match.group(1)


class MiniAppProfileReorderV1ContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.html = HTML_PATH.read_text(encoding="utf-8")
        cls.css = CSS_PATH.read_text(encoding="utf-8")
        cls.js = JS_PATH.read_text(encoding="utf-8")
        cls.dom = parse_dom(cls.html)

    def test_ac1_profile_blocks_have_stable_allowlisted_keys_in_original_order(self):
        layout = find_by_id(self.dom, "profile-layout")
        self.assertEqual(layout.attrs.get("data-profile-layout"), "")
        self.assertEqual(layout.parent.attrs.get("id"), "panel-profile")

        items = [child for child in layout.children if "data-profile-section" in child.attrs]
        self.assertEqual(len(items), len(layout.children), "only ordered profile blocks belong in the layout")
        self.assertEqual(
            [element for element in self.dom.descendants() if "data-profile-section" in element.attrs],
            items,
            "only profile blocks may opt into reordering",
        )
        keys = [item.attrs.get("data-profile-section", "").strip() for item in items]
        self.assertTrue(all(keys), "every profile block needs a stable non-empty key")
        self.assertEqual(len(keys), len(set(keys)), "profile block keys must be unique")
        self.assertEqual(len(keys), len(EXPECTED_PROFILE_BLOCKS))

        signatures = [
            (
                item.tag,
                item.attrs.get("id") or None,
                next((name for name in item.attrs.get("class", "").split() if name in expected_classes), None),
                item.attrs.get("data-action") or None,
            )
            for item, expected_classes in zip(
                items,
                ({signature[2] for signature in EXPECTED_PROFILE_BLOCKS},) * len(items),
            )
        ]
        self.assertEqual(signatures, list(EXPECTED_PROFILE_BLOCKS))

        allowlist_match = re.search(
            r"const\s+PROFILE_SECTION_KEYS\s*=\s*Object\.freeze\(\[([^]]+)\]\)",
            self.js,
            re.DOTALL,
        )
        self.assertIsNotNone(allowlist_match, "the reorder allowlist must be explicit and immutable")
        allowlisted_keys = re.findall(r'["\']([^"\']+)["\']', allowlist_match.group(1))
        self.assertEqual(allowlisted_keys, keys)

        # Existing content and actions remain nested in the same top-level blocks.
        for item, required_id in (
            (items[0], "profile-label"),
            (items[1], "calendar-grid"),
            (items[2], "profile-photo"),
            (items[3], "daily-quest-action"),
            (items[4], "profile-level"),
            (items[5], "achievement-streak-value"),
            (items[6], "profile-metrics"),
        ):
            self.assertEqual(find_descendant(item, element_id=required_id).attrs.get("id"), required_id)
        self.assertEqual(find_descendant(items[2], class_name="profile-share").attrs.get("data-action"), "share")

    def test_regression_dictionary_shortcut_exists_only_in_words_tab(self):
        profile = find_by_id(self.dom, "panel-profile")
        words = find_by_id(self.dom, "panel-words")

        profile_dictionary_controls = [
            element for element in profile.descendants() if "data-open-dictionary" in element.attrs
        ]
        words_dictionary_controls = [
            element for element in words.descendants() if "data-open-dictionary" in element.attrs
        ]

        self.assertEqual(profile_dictionary_controls, [], "the profile must not duplicate dictionary access")
        self.assertEqual(len(words_dictionary_controls), 1, "dictionary access must remain in the Words tab")

    def test_ac2_primary_pointer_long_press_lifts_one_block_and_reorders_by_position(self):
        self.assertIsNotNone(
            re.search(r"const\s+PROFILE_REORDER_HOLD_MS\s*=\s*420\s*;", self.js),
            "the long-press threshold must be exactly 420 ms",
        )
        pointer_down = javascript_function(self.js, "handleProfilePointerDown")
        begin = javascript_function(self.js, "startProfileReorder")
        pointer_move = javascript_function(self.js, "handleProfilePointerMove")

        for token in (
            "event.isPrimary",
            "event.button",
            "PROFILE_REORDER_HOLD_MS",
            "setTimeout",
            "event.clientX",
            "event.clientY",
        ):
            with self.subTest(pointer_down=token):
                self.assertIn(token, pointer_down)
        self.assertRegex(pointer_down, r"event\.button\s*!==?\s*0")

        for token in (
            'classList.add("profile-reorder-dragging")',
            "setPointerCapture",
            "webApp.HapticFeedback",
            "impactOccurred",
        ):
            with self.subTest(begin=token):
                self.assertIn(token, begin)
        self.assertRegex(begin, r"(?:webApp\s*&&\s*webApp\.HapticFeedback|webApp\?\.HapticFeedback)")

        for token in (
            "event.clientY",
            "getBoundingClientRect",
            "insertBefore",
            "nextElementSibling",
            "event.preventDefault()",
        ):
            with self.subTest(pointer_move=token):
                self.assertIn(token, pointer_move)

        self.assertRegex(self.js, r'addEventListener\("pointerdown",\s*handleProfilePointerDown\)')
        self.assertRegex(self.js, r'addEventListener\("pointermove",\s*handleProfilePointerMove\)')
        self.assertRegex(self.js, r'addEventListener\("pointerup",\s*handleProfilePointerEnd\)')

    def test_ac3_order_persists_as_allowlisted_keys_and_restores_before_presentation(self):
        save = javascript_function(self.js, "saveProfileSectionOrder")
        restore = javascript_function(self.js, "restoreProfileSectionOrder")
        render = javascript_function(self.js, "render")

        self.assertRegex(
            self.js,
            r'const\s+PROFILE_ORDER_STORAGE_KEY\s*=\s*["\']lexi:profile-order:v1["\']\s*;',
        )
        self.assertIn(".dataset.profileSection", save)
        self.assertIn("PROFILE_SECTION_KEYS.includes", save)
        self.assertRegex(
            save,
            r"localStorage\.setItem\(PROFILE_ORDER_STORAGE_KEY,\s*JSON\.stringify\(order\)\)",
        )

        for token in (
            "localStorage.getItem(PROFILE_ORDER_STORAGE_KEY)",
            "JSON.parse",
            "Array.isArray",
            "PROFILE_SECTION_KEYS",
            "applyProfileSectionOrder",
        ):
            with self.subTest(restore=token):
                self.assertIn(token, restore)
        self.assertRegex(restore, r"try\s*\{")
        self.assertRegex(restore, r"catch\s*\(")

        restore_call = render.find("restoreProfileSectionOrder()")
        present = render.find('node("app-content").hidden = false')
        self.assertGreaterEqual(restore_call, 0, "saved profile order must be restored during render")
        self.assertGreater(present, restore_call, "restore the profile before it becomes visible")

    def test_ac4_keyboard_reorder_saves_and_announces_localized_position(self):
        move = javascript_function(self.js, "moveProfileSectionByKeyboard")
        announce = javascript_function(self.js, "announceProfileSectionPosition")
        layout = find_by_id(self.dom, "profile-layout")

        self.assertTrue(all(item.attrs.get("tabindex") == "0" for item in layout.children))
        for token in (
            "event.altKey",
            'event.key === "ArrowUp"',
            'event.key === "ArrowDown"',
            "event.preventDefault()",
            "insertBefore",
            "saveProfileSectionOrder()",
            "announceProfileSectionPosition",
        ):
            with self.subTest(move=token):
                self.assertIn(token, move)
        self.assertIn("profile_reorder_moved", announce)
        self.assertIn("position", announce)
        self.assertIn("total", announce)
        self.assertRegex(self.js, r'addEventListener\("keydown",\s*moveProfileSectionByKeyboard\)')

        live = find_by_id(self.dom, "profile-reorder-status")
        self.assertEqual(live.attrs.get("role"), "status")
        self.assertEqual(live.attrs.get("aria-live"), "polite")
        self.assertEqual(live.attrs.get("aria-atomic"), "true")

    def test_ec1_quick_press_motion_and_nested_controls_do_not_accidentally_reorder(self):
        pointer_down = javascript_function(self.js, "handleProfilePointerDown")
        pointer_move = javascript_function(self.js, "handleProfilePointerMove")
        begin = javascript_function(self.js, "startProfileReorder")
        click = javascript_function(self.js, "suppressProfileClickAfterReorder")

        selector_match = re.search(
            r'const\s+PROFILE_REORDER_NATIVE_CONTROL_SELECTOR\s*=\s*["\']([^"\']+)["\']',
            self.js,
        )
        self.assertIsNotNone(selector_match)
        selector = selector_match.group(1)
        for control in ("button", "a", "input", "select", "textarea", "summary"):
            self.assertRegex(selector, rf"(?:^|,\s*){control}(?:\s*,|$)")

        self.assertIn("closest(PROFILE_REORDER_NATIVE_CONTROL_SELECTOR)", pointer_down)
        self.assertRegex(pointer_down, r"nativeControl\s*&&\s*nativeControl\s*!==?\s*item")
        self.assertNotIn("preventDefault()", pointer_down, "quick presses must remain native")
        self.assertIn("PROFILE_REORDER_MOVE_TOLERANCE_PX", pointer_move)
        self.assertIn("Math.hypot", pointer_move)
        self.assertIn("clearTimeout", pointer_move)

        self.assertIn("profileReorderSuppressClick = true", begin)
        self.assertIn("profileReorderSuppressClick", click)
        self.assertIn("event.preventDefault()", click)
        self.assertIn("event.stopPropagation()", click)
        self.assertRegex(self.js, r'addEventListener\("click",\s*suppressProfileClickAfterReorder,\s*true\)')

    def test_ec2_saved_data_is_validated_merged_and_contains_no_profile_data(self):
        normalize = javascript_function(self.js, "normalizeProfileSectionOrder")
        save = javascript_function(self.js, "saveProfileSectionOrder")
        restore = javascript_function(self.js, "restoreProfileSectionOrder")

        for token in (
            "Array.isArray",
            "new Set",
            "PROFILE_SECTION_KEYS.includes",
            "PROFILE_SECTION_KEYS.forEach",
            ".push(",
        ):
            with self.subTest(normalize=token):
                self.assertIn(token, normalize)
        self.assertIn("normalizeProfileSectionOrder", restore)
        self.assertRegex(restore, r"catch\s*\([^)]*\)\s*\{")
        self.assertIn("applyProfileSectionOrder(PROFILE_SECTION_KEYS)", restore)

        storage_writes = re.findall(
            r"localStorage\.setItem\((.*?)\);",
            self.js,
            re.DOTALL,
        )
        profile_order_writes = [write for write in storage_writes if "PROFILE_ORDER_STORAGE_KEY" in write]
        self.assertEqual(len(profile_order_writes), 1)
        self.assertRegex(profile_order_writes[0], r"PROFILE_ORDER_STORAGE_KEY\s*,\s*JSON\.stringify\(order\)")
        all_storage_writes = "\n".join(storage_writes).casefold()
        for forbidden in ("telegram", "user_id", "display_name", "profile.photo", "credits"):
            with self.subTest(storage_forbidden=forbidden):
                self.assertNotIn(forbidden, all_storage_writes)
        lowered_save = save.casefold()
        for forbidden in ("telegram", "user_id", "display_name", "payload", "profile.photo", "credits"):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, lowered_save)

    def test_ec3_pointer_tab_and_page_cancellation_clear_drag_without_saving(self):
        cancel = javascript_function(self.js, "cancelProfileReorder")
        activate_tab = javascript_function(self.js, "activateTab")

        for token in (
            "clearTimeout",
            'classList.remove("profile-reorder-dragging")',
            "releasePointerCapture",
            "applyProfileSectionOrder",
        ):
            with self.subTest(cancel=token):
                self.assertIn(token, cancel)
        self.assertNotIn("saveProfileSectionOrder", cancel)
        self.assertIn("cancelProfileReorder()", activate_tab)

        for event_name in ("pointercancel", "lostpointercapture", "pagehide", "visibilitychange"):
            with self.subTest(event_name=event_name):
                self.assertIn(f'addEventListener("{event_name}"', self.js)
        self.assertRegex(
            self.js,
            r'document\.addEventListener\("visibilitychange",[^;]*document\.hidden[^;]*cancelProfileReorder',
        )

    def test_ec4_accessible_instructions_focus_and_reduced_motion_are_complete(self):
        layout = find_by_id(self.dom, "profile-layout")
        instructions = find_by_id(self.dom, "profile-reorder-instructions")
        self.assertEqual(instructions.attrs.get("data-i18n"), "profile_reorder_instructions")
        self.assertTrue(has_class(instructions, "visually-hidden"))
        self.assertTrue(
            all(item.attrs.get("aria-describedby") == "profile-reorder-instructions" for item in layout.children)
        )

        self.assertEqual(set(MINIAPP_COPY), LOCALES)
        for locale, copy in MINIAPP_COPY.items():
            with self.subTest(locale=locale):
                self.assertTrue(str(copy.get("profile_reorder_instructions", "")).strip())
                moved = str(copy.get("profile_reorder_moved", "")).strip()
                self.assertTrue(moved)
                self.assertIn("{position}", moved)
                self.assertIn("{total}", moved)

        focus = css_rule(self.css, "[data-profile-section]:focus-visible")
        dragging = css_rule(self.css, ".profile-reorder-dragging")
        self.assertRegex(focus, r"outline\s*:")
        self.assertRegex(focus, r"outline-offset\s*:")
        self.assertRegex(dragging, r"transform\s*:")
        self.assertRegex(dragging, r"(?:box-shadow|filter)\s*:")
        self.assertRegex(dragging, r"touch-action\s*:\s*none")
        self.assertRegex(self.css, r"\[data-profile-section\]\s*\{[^}]*transition\s*:")

        reduced = re.search(
            r"@media\s*\(prefers-reduced-motion:\s*reduce\)\s*\{(.*)\}\s*$",
            self.css,
            re.DOTALL,
        )
        self.assertIsNotNone(reduced)
        self.assertRegex(reduced.group(1), r"transition-duration\s*:\s*\.001ms\s*!important")

    def test_regression_profile_long_press_cannot_be_taken_over_by_native_selection(self):
        reorderable = css_rule(self.css, "[data-profile-section]")
        images = css_rule(self.css, "[data-profile-section] img")

        self.assertRegex(reorderable, r"-webkit-user-select\s*:\s*none")
        self.assertRegex(reorderable, r"(?<!-)user-select\s*:\s*none")
        self.assertRegex(images, r"-webkit-user-drag\s*:\s*none")

    def test_regression_pointer_capture_survives_moving_the_dragged_block(self):
        begin = javascript_function(self.js, "startProfileReorder")
        finish = javascript_function(self.js, "finishProfileReorder")
        cancel = javascript_function(self.js, "cancelProfileReorder")

        self.assertIn("profileLayout.setPointerCapture(state.pointerId)", begin)
        self.assertNotIn("state.item.setPointerCapture", begin)
        for cleanup in (finish, cancel):
            self.assertIn("profileLayout.hasPointerCapture(state.pointerId)", cleanup)
            self.assertIn("profileLayout.releasePointerCapture(state.pointerId)", cleanup)
            self.assertNotIn("state.item.hasPointerCapture", cleanup)
            self.assertNotIn("state.item.releasePointerCapture", cleanup)
        self.assertIn(
            'profileLayout.addEventListener("lostpointercapture", cancelProfileReorder)',
            self.js,
        )


if __name__ == "__main__":
    unittest.main()
