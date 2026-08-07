import json
import os
from pathlib import Path
import tempfile
import unittest

from mydictionary.runtime_secrets import (
    RuntimeSecretError,
    load_bot_token_file,
    load_runtime_secret_files,
)


VALID_TOKEN = "123456789:" + "A" * 35


class RuntimeSecretsTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(
            prefix="mydictionary-runtime-secrets-"
        )
        self.root = Path(self.temporary.name)
        os.chmod(self.root, 0o700)

    def tearDown(self):
        self.temporary.cleanup()

    def token_file(self, value: str = VALID_TOKEN) -> Path:
        path = self.root / "telegram-bot-token"
        path.write_text(value, encoding="ascii")
        os.chmod(path, 0o600)
        return path

    def test_loads_private_absolute_token_file_without_overwriting_input(self):
        source = {"BOT_TOKEN_FILE": str(self.token_file(VALID_TOKEN + "\n"))}

        result = load_bot_token_file(source)

        self.assertEqual(result["BOT_TOKEN"], VALID_TOKEN)
        self.assertNotIn("BOT_TOKEN", source)

    def test_rejects_inline_conflict_invalid_token_and_relative_path(self):
        path = self.token_file()
        with self.assertRaisesRegex(RuntimeSecretError, "both"):
            load_bot_token_file(
                {"BOT_TOKEN": VALID_TOKEN, "BOT_TOKEN_FILE": str(path)}
            )
        path.write_text("invalid", encoding="ascii")
        with self.assertRaisesRegex(RuntimeSecretError, "format"):
            load_bot_token_file({"BOT_TOKEN_FILE": str(path)})
        with self.assertRaisesRegex(RuntimeSecretError, "absolute"):
            load_bot_token_file({"BOT_TOKEN_FILE": "relative-token"})

    def test_rejects_symlink_and_unsafe_permissions(self):
        token = self.token_file()
        link = self.root / "token-link"
        link.symlink_to(token)
        with self.assertRaisesRegex(RuntimeSecretError, "symlink"):
            load_bot_token_file({"BOT_TOKEN_FILE": str(link)})

        os.chmod(token, 0o640)
        with self.assertRaisesRegex(RuntimeSecretError, "permissions"):
            load_bot_token_file({"BOT_TOKEN_FILE": str(token)})

    def test_combined_loader_populates_test_token_and_user(self):
        credentials = self.root / "test-credentials.json"
        credentials.write_text(
            json.dumps({"bot_token": VALID_TOKEN, "test_user_id": 7001}),
            encoding="utf-8",
        )
        os.chmod(credentials, 0o600)

        result = load_runtime_secret_files(
            {"TELEGRAM_TEST_CREDENTIALS_FILE": str(credentials)}
        )

        self.assertEqual(result["BOT_TOKEN"], VALID_TOKEN)
        self.assertEqual(result["TELEGRAM_TEST_USER_ID"], "7001")


if __name__ == "__main__":
    unittest.main()
