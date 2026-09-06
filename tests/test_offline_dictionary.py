import base64
from dataclasses import replace
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from mydictionary.admin import CATALOG, create_app
from mydictionary.storage import DatabaseStore


class DictionaryHTML(HTMLParser):
    def __init__(self, text):
        super().__init__()
        self.blocks = []
        self.tags = []
        self.active = None
        self.feed(text)

    def handle_starttag(self, tag, attrs):
        self.tags.append((tag, dict(attrs)))
        if tag in {"script", "style"}:
            self.active = [tag, dict(attrs), ""]
            self.blocks.append(self.active)

    def handle_data(self, data):
        if self.active is not None:
            self.active[2] += data

    def handle_endtag(self, tag):
        if self.active is not None and tag == self.active[0]:
            self.active = None

    def dictionary_data(self):
        return json.loads(next(body for _, attrs, body in self.blocks
                               if attrs.get("id") == "dictionary-data"))


class OfflineDictionaryTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory(prefix="lexi-dictionary-test-")
        self.store = DatabaseStore(f"sqlite:///{Path(self.temp_dir.name) / 'dictionary.db'}")
        self.app = create_app({
            "TESTING": True,
            "SECRET_KEY": "dictionary-test-secret-with-at-least-32-chars",
            "ADMIN_USERNAME": "owner",
            "ADMIN_PASSWORD": "dictionary-test-password",
            "DATA_DIR": self.temp_dir.name,
            "MINIAPP_ENABLED": "false",
        }, database_store=self.store)
        self.client = self.app.test_client()

    def tearDown(self):
        self.store.close()
        self.temp_dir.cleanup()

    def test_ac1_dictionary_is_public_without_miniapp_or_database_access(self):
        with patch.object(self.store, "Session", side_effect=AssertionError("database query")):
            response = self.client.get("/dictionary/?target=fr&native=en&ui=ru")
        self.assertEqual(response.status_code, 200)
        data = DictionaryHTML(response.get_data(as_text=True)).dictionary_data()
        self.assertEqual(data["version"], 1)
        self.assertEqual(self.client.get("/miniapp").status_code, 404)

    def test_ac2_export_contains_only_seven_aligned_public_starter_packs(self):
        response = self.client.get("/dictionary/")
        self.assertEqual(response.status_code, 200)
        data = DictionaryHTML(response.get_data(as_text=True)).dictionary_data()
        expected_ids = {"en-basics-100", "fr-basics-100", "de-basics-100",
                        "ar-basics-100", "zh-basics-100", "es-basics-100", "ru-basics-100"}
        self.assertEqual({pack["id"] for pack in data["packs"]}, expected_ids)
        self.assertEqual(sum(len(pack["entries"]) for pack in data["packs"]), 700)
        shared_ids = {entry["entry_id"] for entry in data["packs"][0]["entries"]}
        for pack in data["packs"]:
            self.assertEqual(pack["entry_count"], 100)
            self.assertEqual({entry["entry_id"] for entry in pack["entries"]}, shared_ids)
            original = {entry["entry_id"]: entry for entry in CATALOG.words(CATALOG.require(pack["id"]))}
            for entry in pack["entries"]:
                self.assertEqual(set(entry), {"entry_id", "target", "meaning", "accepted_meanings", "transcription", "example"})
                self.assertEqual(entry["target"], original[entry["entry_id"]]["target"])
                self.assertIn(entry["meaning"], entry["accepted_meanings"])
        for forbidden in ("pirajoke", "progress_id", "user_id", "telegram_id", "bot_token", "words.json"):
            self.assertNotIn(forbidden, json.dumps(data))

    def test_ec1_json_payload_escapes_script_terminators(self):
        original_words = CATALOG.words
        def hostile_words(pack):
            entries = original_words(pack)
            entries[0]["meaning"] = '</script><script>alert("xss")</script>'
            entries[0]["accepted_meanings"] = (entries[0]["meaning"],)
            return entries
        with patch.object(CATALOG, "words", side_effect=hostile_words):
            response = self.client.get("/dictionary/")
        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertNotIn('</script><script>alert("xss")</script>', html)
        data = DictionaryHTML(html).dictionary_data()
        self.assertEqual(data["packs"][0]["entries"][0]["meaning"], '</script><script>alert("xss")</script>')

    def test_ec3_pack_export_fails_closed_for_changed_access_or_new_packs(self):
        starter = CATALOG.require("en-basics-100")
        for change in ({"visibility": "admin"}, {"is_free": False},
                       {"status": "draft"}, {"content_schema": 1},
                       {"pack_id": "future-unreviewed-pack"}):
            with self.subTest(change=change):
                packs = tuple(replace(pack, **change) if pack == starter else pack
                              for pack in CATALOG.packs)
                with patch.object(CATALOG, "packs", packs):
                    response = self.client.get("/dictionary/")
                self.assertEqual(response.status_code, 200)
                data = DictionaryHTML(response.get_data(as_text=True)).dictionary_data()
                self.assertEqual(len(data["packs"]), 6)
                self.assertNotIn("en-basics-100", {pack["id"] for pack in data["packs"]})

    def test_ec4_export_never_reflects_admin_session_or_request_values(self):
        sentinel = "private-session-telegram-987654321"
        with self.client.session_transaction() as session:
            session["admin_username"] = sentinel
            session["csrf_token"] = sentinel
        response = self.client.get("/dictionary/?target=" + sentinel)
        self.assertEqual(response.status_code, 200)
        self.assertNotIn(sentinel, response.get_data(as_text=True))
        self.assertNotIn("Cookie", response.headers.get("Vary", ""))
        self.assertNotIn("Set-Cookie", response.headers)

    def test_ac3_download_is_self_contained_attachment_with_hashed_csp(self):
        response = self.client.get("/dictionary/download")
        self.assertEqual(response.status_code, 200)
        self.assertIn("attachment", response.headers["Content-Disposition"])
        self.assertIn("lexi-dictionary.html", response.headers["Content-Disposition"])
        parsed = DictionaryHTML(response.get_data(as_text=True))
        self.assertEqual(len(parsed.dictionary_data()["packs"]), 7)
        executable = [block for block in parsed.blocks if block[0] == "script" and block[1].get("type") != "application/json"]
        styles = [block for block in parsed.blocks if block[0] == "style"]
        self.assertTrue(executable)
        self.assertTrue(styles)
        self.assertFalse(any(attrs.get("src") for _, attrs, _ in executable))
        csp = response.headers["Content-Security-Policy"]
        self.assertNotIn("'unsafe-inline'", csp)
        for _, _, body in executable + styles:
            digest = base64.b64encode(hashlib.sha256(body.encode()).digest()).decode()
            self.assertIn("'sha256-" + digest + "'", csp)

    def test_download_preserves_only_allowlisted_language_defaults(self):
        cases = [
            ({"target": "fr", "native": "de", "ui": "ru"}, ("fr", "de", "ru")),
            ({"target": "ru", "native": "ru", "ui": "fr"}, ("ru", "en", "fr")),
            ({}, ("en", "ru", "en")),
            ({"target": '\"><script>alert("query-xss")</script>',
              "native": "private-request-sentinel", "ui": "constructor"}, ("en", "ru", "en")),
        ]
        for query, expected in cases:
            with self.subTest(query=query):
                response = self.client.get("/dictionary/download", query_string=query)
                self.assertEqual(response.status_code, 200)
                html = response.get_data(as_text=True)
                body = next(attrs for tag, attrs in DictionaryHTML(html).tags if tag == "body")
                self.assertEqual(tuple(body.get("data-default-" + key)
                                       for key in ("target", "native", "ui")), expected)
                self.assertNotIn("query-xss", html)
                self.assertNotIn("private-request-sentinel", html)

    def test_meta_csp_omits_header_only_frame_ancestors(self):
        for path in ("/dictionary/", "/dictionary/download"):
            with self.subTest(path=path):
                response = self.client.get(path)
                tags = DictionaryHTML(response.get_data(as_text=True)).tags
                meta = next(attrs["content"] for tag, attrs in tags
                            if tag == "meta" and attrs.get("http-equiv") == "Content-Security-Policy")
                self.assertNotIn("frame-ancestors", meta)
                self.assertIn("frame-ancestors 'none'", response.headers["Content-Security-Policy"])

    def test_worker_revision_tracks_public_content_and_each_shell_asset(self):
        def worker_source():
            with self.client.get("/dictionary/sw.js") as response:
                self.assertEqual(response.status_code, 200)
                source = response.get_data(as_text=True)
                self.assertNotIn("__DICTIONARY_REVISION__", source)
                self.assertRegex(source, r'const CACHE = "lexi-dictionary-[a-f0-9]{16}";')
                return source

        baseline = worker_source()
        self.assertEqual(worker_source(), baseline)
        original_read_bytes = Path.read_bytes
        for filename in ("dictionary.css", "dictionary.js", "dictionary.html", "dictionary-sw.js"):
            def changed_asset(path, filename=filename):
                source = original_read_bytes(path)
                return source + b"\n/* revision test */" if path.name == filename else source
            with self.subTest(filename=filename), patch.object(Path, "read_bytes", changed_asset):
                self.assertNotEqual(worker_source(), baseline)

        original_words = CATALOG.words
        def changed_entry(pack):
            entries = original_words(pack)
            entries[0]["meaning"] += " updated"
            return entries
        with patch.object(CATALOG, "words", side_effect=changed_entry):
            self.assertNotEqual(worker_source(), baseline)

    def test_worker_revision_never_reads_private_pack_or_learner_state(self):
        original_words = CATALOG.words
        def public_words_only(pack):
            self.assertEqual(pack.visibility, "public")
            self.assertTrue(pack.is_free)
            self.assertEqual(pack.content_schema, 2)
            return original_words(pack)
        with patch.object(CATALOG, "words", side_effect=public_words_only), \
                patch.object(self.store, "Session", side_effect=AssertionError("database query")):
            with self.client.get("/dictionary/sw.js") as response:
                self.assertEqual(response.status_code, 200)
                self.assertNotIn("pirajoke", response.get_data(as_text=True))

    def test_ec2_public_worker_scope_and_manifest_do_not_relax_auth_cache(self):
        worker = self.client.get("/dictionary/sw.js")
        self.assertEqual(worker.status_code, 200)
        self.assertIn("javascript", worker.content_type)
        self.assertEqual(worker.headers["Service-Worker-Allowed"], "/dictionary/")
        worker.close()
        manifest = self.client.get("/dictionary/manifest.webmanifest")
        self.assertEqual(manifest.status_code, 200)
        self.assertEqual(manifest.json["start_url"], "/dictionary/")
        self.assertEqual(manifest.json["scope"], "/dictionary/")
        self.assertEqual(manifest.json["display"], "standalone")
        self.assertEqual(manifest.json["background_color"], "#f7f9fc")
        self.assertEqual(manifest.json["theme_color"], "#12202d")
        self.assertEqual(self.client.get("/admin/login").headers["Cache-Control"], "no-store")
        self.assertEqual(self.client.get("/miniapp/api/bootstrap").headers["Cache-Control"], "no-store")


if __name__ == "__main__":
    unittest.main()
