import os
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch


os.environ.setdefault("BOT_TOKEN", "123456:TESTTOKEN")
os.environ.setdefault("ALLOWED_USER_ID", "1")
os.environ.setdefault("ALLOW_SQLITE_DEV", "true")

import bot


ROOT_CALLBACKS = {
    "settings:section:language",
    "settings:section:pace",
    "settings:section:tutor",
}


def callback_data(reply_markup):
    return {
        button.callback_data
        for row in reply_markup.inline_keyboard
        for button in row
        if button.callback_data
    }


class FakeSettingsStore:
    def __init__(self):
        self.product = {"daily_word_goal": 10}
        self.preferences = {
            "mode": "teacher",
            "depth": "balanced",
            "level": "adaptive",
        }

    def product_profile(self, _user_id):
        return dict(self.product)

    def update_product_profile(self, _user_id, **changes):
        self.product.update(changes)
        return dict(self.product)

    def get_mirror_preferences(self, _user_id):
        return dict(self.preferences)

    def set_mirror_preferences(self, _user_id, **preferences):
        self.preferences = dict(preferences)
        return dict(self.preferences)

    def record_event(self, *_args, **_kwargs):
        return None


class TelegramSettingsNavigationE2ETest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.store = FakeSettingsStore()
        self.runtime = SimpleNamespace(
            user_id=101,
            store=self.store,
            interface_locale="ru",
            meaning_language="ru",
            role="learner",
            progress=dict(bot.PROGRESS_DEFAULTS),
        )
        self.context = SimpleNamespace(
            user_data={"interface_locale": "ru"},
            bot=SimpleNamespace(send_message=AsyncMock()),
        )
        self.policy = {
            "enabled_modes": ["teacher", "coach", "brief"],
        }
        self.runtime_token = bot._ACTIVE_RUNTIME.set(self.runtime)

    def tearDown(self):
        bot._ACTIVE_RUNTIME.reset(self.runtime_token)

    def update_for(self, data):
        query = SimpleNamespace(
            data=data,
            answer=AsyncMock(),
            edit_message_text=AsyncMock(),
            message=SimpleNamespace(chat_id=101),
        )
        update = SimpleNamespace(
            callback_query=query,
            effective_user=SimpleNamespace(id=101, language_code="ru"),
        )
        return update, query

    def admin_store_patch(self):
        return patch.object(
            bot,
            "AdminStore",
            return_value=SimpleNamespace(
                get_mirror_control_plane=lambda: dict(self.policy)
            ),
        )

    async def invoke_settings(self, data):
        update, query = self.update_for(data)
        with self.admin_store_patch():
            await bot.settings_cb.__wrapped__(update, self.context)
        return query

    async def test_settings_entry_is_a_compact_three_section_hub(self):
        update, query = self.update_for("start:settings")

        with self.admin_store_patch():
            await bot.start_menu_cb.__wrapped__(update, self.context)

        query.answer.assert_awaited_once_with()
        payload = self.context.bot.send_message.await_args.kwargs
        self.assertEqual(callback_data(payload["reply_markup"]), ROOT_CALLBACKS)

    async def test_every_root_section_opens_only_its_options_and_back_returns_root(self):
        expected_section_callbacks = {
            "language": {
                *(
                    f"settings:language:{pack.pack_id}"
                    for pack in bot.switchable_packs()
                ),
                "settings:back:root",
            },
            "pace": {
                "settings:pace:5",
                "settings:pace:10",
                "settings:pace:20",
                "settings:back:root",
            },
            "tutor": {
                "settings:section:tutor-style",
                "settings:section:tutor-depth",
                "settings:section:tutor-level",
                "settings:back:root",
            },
        }

        for section, expected in expected_section_callbacks.items():
            with self.subTest(section=section):
                query = await self.invoke_settings(f"settings:section:{section}")
                query.edit_message_text.assert_awaited_once()
                payload = query.edit_message_text.await_args.kwargs
                self.assertEqual(callback_data(payload["reply_markup"]), expected)

                back_query = await self.invoke_settings("settings:back:root")
                back_query.edit_message_text.assert_awaited_once()
                back_payload = back_query.edit_message_text.await_args.kwargs
                self.assertEqual(
                    callback_data(back_payload["reply_markup"]), ROOT_CALLBACKS
                )

    async def test_tutor_hub_subsections_and_back_buttons_are_complete(self):
        tutor_query = await self.invoke_settings("settings:section:tutor")
        tutor_query.edit_message_text.assert_awaited_once()
        self.assertEqual(
            callback_data(
                tutor_query.edit_message_text.await_args.kwargs["reply_markup"]
            ),
            {
                "settings:section:tutor-style",
                "settings:section:tutor-depth",
                "settings:section:tutor-level",
                "settings:back:root",
            },
        )

        expected = {
            "tutor-style": {
                "settings:mirror:teacher",
                "settings:mirror:coach",
                "settings:mirror:brief",
                "settings:back:tutor",
            },
            "tutor-depth": {
                "settings:mirror-depth:compact",
                "settings:mirror-depth:balanced",
                "settings:mirror-depth:deep",
                "settings:back:tutor",
            },
            "tutor-level": {
                "settings:mirror-level:adaptive",
                "settings:mirror-level:a1",
                "settings:mirror-level:a2",
                "settings:mirror-level:b1",
                "settings:mirror-level:b2",
                "settings:mirror-level:c1",
                "settings:back:tutor",
            },
        }
        for subsection, callbacks in expected.items():
            with self.subTest(subsection=subsection):
                query = await self.invoke_settings(f"settings:section:{subsection}")
                query.edit_message_text.assert_awaited_once()
                self.assertEqual(
                    callback_data(
                        query.edit_message_text.await_args.kwargs["reply_markup"]
                    ),
                    callbacks,
                )

                back_query = await self.invoke_settings("settings:back:tutor")
                back_query.edit_message_text.assert_awaited_once()
                self.assertEqual(
                    callback_data(
                        back_query.edit_message_text.await_args.kwargs["reply_markup"]
                    ),
                    {
                        "settings:section:tutor-style",
                        "settings:section:tutor-depth",
                        "settings:section:tutor-level",
                        "settings:back:root",
                    },
                )

    async def test_saved_choices_remain_in_their_matching_sections(self):
        pace_query = await self.invoke_settings("settings:pace:20")
        self.assertEqual(self.store.product["daily_word_goal"], 20)
        pace_callbacks = callback_data(
            pace_query.edit_message_text.await_args.kwargs["reply_markup"]
        )
        self.assertEqual(
            pace_callbacks,
            {
                "settings:pace:5",
                "settings:pace:10",
                "settings:pace:20",
                "settings:back:root",
            },
        )

        tutor_query = await self.invoke_settings("settings:mirror:coach")
        self.assertEqual(self.store.preferences["mode"], "coach")
        tutor_callbacks = callback_data(
            tutor_query.edit_message_text.await_args.kwargs["reply_markup"]
        )
        self.assertIn("settings:mirror:coach", tutor_callbacks)
        self.assertEqual(
            tutor_callbacks,
            {
                "settings:mirror:teacher",
                "settings:mirror:coach",
                "settings:mirror:brief",
                "settings:back:tutor",
            },
        )

        depth_query = await self.invoke_settings("settings:mirror-depth:deep")
        self.assertEqual(self.store.preferences["depth"], "deep")
        self.assertEqual(
            callback_data(
                depth_query.edit_message_text.await_args.kwargs["reply_markup"]
            ),
            {
                "settings:mirror-depth:compact",
                "settings:mirror-depth:balanced",
                "settings:mirror-depth:deep",
                "settings:back:tutor",
            },
        )

        level_query = await self.invoke_settings("settings:mirror-level:b1")
        self.assertEqual(self.store.preferences["level"], "b1")
        self.assertEqual(
            callback_data(
                level_query.edit_message_text.await_args.kwargs["reply_markup"]
            ),
            {
                "settings:mirror-level:adaptive",
                "settings:mirror-level:a1",
                "settings:mirror-level:a2",
                "settings:mirror-level:b1",
                "settings:mirror-level:b2",
                "settings:mirror-level:c1",
                "settings:back:tutor",
            },
        )

    async def test_language_choice_is_handled_in_settings_and_stays_in_section(self):
        pack = bot.switchable_packs()[0]
        update, query = self.update_for(f"settings:language:{pack.pack_id}")
        with (
            patch.object(bot, "switchable_packs", return_value=[pack]),
            patch.object(bot, "activate_content_pack") as activate,
            patch.object(bot, "record_product_event"),
            self.admin_store_patch(),
        ):
            await bot.settings_cb.__wrapped__(update, self.context)

        activate.assert_called_once_with(pack, source="catalog")
        query.edit_message_text.assert_awaited_once()
        payload = query.edit_message_text.await_args.kwargs
        self.assertEqual(
            callback_data(payload["reply_markup"]),
            {f"settings:language:{pack.pack_id}", "settings:back:root"},
        )


if __name__ == "__main__":
    unittest.main()
