from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "mydictionary/templates/miniapp.html"
CSS = ROOT / "mydictionary/static/miniapp.css"
MASCOT_DIR = ROOT / "mydictionary/static/mascot"
SECTION_DIR = ROOT / "mydictionary/static/miniapp"


class LexiBrandContractTest(unittest.TestCase):
    def test_miniapp_uses_compact_lexi_profile_art_without_replacing_learner_avatar(self) -> None:
        html = TEMPLATE.read_text(encoding="utf-8")
        css = CSS.read_text(encoding="utf-8")

        self.assertIn('class="section-art"', html)
        self.assertIn("miniapp/lexi-section-profile-v1.webp", html)
        self.assertIn('id="profile-photo"', html)
        self.assertIn('class="avatar-shell"', html)
        self.assertNotIn(".lexi-hero", css)
        self.assertIn(".section-art", css)

    def test_selected_delivery_assets_are_bounded_and_nonempty(self) -> None:
        expected = {
            MASCOT_DIR / "lexi-telegram-avatar-v1.jpg": (b"\xff\xd8\xff", 300_000),
            SECTION_DIR / "lexi-section-profile-v1.webp": (b"RIFF", 150_000),
        }
        for asset, (magic, maximum_bytes) in expected.items():
            with self.subTest(filename=asset.name):
                self.assertTrue(asset.is_file())
                self.assertGreater(asset.stat().st_size, 10_000)
                self.assertLessEqual(asset.stat().st_size, maximum_bytes)
                self.assertEqual(asset.read_bytes()[: len(magic)], magic)


if __name__ == "__main__":
    unittest.main()
