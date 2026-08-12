import os
import unittest


os.environ.setdefault("BOT_TOKEN", "123456:TESTTOKEN")
os.environ.setdefault("ALLOWED_USER_ID", "1")

import bot
from mydictionary.bot_profile import BOT_PROFILE_DEFAULTS, render_start_text
from mydictionary.localization import (
    INTERFACE_LOCALES,
    catalog_is_complete,
    normalize_locale,
    translate,
)
from mydictionary.mirror_assistant import (
    build_mirror_provider_payload,
    render_mirror_capabilities,
    render_mirror_greeting,
)


class LocaleContractTest(unittest.TestCase):
    def test_eight_interface_locales_are_complete(self):
        self.assertEqual(
            INTERFACE_LOCALES,
            frozenset({"en", "fr", "de", "ja", "ar", "zh", "ru", "es"}),
        )
        self.assertTrue(catalog_is_complete())

    def test_telegram_locale_normalization_handles_regional_variants(self):
        self.assertEqual(normalize_locale("fr-FR"), "fr")
        self.assertEqual(normalize_locale("pt-BR"), "en")
        self.assertEqual(normalize_locale("zh-hant"), "zh")
        self.assertEqual(normalize_locale("JA_jp"), "ja")

    def test_start_text_and_primary_keyboard_follow_interface_locale(self):
        french = render_start_text(BOT_PROFILE_DEFAULTS, "Marc", locale="fr")
        self.assertTrue(french.startswith("Bonjour, Marc"))
        self.assertEqual(
            bot.start_keyboard("fr").inline_keyboard[0][0].text,
            "▶️ Leçon du jour",
        )

        japanese = render_start_text(BOT_PROFILE_DEFAULTS, "Aki", locale="ja")
        self.assertTrue(japanese.startswith("Akiさん、こんにちは"))
        self.assertEqual(
            bot.start_keyboard("ja").inline_keyboard[0][0].text,
            "▶️ 今日のレッスン",
        )

    def test_onboarding_copy_is_available_in_every_locale(self):
        russian = translate("onboarding_intro", "ru")
        for locale in INTERFACE_LOCALES:
            with self.subTest(locale=locale):
                if locale != "ru":
                    self.assertNotEqual(translate("onboarding_intro", locale), russian)
                self.assertTrue(translate("onboarding_choose_pack", locale))
                self.assertTrue(translate("onboarding_choose_pace", locale))


class MirrorLocaleContractTest(unittest.TestCase):
    def test_free_mirror_responses_follow_locale(self):
        greeting = render_mirror_greeting(
            locale="es", first_name="Ana", target_language="fr"
        )
        self.assertIn("Hola, Ana", greeting)
        self.assertIn("francés", greeting.lower())
        self.assertIn("puedo", render_mirror_capabilities("", locale="es").lower())
        self.assertTrue(
            render_mirror_greeting(locale="ja", target_language="en").startswith(
                "こんにちは"
            )
        )

    def test_billable_payload_has_immutable_response_language_instruction(self):
        payload = build_mirror_provider_payload(
            question="Explique bonjour",
            admin_guidance="Answer as a careful language teacher.",
            grounded_snapshot={"has_progress": False},
            interface_locale="fr-FR",
        )
        self.assertEqual(payload["interface_locale"], "fr")
        self.assertIn("French", payload["response_language_instruction"])

        with self.assertRaisesRegex(ValueError, "Unsupported interface locale"):
            build_mirror_provider_payload(
                question="Explain bonjour",
                admin_guidance="Answer as a careful language teacher.",
                grounded_snapshot={"has_progress": False},
                interface_locale="pt-BR",
            )

    def test_legacy_direct_calls_keep_russian_default(self):
        self.assertTrue(
            render_start_text(BOT_PROFILE_DEFAULTS, "Макс").startswith(
                "Привет, Макс!"
            )
        )
        self.assertEqual(
            bot.start_keyboard().inline_keyboard[0][0].text,
            "▶️ Урок на сегодня",
        )


if __name__ == "__main__":
    unittest.main()
