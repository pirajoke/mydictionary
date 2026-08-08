import importlib.util
import os
from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "mydictionary_telegram_security",
    ROOT / "ops" / "mydictionary_telegram_security.py",
)
security = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = security
SPEC.loader.exec_module(security)


TOKEN = "123456789:" + "B" * 35


class TelegramLogSecurityTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(
            prefix="mydictionary-telegram-security-"
        )
        self.root = Path(self.temporary.name)
        os.chmod(self.root, 0o700)
        self.source = self.root / "bot.log"
        self.original = (
            f"GET https://api.telegram.org/bot{TOKEN}/getUpdates\n"
            f"retry token={TOKEN}\n"
            "ordinary application line\n"
        ).encode("ascii")
        self.source.write_bytes(self.original)
        os.chmod(self.source, 0o600)

    def tearDown(self):
        self.temporary.cleanup()

    def test_preview_returns_counts_only_and_does_not_write(self):
        result = security.inspect_log(self.source)

        self.assertEqual(result.occurrences, 2)
        self.assertEqual(result.size_bytes, len(self.original))
        self.assertNotIn(TOKEN, repr(result))
        self.assertEqual(self.source.read_bytes(), self.original)

    def test_sanitize_writes_private_new_copy_and_preserves_source(self):
        destination = self.root / "bot.sanitized.log"

        result = security.sanitize_copy(self.source, destination)

        self.assertEqual(result.occurrences, 2)
        self.assertEqual(destination.stat().st_mode & 0o777, 0o600)
        self.assertEqual(self.source.read_bytes(), self.original)
        rendered = destination.read_text(encoding="utf-8")
        self.assertNotIn(TOKEN, rendered)
        self.assertEqual(rendered.count("[REDACTED_BOT_TOKEN]"), 2)
        self.assertIn("ordinary application line", rendered)

    def test_rejects_symlink_source_and_existing_destination(self):
        link = self.root / "source-link"
        link.symlink_to(self.source)
        with self.assertRaisesRegex(security.TelegramSecurityError, "symlink"):
            security.inspect_log(link)

        destination = self.root / "existing.log"
        destination.write_text("keep", encoding="utf-8")
        with self.assertRaisesRegex(security.TelegramSecurityError, "exists"):
            security.sanitize_copy(self.source, destination)
        self.assertEqual(destination.read_text(encoding="utf-8"), "keep")

    def test_rejects_unsafe_source_and_destination_parent(self):
        os.chmod(self.source, 0o644)
        with self.assertRaisesRegex(security.TelegramSecurityError, "permissions"):
            security.inspect_log(self.source)
        os.chmod(self.source, 0o600)

        unsafe = self.root / "unsafe"
        unsafe.mkdir()
        os.chmod(unsafe, 0o777)
        with self.assertRaisesRegex(security.TelegramSecurityError, "directory"):
            security.sanitize_copy(self.source, unsafe / "copy.log")


if __name__ == "__main__":
    unittest.main()
