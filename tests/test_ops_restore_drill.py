from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from ops import mydictionary_restore_drill as restore


class RestoreDrillTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(
            prefix="mydictionary-restore-drill-test-"
        )
        self.root = Path(self.temporary.name)
        os.chmod(self.root, 0o700)
        self.identity = self.root / "age-identity.txt"
        self.identity.write_text("AGE-SECRET-KEY-TEST", encoding="ascii")
        os.chmod(self.identity, 0o600)
        self.receipt_dir = self.root / "receipts"
        self.config = restore.Config(
            age_binary="age",
            rclone_binary="rclone",
            pg_restore_binary="pg_restore",
            psql_binary="psql",
            createdb_binary="createdb",
            dropdb_binary="dropdb",
            age_identity=self.identity,
            remote_prefix="private:mydictionary/backups",
            expected_revision="0011_pilot_operations",
            receipt_dir=self.receipt_dir,
            timeout_seconds=1800,
        )
        self.encrypted_name = (
            "mydictionary-20260806T120000.000000Z-aaaaaaaaaaaa.dump.age"
        )
        self.encrypted_payload = b"authenticated age ciphertext"
        self.commands = []

    def tearDown(self):
        self.temporary.cleanup()

    def runner(self, command, **kwargs):
        self.commands.append((command, kwargs))
        if command[0] == "rclone":
            destination = Path(command[-1])
            if command[-2].endswith(".sha256"):
                digest = hashlib.sha256(self.encrypted_payload).hexdigest()
                destination.write_text(
                    f"{digest}  {self.encrypted_name}\n", encoding="ascii"
                )
            else:
                destination.write_bytes(self.encrypted_payload)
        elif command[0] == "age":
            destination = Path(command[command.index("--output") + 1])
            destination.write_bytes(b"valid PostgreSQL custom dump")
        elif command[0] == "psql":
            return MagicMock(stdout="0011_pilot_operations\n")
        return MagicMock(stdout="")

    def execute(self, runner=None):
        return restore.restore_drill(
            self.config,
            self.encrypted_name,
            execute=True,
            runner=runner or self.runner,
            now=lambda: datetime(2026, 8, 6, 12, 30, tzinfo=timezone.utc),
            token_factory=lambda _: "deadbeef",
        )

    def test_preview_is_read_only_and_names_exact_remote_object(self):
        result = restore.restore_drill(
            self.config,
            self.encrypted_name,
            execute=False,
            runner=self.runner,
        )

        self.assertFalse(result.executed)
        self.assertEqual(self.commands, [])
        self.assertEqual(
            result.remote_object,
            f"private:mydictionary/backups/{self.encrypted_name}",
        )
        self.assertFalse(self.receipt_dir.exists())

    def test_execute_verifies_restores_queries_and_drops_isolated_database(self):
        with patch.dict(
            os.environ,
            {
                "HOME": str(self.root),
                "PATH": "/usr/bin",
                "PGHOST": "/tmp",
                "PGUSER": "restore_operator",
                "BOT_TOKEN": "must-not-leak",
                "OPENAI_API_KEY": "must-not-leak",
                "DATABASE_URL": "must-not-be-used",
            },
            clear=True,
        ):
            result = self.execute()

        self.assertTrue(result.executed)
        self.assertEqual(result.restored_revision, "0011_pilot_operations")
        self.assertEqual(len(result.encrypted_sha256), 64)
        self.assertIsNotNone(result.receipt_path)
        self.assertEqual(result.receipt_path.stat().st_mode & 0o777, 0o600)
        self.assertEqual(self.receipt_dir.stat().st_mode & 0o777, 0o700)
        receipt = json.loads(result.receipt_path.read_text(encoding="utf-8"))
        self.assertEqual(receipt["schema_version"], 1)
        self.assertEqual(receipt["encrypted_backup"], self.encrypted_name)
        self.assertEqual(receipt["database_revision"], "0011_pilot_operations")

        executables = [command[0][0] for command in self.commands]
        self.assertEqual(
            executables,
            [
                "rclone",
                "rclone",
                "age",
                "pg_restore",
                "createdb",
                "pg_restore",
                "psql",
                "dropdb",
            ],
        )
        created_database = self.commands[4][0][-1]
        self.assertRegex(created_database, restore.DRILL_DATABASE_RE)
        self.assertIn("--maintenance-db=postgres", self.commands[4][0])
        restore_command = self.commands[5][0]
        self.assertEqual(
            restore_command[restore_command.index("--dbname") + 1],
            created_database,
        )
        self.assertTrue(restore_command[-1].endswith(".dump"))
        self.assertEqual(self.commands[6][0][2], created_database)
        self.assertEqual(self.commands[7][0][-1], created_database)
        self.assertIn("--maintenance-db=postgres", self.commands[7][0])
        self.assertNotEqual(created_database, "mydictionary")
        for _, options in self.commands:
            self.assertNotIn("BOT_TOKEN", options["env"])
            self.assertNotIn("OPENAI_API_KEY", options["env"])
            self.assertNotIn("DATABASE_URL", options["env"])
            self.assertEqual(options["env"]["PGHOST"], "/tmp")
            self.assertEqual(options["timeout"], 1800)

    def test_checksum_mismatch_fails_before_decryption_or_database_creation(self):
        def runner(command, **kwargs):
            self.commands.append((command, kwargs))
            if command[0] == "rclone":
                destination = Path(command[-1])
                if command[-2].endswith(".sha256"):
                    destination.write_text(
                        f"{'0' * 64}  {self.encrypted_name}\n", encoding="ascii"
                    )
                else:
                    destination.write_bytes(self.encrypted_payload)
            return MagicMock(stdout="")

        with self.assertRaisesRegex(restore.RestoreDrillError, "checksum"):
            self.execute(runner)

        self.assertEqual([command[0][0] for command in self.commands], ["rclone", "rclone"])
        self.assertFalse(self.receipt_dir.exists())

    def test_revision_mismatch_still_drops_database_and_writes_no_receipt(self):
        def runner(command, **kwargs):
            result = self.runner(command, **kwargs)
            if command[0] == "psql":
                return MagicMock(stdout="0010_launch_readiness\n")
            return result

        with self.assertRaisesRegex(restore.RestoreDrillError, "revision"):
            self.execute(runner)

        self.assertEqual(self.commands[-1][0][0], "dropdb")
        self.assertFalse(self.receipt_dir.exists())

    def test_restore_failure_still_drops_database_and_writes_no_receipt(self):
        def runner(command, **kwargs):
            result = self.runner(command, **kwargs)
            if command[0] == "pg_restore" and "--dbname" in command:
                raise subprocess.CalledProcessError(1, command)
            return result

        with self.assertRaises(subprocess.CalledProcessError):
            self.execute(runner)

        self.assertEqual(self.commands[-1][0][0], "dropdb")
        self.assertFalse(self.receipt_dir.exists())

    def test_invalid_remote_identity_permissions_and_name_are_rejected(self):
        environment = {
            "MYDICTIONARY_BACKUP_RCLONE_REMOTE": "private:../escape",
            "MYDICTIONARY_BACKUP_AGE_IDENTITY": str(self.identity),
            "MYDICTIONARY_RESTORE_EXPECTED_REVISION": "0011_pilot_operations",
            "MYDICTIONARY_RESTORE_DRILL_RECEIPT_DIR": str(self.receipt_dir),
        }
        with self.assertRaisesRegex(restore.RestoreDrillError, "REMOTE"):
            restore.Config.from_env(environment)

        environment["MYDICTIONARY_BACKUP_RCLONE_REMOTE"] = (
            "private:mydictionary/backups"
        )
        os.chmod(self.identity, 0o644)
        with self.assertRaisesRegex(restore.RestoreDrillError, "identity"):
            restore.Config.from_env(environment)

        os.chmod(self.identity, 0o600)
        identity_link = self.root / "identity-link"
        identity_link.symlink_to(self.identity)
        environment["MYDICTIONARY_BACKUP_AGE_IDENTITY"] = str(identity_link)
        with self.assertRaisesRegex(restore.RestoreDrillError, "symlink"):
            restore.Config.from_env(environment)

        environment["MYDICTIONARY_BACKUP_AGE_IDENTITY"] = str(self.identity)
        self.receipt_dir.mkdir()
        os.chmod(self.receipt_dir, 0o755)
        with self.assertRaisesRegex(restore.RestoreDrillError, "receipt"):
            restore.Config.from_env(environment)

        with self.assertRaisesRegex(restore.RestoreDrillError, "name"):
            restore.restore_drill(
                self.config,
                "../../production.dump.age",
                execute=False,
                runner=self.runner,
            )


if __name__ == "__main__":
    unittest.main()
