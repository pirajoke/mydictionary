import os
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock, patch


os.environ.setdefault("BOT_TOKEN", "123456:TESTTOKEN")
os.environ.setdefault("ALLOWED_USER_ID", "1")
os.environ.setdefault("ALLOW_SQLITE_DEV", "true")

import bot
from mydictionary.localization import INTERFACE_LOCALES, catalog_is_complete


PRODUCT = {
    "daily_word_goal": 10,
    "mirror_mode": "teacher",
    "mirror_depth": "balanced",
    "mirror_level": "adaptive",
}
POLICY = {
    "enabled_modes": [
        "teacher",
        "conversation",
        "coach",
        "brief",
        "practice",
        "exam",
    ]
}
MINIAPP_URL = "https://example.test/miniapp"


def callbacks(markup):
    return [
        button.callback_data
        for row in markup.inline_keyboard
        for button in row
        if button.callback_data
    ]


class TelegramSettingsHubContractTest(unittest.TestCase):
    def setUp(self):
        self.pack = bot.CATALOG.require("ja-basics-100")

    def test_ac1_ac2_home_is_commands_sections_and_private_miniapp_only(self):
        text = bot.settings_text(
            self.pack,
            PRODUCT,
            locale="ru",
            section="home",
        )
        markup = bot.settings_keyboard(
            PRODUCT,
            mirror_policy=POLICY,
            locale="ru",
            section="home",
            miniapp_url=MINIAPP_URL,
        )

        for command in ("/learn", "/ai", "/stats", "/lang", "/app", "/privacy"):
            self.assertIn(command, text)
        home_callbacks = callbacks(markup)
        self.assertEqual(
            home_callbacks,
            ["settings:section:study", "settings:section:ai"],
        )
        self.assertFalse(any(value.startswith("lang:") for value in home_callbacks))
        self.assertFalse(any(value.startswith("settings:pace:") for value in home_callbacks))
        self.assertFalse(any(value.startswith("settings:mirror") for value in home_callbacks))
        web_button = markup.inline_keyboard[0][0]
        self.assertEqual(web_button.web_app.url, MINIAPP_URL)
        self.assertIsNone(web_button.callback_data)

        group_markup = bot.settings_keyboard(
            PRODUCT,
            mirror_policy=POLICY,
            locale="ru",
            section="home",
            miniapp_url=None,
        )
        self.assertTrue(
            all(
                button.web_app is None
                for row in group_markup.inline_keyboard
                for button in row
            )
        )

    def test_ac3_study_section_groups_only_language_pace_and_back(self):
        markup = bot.settings_keyboard(
            PRODUCT,
            mirror_policy=POLICY,
            locale="fr",
            section="study",
        )
        values = callbacks(markup)
        language_values = [value for value in values if value.startswith("lang:")]
        self.assertEqual(
            set(language_values),
            {f"lang:{pack.pack_id}" for pack in bot.switchable_packs()},
        )
        self.assertEqual(
            {value for value in values if value.startswith("settings:pace:")},
            {"settings:pace:5", "settings:pace:10", "settings:pace:20"},
        )
        self.assertIn("settings:section:home", values)
        self.assertFalse(any(value.startswith("settings:mirror") for value in values))
        for row in markup.inline_keyboard:
            row_languages = [
                button for button in row if (button.callback_data or "").startswith("lang:")
            ]
            self.assertLessEqual(len(row_languages), 2)
        self.assertLessEqual(len(markup.inline_keyboard), 7)

    def test_ac4_ai_section_groups_only_style_depth_level_and_back(self):
        markup = bot.settings_keyboard(
            PRODUCT,
            mirror_policy=POLICY,
            locale="de",
            section="ai",
        )
        values = callbacks(markup)
        self.assertFalse(any(value.startswith("lang:") for value in values))
        self.assertFalse(any(value.startswith("settings:pace:") for value in values))
        self.assertEqual(
            {value for value in values if value.startswith("settings:mirror:")},
            {f"settings:mirror:{value}" for value in POLICY["enabled_modes"]},
        )
        self.assertEqual(
            {value for value in values if value.startswith("settings:mirror-depth:")},
            {
                "settings:mirror-depth:compact",
                "settings:mirror-depth:balanced",
                "settings:mirror-depth:deep",
            },
        )
        self.assertEqual(
            {value for value in values if value.startswith("settings:mirror-level:")},
            {f"settings:mirror-level:{value}" for value in bot.MIRROR_LEARNER_LEVELS},
        )
        self.assertIn("settings:section:home", values)
        self.assertTrue(all(len(value.encode("utf-8")) <= 64 for value in values))
        self.assertLessEqual(len(markup.inline_keyboard), 8)

    def test_ac6_copy_is_complete_and_every_section_is_localized(self):
        self.assertTrue(catalog_is_complete())
        russian = {
            section: bot.settings_text(self.pack, PRODUCT, locale="ru", section=section)
            for section in ("home", "study", "ai")
        }
        for locale in INTERFACE_LOCALES:
            for section in ("home", "study", "ai"):
                with self.subTest(locale=locale, section=section):
                    rendered = bot.settings_text(
                        self.pack,
                        PRODUCT,
                        locale=locale,
                        section=section,
                    )
                    self.assertTrue(rendered.strip())
                    if locale != "ru":
                        self.assertNotEqual(rendered, russian[section])


class TelegramSettingsHubHandlerTest(unittest.IsolatedAsyncioTestCase):
    def runtime(self):
        store = SimpleNamespace(
            get_mirror_preferences=Mock(
                return_value={"mode": "teacher", "depth": "balanced", "level": "adaptive"}
            ),
            get_mirror_style=Mock(return_value="teacher"),
            product_profile=Mock(return_value=dict(PRODUCT)),
            update_product_profile=Mock(return_value={**PRODUCT, "daily_word_goal": 20}),
            set_mirror_preferences=Mock(
                return_value={"mode": "coach", "depth": "balanced", "level": "adaptive"}
            ),
        )
        runtime = bot.LearnerRuntime(
            user_id=77,
            store=store,
            progress=dict(bot.PROGRESS_DEFAULTS),
            meaning_language="ru",
        )
        return runtime, store

    async def invoke(self, data):
        query = SimpleNamespace(
            data=data,
            answer=AsyncMock(),
            edit_message_text=AsyncMock(),
            message=SimpleNamespace(chat_id=77),
        )
        update = SimpleNamespace(
            callback_query=query,
            effective_user=SimpleNamespace(id=77, language_code="en"),
            effective_chat=SimpleNamespace(type="private"),
        )
        context = SimpleNamespace(user_data={}, bot=SimpleNamespace())
        runtime, store = self.runtime()
        token = bot._ACTIVE_RUNTIME.set(runtime)
        try:
            with (
                patch.object(bot, "active_content_pack", return_value=bot.CATALOG.require("ja-basics-100")),
                patch.object(
                    bot,
                    "AdminStore",
                    return_value=SimpleNamespace(get_mirror_control_plane=lambda: POLICY),
                ),
                patch.object(bot, "record_product_event"),
            ):
                await bot.settings_cb.__wrapped__(update, context)
        finally:
            bot._ACTIVE_RUNTIME.reset(token)
        return query, store

    async def test_ac5_section_navigation_and_saves_stay_in_their_section(self):
        for data, expected_section in (
            ("settings:section:study", "study"),
            ("settings:section:ai", "ai"),
            ("settings:section:home", "home"),
            ("settings:pace:20", "study"),
            ("settings:mirror:coach", "ai"),
            ("settings:mirror-depth:deep", "ai"),
            ("settings:mirror-level:b1", "ai"),
        ):
            with self.subTest(data=data):
                query, _store = await self.invoke(data)
                markup = query.edit_message_text.await_args.kwargs["reply_markup"]
                values = callbacks(markup)
                if expected_section == "home":
                    self.assertIn("settings:section:study", values)
                    self.assertIn("settings:section:ai", values)
                else:
                    self.assertIn("settings:section:home", values)
                    if expected_section == "study":
                        self.assertTrue(any(value.startswith("settings:pace:") for value in values))
                        self.assertFalse(any(value.startswith("settings:mirror:") for value in values))
                    else:
                        self.assertTrue(any(value.startswith("settings:mirror:") for value in values))
                        self.assertFalse(any(value.startswith("settings:pace:") for value in values))

    async def test_ac2_start_settings_wires_webapp_only_for_private_chat(self):
        for chat_type, expected_url in (("private", MINIAPP_URL), ("group", None)):
            with self.subTest(chat_type=chat_type):
                query = SimpleNamespace(
                    data="start:settings",
                    answer=AsyncMock(),
                    message=SimpleNamespace(chat_id=77),
                )
                update = SimpleNamespace(
                    callback_query=query,
                    effective_user=SimpleNamespace(id=77, language_code="en"),
                    effective_chat=SimpleNamespace(type=chat_type),
                )
                context = SimpleNamespace(
                    user_data={},
                    bot=SimpleNamespace(send_message=AsyncMock()),
                )
                runtime, _store = self.runtime()
                token = bot._ACTIVE_RUNTIME.set(runtime)
                try:
                    with (
                        patch.object(
                            bot,
                            "active_content_pack",
                            return_value=bot.CATALOG.require("ja-basics-100"),
                        ),
                        patch.object(
                            bot,
                            "AdminStore",
                            return_value=SimpleNamespace(
                                get_mirror_control_plane=lambda: POLICY
                            ),
                        ),
                        patch.object(
                            bot,
                            "MINIAPP_SETTINGS",
                            SimpleNamespace(enabled=True, public_url=MINIAPP_URL),
                        ),
                    ):
                        await bot.start_menu_cb.__wrapped__(update, context)
                finally:
                    bot._ACTIVE_RUNTIME.reset(token)
                markup = context.bot.send_message.await_args.kwargs["reply_markup"]
                web_urls = [
                    button.web_app.url
                    for row in markup.inline_keyboard
                    for button in row
                    if button.web_app is not None
                ]
                self.assertEqual(web_urls, [expected_url] if expected_url else [])

    async def test_err1_unknown_section_fails_closed_without_mutation(self):
        query, store = await self.invoke("settings:section:unknown")
        query.answer.assert_awaited_once_with(
            bot.translate("settings_unavailable", "en"),
            show_alert=True,
        )
        query.edit_message_text.assert_not_awaited()
        store.update_product_profile.assert_not_called()
        store.set_mirror_preferences.assert_not_called()


if __name__ == "__main__":
    unittest.main()
