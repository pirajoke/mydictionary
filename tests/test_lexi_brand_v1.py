from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "mydictionary/templates/miniapp.html"
CSS = ROOT / "mydictionary/static/miniapp.css"
ASSET_DIR = ROOT / "mydictionary/static/mascot"


class LexiBrandContractTest(unittest.TestCase):
    def test_miniapp_uses_selected_lexi_hero_without_replacing_learner_avatar(self) -> None:
        html = TEMPLATE.read_text(encoding="utf-8")
        css = CSS.read_text(encoding="utf-8")

        self.assertIn('class="lexi-hero dashboard-section"', html)
        self.assertIn("mascot/lexi-miniapp-hero-v1.jpg", html)
        self.assertIn('id="profile-photo"', html)
        self.assertIn('class="avatar-shell"', html)
        self.assertIn(".lexi-hero", css)
        self.assertIn(".lexi-hero img", css)

    def test_selected_delivery_assets_are_bounded_and_nonempty(self) -> None:
        expected = {
            "lexi-telegram-avatar-v1.jpg": 300_000,
            "lexi-miniapp-hero-v1.jpg": 350_000,
        }
        for filename, maximum_bytes in expected.items():
            with self.subTest(filename=filename):
                asset = ASSET_DIR / filename
                self.assertTrue(asset.is_file())
                self.assertGreater(asset.stat().st_size, 10_000)
                self.assertLessEqual(asset.stat().st_size, maximum_bytes)
                self.assertEqual(asset.read_bytes()[:3], b"\xff\xd8\xff")


if __name__ == "__main__":
    unittest.main()
