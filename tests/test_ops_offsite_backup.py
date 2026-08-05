from datetime import datetime, timezone
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from ops import mydictionary_backup as backup
from ops import mydictionary_offsite_backup as offsite


class OffsiteBackupTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="mydictionary-offsite-")
        self.root = Path(self.temporary.name)
        self.dump = self.root / "mydictionary-20260805T120000.000000Z-aaaaaaaaaaaa.dump"
        self.dump.write_bytes(b"private database dump")
        self.record = backup.BackupRecord(
            path=self.dump,
            digest_sha256="a" * 64,
            size_bytes=self.dump.stat().st_size,
            database_revision="0008_product_safety",
            created_at=datetime(2026, 8, 5, 12, 0, tzinfo=timezone.utc),
        )
        self.backup_config = MagicMock(spec=backup.Config)
        self.config = offsite.Config(
            age_binary="age",
            rclone_binary="rclone",
            age_recipient="age1" + "q" * 58,
            remote_prefix="private:mydictionary/backups",
            timeout_seconds=1800,
        )
        self.commands = []

    def tearDown(self):
        self.temporary.cleanup()

    def runner(self, command, **kwargs):
        self.commands.append((command, kwargs))
        if command[0] == "age":
            output = Path(command[command.index("--output") + 1])
            output.write_bytes(b"age encrypted payload")
        return MagicMock(stdout="")

    def test_preview_verifies_source_without_running_upload_commands(self):
        with patch.object(backup, "verify_latest", return_value=self.record) as verify:
            result = offsite.upload_latest(
                self.backup_config,
                self.config,
                execute=False,
                runner=self.runner,
            )

        verify.assert_called_once_with(self.backup_config)
        self.assertFalse(result.executed)
        self.assertEqual(self.commands, [])
        self.assertTrue(result.remote_object.endswith(".dump.age"))

    def test_execute_encrypts_before_two_immutable_uploads(self):
        with patch.object(backup, "verify_latest", return_value=self.record):
            result = offsite.upload_latest(
                self.backup_config,
                self.config,
                execute=True,
                runner=self.runner,
            )

        self.assertTrue(result.executed)
        self.assertEqual([row[0][0] for row in self.commands], ["age", "rclone", "rclone"])
        self.assertIn("--recipient", self.commands[0][0])
        for command, options in self.commands[1:]:
            self.assertIn("--immutable", command)
            self.assertEqual(options["timeout"], 1800)
        uploaded_sources = [Path(row[0][3]).suffix for row in self.commands[1:]]
        self.assertEqual(uploaded_sources, [".age", ".sha256"])
        self.assertEqual(len(result.encrypted_sha256), 64)

    def test_runtime_environment_does_not_forward_application_secrets(self):
        with patch.dict(
            os.environ,
            {
                "PATH": "/usr/bin",
                "BOT_TOKEN": "secret-bot-token",
                "OPENAI_API_KEY": "secret-ai-key",
            },
            clear=True,
        ):
            environment = offsite._environment()

        self.assertEqual(environment, {"PATH": "/usr/bin"})

    def test_invalid_recipient_and_remote_are_rejected(self):
        with self.assertRaises(offsite.OffsiteBackupError):
            offsite.Config.from_env(
                {
                    "MYDICTIONARY_BACKUP_AGE_RECIPIENT": "not-an-age-key",
                    "MYDICTIONARY_BACKUP_RCLONE_REMOTE": "private:backups",
                }
            )
        with self.assertRaises(offsite.OffsiteBackupError):
            offsite.Config.from_env(
                {
                    "MYDICTIONARY_BACKUP_AGE_RECIPIENT": "age1" + "q" * 58,
                    "MYDICTIONARY_BACKUP_RCLONE_REMOTE": "private:../escape",
                }
            )
