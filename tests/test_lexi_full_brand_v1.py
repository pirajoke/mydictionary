from pathlib import Path
import unittest

from mydictionary.bot_profile import BOT_PROFILE_DEFAULTS, render_start_text
from mydictionary.localization import INTERFACE_LOCALES, translate
from mydictionary.miniapp import MINIAPP_COPY


ROOT = Path(__file__).resolve().parents[1]
PUBLIC_TEMPLATES = (
    ROOT / "mydictionary/templates/miniapp.html",
    ROOT / "mydictionary/templates/admin/login.html",
    ROOT / "mydictionary/templates/admin/index.html",
    ROOT / "mydictionary/templates/admin/forgot_password.html",
    ROOT / "mydictionary/templates/admin/reset_password.html",
    ROOT / "mydictionary/templates/admin/ai_key.html",
    ROOT / "mydictionary/templates/admin/stars_launch.html",
)


class LexiFullBrandContractTest(unittest.TestCase):
    def test_telegram_profile_and_localized_entry_copy_use_lexi(self) -> None:
        self.assertEqual(BOT_PROFILE_DEFAULTS["bot_name"], "Lexi")
        for key, value in BOT_PROFILE_DEFAULTS.items():
            with self.subTest(key=key):
                self.assertNotIn("MY DICTIONARY", value)

        for locale in sorted(INTERFACE_LOCALES):
            with self.subTest(locale=locale):
                start = render_start_text(BOT_PROFILE_DEFAULTS, "Alex", locale=locale)
                self.assertIn("Lexi", start)
                self.assertNotIn("MY DICTIONARY", start)
                self.assertIn("Lexi", translate("bot_help", locale))
                self.assertIn("Lexi", translate("miniapp_open", locale))

    def test_miniapp_copy_uses_lexi_in_all_supported_locales(self) -> None:
        self.assertEqual(set(MINIAPP_COPY), set(INTERFACE_LOCALES))
        for locale, copy in MINIAPP_COPY.items():
            visible_copy = "\n".join(str(value) for value in copy.values())
            with self.subTest(locale=locale):
                self.assertNotIn("MY DICTIONARY", visible_copy)
                self.assertIn("Lexi", copy["settings_help"])
                self.assertIn("Lexi", copy["referral_share_text"])

    def test_public_templates_show_lexi_and_use_the_selected_mascot(self) -> None:
        for template in PUBLIC_TEMPLATES:
            text = template.read_text(encoding="utf-8")
            with self.subTest(template=template.name):
                self.assertNotIn("MY DICTIONARY", text)
                self.assertIn("Lexi", text)

        miniapp = PUBLIC_TEMPLATES[0].read_text(encoding="utf-8")
        self.assertIn("mascot/lexi-telegram-avatar-v1.jpg", miniapp)
        self.assertIn("miniapp/lexi-section-words-v1.webp", miniapp)
        self.assertIn("miniapp/lexi-section-credits-v1.webp", miniapp)
        self.assertIn("miniapp/lexi-section-languages-v1.webp", miniapp)
        self.assertIn("miniapp/lexi-section-profile-v1.webp", miniapp)
        self.assertIn("miniapp/lexi-section-settings-v1.webp", miniapp)
        self.assertNotIn("admin/brand-mark.png", miniapp)
        self.assertNotIn("miniapp-section-", miniapp)

        for template in PUBLIC_TEMPLATES[1:]:
            self.assertNotIn(
                "admin/brand-mark.png", template.read_text(encoding="utf-8")
            )

    def test_runtime_welcome_and_reset_mail_use_lexi(self) -> None:
        bot_source = (ROOT / "bot.py").read_text(encoding="utf-8")
        admin_auth = (ROOT / "mydictionary/admin_auth.py").read_text(
            encoding="utf-8"
        )
        admin_source = (ROOT / "mydictionary/admin.py").read_text(
            encoding="utf-8"
        )
        self.assertIn('"lexi-telegram-avatar-v1.jpg"', bot_source)
        self.assertNotIn("mydictionary-welcome.jpg", bot_source)
        self.assertIn("Lexi", admin_auth)
        self.assertNotIn("MY DICTIONARY", admin_auth)
        self.assertIn("mydictionary/static/mascot/lexi-telegram-avatar-v1.jpg", admin_source)

    def test_active_runtime_and_operator_surfaces_have_no_old_public_name(self) -> None:
        runtime_sources = [ROOT / "bot.py"]
        runtime_sources.extend((ROOT / "mydictionary").glob("*.py"))
        runtime_sources.extend((ROOT / "ops").glob("*.py"))

        for source in runtime_sources:
            with self.subTest(source=source.relative_to(ROOT)):
                text = source.read_text(encoding="utf-8")
                self.assertNotIn("MY DICTIONARY", text)
                self.assertNotIn("MY DICTIONNARY", text)

    def test_selected_lexi_brand_assets_are_bounded_and_nonempty(self) -> None:
        expected = {
            ROOT / "mydictionary/static/mascot/lexi-telegram-avatar-v1.jpg": (
                b"\xff\xd8\xff",
                300_000,
            ),
            ROOT / "mydictionary/static/miniapp/lexi-section-profile-v1.webp": (
                b"RIFF",
                150_000,
            ),
            ROOT / "mydictionary/static/miniapp/lexi-section-words-v1.webp": (
                b"RIFF",
                350_000,
            ),
            ROOT / "mydictionary/static/miniapp/lexi-section-credits-v1.webp": (
                b"RIFF",
                350_000,
            ),
            ROOT / "mydictionary/static/miniapp/lexi-section-languages-v1.webp": (
                b"RIFF",
                300_000,
            ),
            ROOT / "mydictionary/static/miniapp/lexi-section-settings-v1.webp": (
                b"RIFF",
                150_000,
            ),
        }
        for asset, (magic, maximum_bytes) in expected.items():
            with self.subTest(asset=asset.name):
                self.assertTrue(asset.is_file())
                self.assertGreater(asset.stat().st_size, 10_000)
                self.assertLessEqual(asset.stat().st_size, maximum_bytes)
                self.assertEqual(asset.read_bytes()[: len(magic)], magic)

    def test_public_legal_title_keeps_continuity_without_old_primary_brand(self) -> None:
        terms = (ROOT / "docs/legal/telegram-stars-terms-ru-v1.md").read_text(
            encoding="utf-8"
        )
        self.assertTrue(terms.startswith("# Условия покупки AI-кредитов Lexi"))
        self.assertNotIn("AI-репетитора MY DICTIONARY", terms)

    def test_active_ai_personas_use_lexi_and_preserve_previous_contracts(self) -> None:
        ai_source = (ROOT / "mydictionary/ai_tutor.py").read_text(encoding="utf-8")
        tutor = ROOT / "prompts/ai-tutor-v2.txt"
        mirror = ROOT / "prompts/mirror-v8.txt"

        self.assertTrue(tutor.is_file())
        self.assertTrue(mirror.is_file())
        self.assertIn('load_prompt_contract(_PROMPT_ROOT / "ai-tutor-v2.txt")', ai_source)
        self.assertIn('load_prompt_contract(_PROMPT_ROOT / "mirror-v8.txt")', ai_source)
        for contract in (tutor, mirror):
            text = contract.read_text(encoding="utf-8")
            with self.subTest(contract=contract.name):
                self.assertIn("Lexi", text)
                self.assertNotIn("MY DICTIONARY", text)

        self.assertTrue((ROOT / "prompts/ai-tutor-v1.txt").is_file())
        self.assertTrue((ROOT / "prompts/mirror-v7.txt").is_file())


if __name__ == "__main__":
    unittest.main()
