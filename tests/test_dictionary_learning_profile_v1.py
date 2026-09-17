from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
HTML = (ROOT / "mydictionary/templates/dictionary.html").read_text(encoding="utf-8")
CSS = (ROOT / "mydictionary/static/dictionary.css").read_text(encoding="utf-8")
JS = (ROOT / "mydictionary/static/dictionary.js").read_text(encoding="utf-8")
SW = (ROOT / "mydictionary/static/dictionary-sw.js").read_text(encoding="utf-8")
ADMIN = (ROOT / "mydictionary/admin.py").read_text(encoding="utf-8")


class DictionaryLearningProfileV1ContractTest(unittest.TestCase):
    def test_ac1_profile_precedes_dictionary_controls_and_names_local_scope(self):
        profile = HTML.index('id="learning-profile"')
        self.assertLess(profile, HTML.index('id="target-language"'))
        self.assertLess(profile, HTML.index('id="dictionary-results"'))
        for identifier in (
            "profile-saved", "profile-learned", "profile-due", "profile-days",
            "profile-progress", "profile-activity", "profile-streak",
        ):
            self.assertIn(f'id="{identifier}"', HTML)
        self.assertIn('data-copy="profile_scope"', HTML)

    def test_ac3_results_are_progressively_revealed(self):
        self.assertIn("const pageSize = 8", JS)
        self.assertIn('id="show-more-results"', HTML)
        self.assertIn('data-copy="show_more"', HTML)
        self.assertIn("visibleLimit = pageSize", JS)

    def test_ac4_pdf_and_offline_tools_are_secondary(self):
        self.assertIn('id="print-profile"', HTML)
        self.assertIn("window.print()", JS)
        self.assertRegex(HTML, r'<details\s+class="offline-tools"[^>]*>')
        self.assertNotRegex(HTML, r'<details\s+class="offline-tools"[^>]*\sopen(?:\s|=|>)')
        for identifier in ("save-offline", "download-dictionary", "export-saved"):
            self.assertEqual(HTML.count(f'id="{identifier}"'), 1)
        self.assertIn("@media print", CSS)

    def test_ac5_profile_runtime_is_shared_online_offline_and_cached(self):
        profile_script = 'src="/static/dictionary-profile.js"'
        dictionary_script = 'src="/static/dictionary.js"'
        self.assertLess(HTML.index(profile_script), HTML.index(dictionary_script))
        self.assertIn('dictionary_profile_js|safe', HTML)
        self.assertIn('"dictionary-profile.js"', ADMIN)
        self.assertIn('"/static/dictionary-profile.js"', SW)


if __name__ == "__main__":
    unittest.main()
