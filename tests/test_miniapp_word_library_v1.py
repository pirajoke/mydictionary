from pathlib import Path
import unittest

from mydictionary.miniapp import MINIAPP_COPY


ROOT = Path(__file__).resolve().parents[1]
HTML = (ROOT / "mydictionary/templates/miniapp.html").read_text(encoding="utf-8")
CSS = (ROOT / "mydictionary/static/miniapp.css").read_text(encoding="utf-8")
JS = (ROOT / "mydictionary/static/miniapp.js").read_text(encoding="utf-8")


class MiniAppWordLibraryV1ContractTest(unittest.TestCase):
    def test_two_word_sources_share_one_accessible_library_surface(self):
        self.assertIn('class="word-library"', HTML)
        self.assertIn('role="tablist"', HTML)
        self.assertIn('id="word-library-custom-tab"', HTML)
        self.assertIn('aria-controls="word-library-custom-panel"', HTML)
        self.assertIn('id="word-library-tracked-tab"', HTML)
        self.assertIn('aria-controls="word-library-tracked-panel"', HTML)
        self.assertIn('id="word-library-custom-panel"', HTML)
        self.assertIn('id="word-library-tracked-panel"', HTML)
        self.assertIn('role="tabpanel"', HTML)

    def test_each_list_uses_fixed_pagination_instead_of_unbounded_rendering(self):
        self.assertIn("const WORD_LIBRARY_PAGE_SIZE = 6;", JS)
        self.assertIn("items.slice(start, start + WORD_LIBRARY_PAGE_SIZE)", JS)
        self.assertIn('id="custom-word-page-previous"', HTML)
        self.assertIn('id="custom-word-page-next"', HTML)
        self.assertIn('id="tracked-word-page-previous"', HTML)
        self.assertIn('id="tracked-word-page-next"', HTML)
        self.assertIn(".word-library-pager", CSS)
        self.assertIn("min-height: 44px", CSS)

    def test_library_navigation_copy_exists_for_every_interface_locale(self):
        keys = {
            "word_library_title",
            "word_library_previous",
            "word_library_next",
            "word_library_page",
        }
        for locale, copy in MINIAPP_COPY.items():
            with self.subTest(locale=locale):
                self.assertTrue(keys.issubset(copy))
                self.assertTrue(all(str(copy[key]).strip() for key in keys))


if __name__ == "__main__":
    unittest.main()
