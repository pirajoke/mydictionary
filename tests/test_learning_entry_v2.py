"""Public Telegram entry routing for the locked learning-flow v2 contract."""
from contextlib import ExitStack
from dataclasses import replace
import os
from pathlib import Path
import re
import shutil
import subprocess
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch
from urllib.parse import parse_qs, urlsplit

os.environ.setdefault("BOT_TOKEN", "123456:TESTTOKEN_ABCDEFGHIJKLMNOP")
os.environ.setdefault("ALLOWED_USER_ID", "1")
os.environ.setdefault("ALLOW_SQLITE_DEV", "true")

import bot


class LearningEntryV2Test(unittest.IsolatedAsyncioTestCase):
    def fixture(self, action, locale="en"):
        message = SimpleNamespace(text=bot.quick_action_label(action, locale), chat_id=123, reply_text=AsyncMock())
        return (
            SimpleNamespace(message=message, effective_message=message,
                            effective_user=SimpleNamespace(id=1, language_code=locale)),
            SimpleNamespace(user_data={"interface_locale": locale}),
        )

    def routes(self, stack):
        return {
            "continue": stack.enter_context(patch.object(bot, "continue_or_start_lesson", new_callable=AsyncMock)),
            "review": stack.enter_context(patch.object(bot, "start_home_lesson", new_callable=AsyncMock)),
            "mode": stack.enter_context(patch.object(bot, "open_practice_mode_picker", new_callable=AsyncMock)),
            "words": stack.enter_context(patch.object(bot.cmd_learn, "__wrapped__", new_callable=AsyncMock)),
            "lang": stack.enter_context(patch.object(bot.cmd_lang, "__wrapped__", new_callable=AsyncMock)),
        }

    async def test_ac2_enabled_quick_actions_open_native_destinations_in_all_locales(self):
        destinations = {"continue": "practice", "review": "review", "mode": "words", "words": "words", "lang": "languages"}
        for locale in ("en", "ru", "fr", "de", "es", "ja", "zh", "ar"):
            for action, destination in destinations.items():
                with self.subTest(locale=locale, action=action), ExitStack() as stack:
                    routes = self.routes(stack)
                    event = stack.enter_context(patch.object(bot, "record_product_event"))
                    stack.enter_context(patch.object(bot, "MINIAPP_SETTINGS", replace(bot.MINIAPP_SETTINGS, enabled=True, public_url="https://dictionary.example/miniapp")))
                    update, context = self.fixture(action, locale)
                    await bot.handle_quick_action.__wrapped__(update, context)
                    update.message.reply_text.assert_awaited_once()
                    self.assertTrue(update.message.reply_text.await_args.args[0].strip())
                    markup = update.message.reply_text.await_args.kwargs.get("reply_markup")
                    self.assertIsNotNone(markup)
                    buttons = [button for row in markup.inline_keyboard for button in row if button.web_app]
                    self.assertEqual(len(buttons), 1)
                    parsed = urlsplit(buttons[0].web_app.url)
                    self.assertEqual((parsed.scheme, parsed.netloc, parsed.path), ("https", "dictionary.example", "/miniapp"))
                    self.assertEqual(parse_qs(parsed.query), {"view": [destination]})
                    self.assertFalse(parsed.fragment)
                    for route in routes.values():
                        route.assert_not_awaited()
                    event.assert_called_once_with("quick_action_selected", source=action)

    async def test_ec2_disabled_miniapp_preserves_every_deterministic_bot_route(self):
        for action in ("continue", "review", "mode", "words", "lang"):
            with self.subTest(action=action), ExitStack() as stack:
                routes = self.routes(stack)
                stack.enter_context(patch.object(bot, "record_product_event"))
                stack.enter_context(patch.object(bot, "MINIAPP_SETTINGS", replace(bot.MINIAPP_SETTINGS, enabled=False)))
                update, context = self.fixture(action)
                await bot.handle_quick_action.__wrapped__(update, context)
                routes[action].assert_awaited_once()
                if action == "review":
                    self.assertEqual(routes[action].await_args.kwargs["lesson_kind"], "review")
                update.message.reply_text.assert_not_awaited()


class LearningControllerV2Test(unittest.TestCase):
    def test_ac2_words_action_and_deep_link_open_chooser_without_entering_a_deck(self):
        root = Path(__file__).resolve().parents[1]
        script = (root / "mydictionary/static/miniapp.js").read_text(encoding="utf-8")
        node_runtime = shutil.which("node") or "/Users/mark/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node"
        action_function = "function openAction(action)" + script.split("function openAction(action)", 1)[1].split("\n  function ", 1)[0]
        requested_block_start = "    if (window.LexiSwipe) {\n      window.LexiSwipe.configure(data);"
        requested_block = requested_block_start + script.split(requested_block_start, 1)[1].split("\n    openRequestedDetailView();", 1)[0]
        # Run the actual route bodies with controller spies. An existing card
        # must yield to the chooser, without silently entering another deck.
        harness = '''
const assert = require("node:assert/strict");
const calls = [];
const payload = {}, data = {}, requestedView = "words";
let requestedPracticeOpened = false;
const node = id => id;
const activateTab = id => calls.push(["tab", id]);
const window = {LexiSwipe: {
  choose: () => calls.push(["choose"]),
  enter: mode => calls.push(["enter", mode]),
  configure() {}, refresh() {}
}};
'''
        for route, code in (("words action", action_function + '\nopenAction("words");'), ("words deep link", requested_block)):
            with self.subTest(route=route):
                run = subprocess.run([node_runtime, "-e", harness + code + '\nassert.deepEqual(calls, [["tab", "tab-words"], ["choose"]]);'],
                                     cwd=root, capture_output=True, text=True, timeout=10)
                self.assertEqual(run.returncode, 0, run.stdout + run.stderr)

    def test_ac7_language_shortcut_is_hidden_until_bootstrap_and_on_auth_error(self):
        root = Path(__file__).resolve().parents[1]
        html = (root / "mydictionary/templates/miniapp.html").read_text(encoding="utf-8")
        script = (root / "mydictionary/static/miniapp.js").read_text(encoding="utf-8")
        button = re.search(r'<button\b[^>]*\bid="change-learning-language"[^>]*>', html)
        self.assertIsNotNone(button, "Authenticated learners retain a language shortcut")
        with self.subTest(state="initial shell"):
            self.assertRegex(button.group(), r"\shidden(?:\s|=|>)", "No blank actionable language shortcut before authentication")
        render = script.split("function render(data)", 1)[1].split("\n  function ", 1)[0]
        show_error = script.split("function showError(error)", 1)[1].split("\n  async function ", 1)[0]
        for state, body, hidden in (("authenticated render", render, "false"), ("error recovery", show_error, "true")):
            with self.subTest(state=state):
                self.assertRegex(body, rf'node\(["\']change-learning-language["\']\)\.hidden\s*=\s*{hidden}\b')
        self.assertIn("?start=miniapp_help", show_error)

    def test_ac1_ac3_ac5_ec1_err2_public_learning_controller(self):
        root = Path(__file__).resolve().parents[1]
        node = shutil.which("node") or "/Users/mark/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node"
        if not Path(node).is_file():
            self.skipTest("Node runtime is unavailable for the public controller contract")
        run = subprocess.run(
            [node, "--test", str(root / "tests/browser/learning-flow-v2.cjs")],
            cwd=root, capture_output=True, text=True, timeout=30,
        )
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)


if __name__ == "__main__":
    unittest.main()
