from html.parser import HTMLParser
import os
from pathlib import Path
import tempfile
import unittest


os.environ.setdefault("ALLOW_SQLITE_DEV", "true")

from mydictionary.admin import create_app
from mydictionary.storage import DatabaseStore


BANNER_SOURCES = {
    f"/static/miniapp/lexi-section-{section}-v1.webp"
    for section in ("profile", "words", "credits", "languages", "settings")
}


class MiniAppImageParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.in_head = False
        self.preloads = []
        self.banners = []

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        if tag == "head":
            self.in_head = True
        if (
            self.in_head
            and tag == "link"
            and "preload" in attributes.get("rel", "").split()
            and attributes.get("as") == "image"
        ):
            self.preloads.append(attributes.get("href"))
        if tag == "img" and "section-art" in attributes.get("class", "").split():
            self.banners.append(attributes)

    def handle_endtag(self, tag):
        if tag == "head":
            self.in_head = False


class MiniAppImageLoadingTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="miniapp-images-")
        self.addCleanup(temporary.cleanup)
        self.store = DatabaseStore(f"sqlite:///{Path(temporary.name) / 'miniapp.sqlite3'}")
        self.addCleanup(self.store.close)
        self.client = create_app(
            {
                "TESTING": True,
                "SECRET_KEY": "s" * 40,
                "ADMIN_USERNAME": "owner",
                "ADMIN_PASSWORD": "password",
                "MINIAPP_ENABLED": True,
                "MINIAPP_PUBLIC_URL": "https://mydictionary.example.test/miniapp",
                "MINIAPP_BOT_USERNAME": "mydictionary_test_bot",
                "BOT_TOKEN_FILE": "/protected/bot-token",
            },
            database_store=self.store,
        ).test_client()

    def shell_images(self):
        response = self.client.get("/miniapp")
        self.assertEqual(response.status_code, 200)
        parser = MiniAppImageParser()
        parser.feed(response.get_data(as_text=True))
        self.assertEqual(len(parser.banners), 5)
        self.assertEqual({image["src"] for image in parser.banners}, BANNER_SOURCES)
        return parser

    def test_all_tab_banners_are_discoverable_as_head_image_preloads(self):
        parser = self.shell_images()
        self.assertEqual(
            set(parser.preloads),
            {image["src"] for image in parser.banners},
            "all five rendered banners need matching head image preloads before tabs open",
        )

    def test_hidden_tab_banners_do_not_wait_for_lazy_loading(self):
        parser = self.shell_images()
        lazy_sources = [
            image["src"] for image in parser.banners
            if image.get("loading", "eager") != "eager"
        ]
        self.assertEqual(lazy_sources, [], "tab banners must load eagerly, including hidden tabs")

    def test_only_versioned_public_banners_have_reusable_browser_cache(self):
        for source in sorted(BANNER_SOURCES):
            with self.subTest(source=source):
                response = self.client.get(source)
                self.addCleanup(response.close)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.mimetype, "image/webp")
                self.assertTrue(response.cache_control.public, response.headers.get("Cache-Control"))
                self.assertGreater(response.cache_control.max_age or 0, 0)
                self.assertFalse(response.cache_control.no_store)

    def test_shell_api_errors_and_nonbanner_assets_remain_no_store(self):
        for source, status in (
            ("/miniapp", 200),
            ("/miniapp/api/bootstrap", 401),
            ("/miniapp/static/miniapp.js", 200),
            ("/static/mascot/lexi-telegram-avatar-v1.jpg", 200),
        ):
            with self.subTest(source=source):
                response = self.client.get(source)
                self.addCleanup(response.close)
                self.assertEqual(response.status_code, status)
                self.assertEqual(response.headers["Cache-Control"], "no-store")


if __name__ == "__main__":
    unittest.main()
