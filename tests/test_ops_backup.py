import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from ops import mydictionary_backup as backup


class BackupPolicyTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="mydictionary-backup-")
        self.root = Path(self.temporary.name)
        self.config = backup.Config(
            app_root=self.root,
            backup_dir=self.root / "backups",
            database_target="mydictionary",
            pg_dump_binary="pg_dump",
            pg_restore_binary="pg_restore",
            psql_binary="psql",
            retention_days=30,
            minimum_backups=2,
            maximum_age_seconds=93600,
            minimum_free_bytes=104857600,
            command_timeout_seconds=1800,
            lock_file=self.root / ".backup.lock",
            state_file=self.root / ".backup-state.json",
        )
        self.commands = []

    def tearDown(self):
        self.temporary.cleanup()

    def fake_run(self, command, **kwargs):
        self.commands.append((command, kwargs))
        if command[0] == "psql":
            return MagicMock(stdout="0005_pilot_access\n")
        if command[0] == "pg_dump":
            destination = Path(command[command.index("--file") + 1])
            destination.write_bytes(b"valid custom PostgreSQL backup")
        return MagicMock(stdout="")

    def create(self, observed_at):
        with patch.object(backup, "run", side_effect=self.fake_run):
            return backup.create_backup(self.config, now=lambda: observed_at)

    def test_backup_is_private_validated_and_contains_no_database_argument(self):
        observed_at = datetime(2026, 8, 4, 8, 0, tzinfo=timezone.utc)
        with patch.dict(
            os.environ,
            {
                "HOME": str(self.root),
                "PATH": "/usr/bin",
                "BOT_TOKEN": "production-token",
                "OPENAI_API_KEY": "production-ai-key",
            },
            clear=True,
        ):
            record = self.create(observed_at)

        self.assertEqual(record.database_revision, "0005_pilot_access")
        self.assertEqual(record.path.stat().st_mode & 0o777, 0o600)
        self.assertEqual(self.config.backup_dir.stat().st_mode & 0o777, 0o700)
        self.assertEqual(self.config.state_file.stat().st_mode & 0o777, 0o600)
        manifest = Path(f"{record.path}.json")
        self.assertEqual(manifest.stat().st_mode & 0o777, 0o600)
        state = json.loads(self.config.state_file.read_text(encoding="utf-8"))
        self.assertNotIn("database_target", state)
        self.assertNotIn("PGDATABASE", json.dumps(state))

        database_commands = [
            item for item in self.commands if item[0][0] in {"psql", "pg_dump"}
        ]
        self.assertEqual(len(database_commands), 2)
        for command, options in database_commands:
            self.assertNotIn("mydictionary", command)
            self.assertEqual(options["env"]["PGDATABASE"], "mydictionary")
            self.assertNotIn("BOT_TOKEN", options["env"])
            self.assertNotIn("OPENAI_API_KEY", options["env"])
            self.assertEqual(options["timeout"], 1800)

    def test_latest_check_revalidates_checksum_manifest_format_and_age(self):
        observed_at = datetime.now(timezone.utc)
        expected = self.create(observed_at)
        self.commands.clear()

        with patch.object(backup, "run", side_effect=self.fake_run):
            actual = backup.verify_latest(self.config)

        self.assertEqual(actual, expected)
        self.assertEqual([command[0][0] for command in self.commands], ["pg_restore"])
        restore_environment = self.commands[0][1]["env"]
        self.assertNotIn("BOT_TOKEN", restore_environment)
        self.assertNotIn("OPENAI_API_KEY", restore_environment)

    def test_latest_check_rejects_tampered_dump(self):
        observed_at = datetime.now(timezone.utc)
        record = self.create(observed_at)
        record.path.write_bytes(b"tampered")

        with self.assertRaisesRegex(backup.BackupError, "size|checksum"):
            backup.verify_latest(self.config)

    def test_latest_check_rejects_stale_backup(self):
        observed_at = datetime(2026, 8, 1, 8, 0, tzinfo=timezone.utc)
        self.create(observed_at)

        with self.assertRaisesRegex(backup.BackupError, "stale"):
            backup.verify_record(
                self.config,
                backup._record_from_payload(
                    self.config,
                    backup._read_json(self.config.state_file),
                ),
                now=lambda: observed_at + timedelta(days=2),
            )

    def test_latest_check_does_not_require_free_space_or_repair_permissions(self):
        observed_at = datetime.now(timezone.utc)
        self.create(observed_at)

        with (
            patch.object(backup.shutil, "disk_usage") as disk_usage,
            patch.object(backup, "run", side_effect=self.fake_run),
        ):
            backup.verify_latest(self.config)

        disk_usage.assert_not_called()

    def test_latest_check_rejects_missing_state_and_public_manifest(self):
        observed_at = datetime.now(timezone.utc)
        record = self.create(observed_at)
        self.config.state_file.unlink()
        with self.assertRaisesRegex(backup.BackupError, "state"):
            backup.verify_latest(self.config)

        self.config.state_file.write_text(
            json.dumps(record.payload()), encoding="utf-8"
        )
        os.chmod(self.config.state_file, 0o600)
        os.chmod(Path(f"{record.path}.json"), 0o644)
        with self.assertRaisesRegex(backup.BackupError, "manifest"):
            backup.verify_latest(self.config)

        Path(f"{record.path}.json").unlink()
        with self.assertRaisesRegex(backup.BackupError, "manifest"):
            backup.verify_latest(self.config)

    def test_failed_dump_leaves_no_backup_or_state(self):
        def failed_run(command, **kwargs):
            if command[0] == "psql":
                return MagicMock(stdout="0005_pilot_access\n")
            raise subprocess.CalledProcessError(1, command)

        with (
            patch.object(backup, "run", side_effect=failed_run),
            self.assertRaises(subprocess.CalledProcessError),
        ):
            backup.create_backup(self.config)

        self.assertFalse(self.config.state_file.exists())
        self.assertEqual(list(self.config.backup_dir.iterdir()), [])

    def test_prune_keeps_count_and_age_floors(self):
        now = datetime(2026, 8, 4, 8, 0, tzinfo=timezone.utc)
        for days_ago in (60, 50, 40, 20, 10, 1):
            self.create(now - timedelta(days=days_ago))

        with patch.object(backup, "run", side_effect=self.fake_run):
            deleted = backup.prune_backups(self.config, now=lambda: now)

        self.assertEqual(deleted, 3)
        remaining = list(self.config.backup_dir.glob("*.dump"))
        self.assertEqual(len(remaining), 3)
        latest = backup._record_from_payload(
            self.config, backup._read_json(self.config.state_file)
        )
        self.assertTrue(latest.path.exists())

    def test_prune_validates_every_candidate_before_deleting_anything(self):
        now = datetime(2026, 8, 4, 8, 0, tzinfo=timezone.utc)
        records = [
            self.create(now - timedelta(days=days_ago))
            for days_ago in (60, 50, 10, 1)
        ]
        records[1].path.write_bytes(b"tampered")
        before = set(self.config.backup_dir.iterdir())

        with (
            patch.object(backup, "run", side_effect=self.fake_run),
            self.assertRaisesRegex(backup.BackupError, "size|checksum"),
        ):
            backup.prune_backups(self.config, now=lambda: now)

        self.assertEqual(set(self.config.backup_dir.iterdir()), before)

    def test_prune_rejects_public_state_without_deleting_anything(self):
        now = datetime(2026, 8, 4, 8, 0, tzinfo=timezone.utc)
        for days_ago in (60, 50, 10, 1):
            self.create(now - timedelta(days=days_ago))
        before = set(self.config.backup_dir.iterdir())
        os.chmod(self.config.state_file, 0o644)

        with self.assertRaisesRegex(backup.BackupError, "state"):
            backup.prune_backups(self.config, now=lambda: now)

        self.assertEqual(set(self.config.backup_dir.iterdir()), before)

    def test_lock_rejects_symlink_without_changing_target(self):
        target = self.root / "target"
        target.write_text("do not modify", encoding="utf-8")
        os.chmod(target, 0o644)
        self.config.lock_file.symlink_to(target)

        with self.assertRaisesRegex(backup.BackupError, "lock"):
            backup._run_locked(self.config, lambda: None)

        self.assertEqual(target.read_text(encoding="utf-8"), "do not modify")
        self.assertEqual(target.stat().st_mode & 0o777, 0o644)

    def test_configuration_has_bounded_retention_defaults(self):
        environment = {
            "MYDICTIONARY_APP_ROOT": str(self.root),
            "MYDICTIONARY_PGDUMP_DATABASE": "mydictionary",
        }
        configured = backup.Config.from_env(environment)
        self.assertEqual(configured.retention_days, 30)
        self.assertEqual(configured.minimum_backups, 7)
        self.assertEqual(configured.maximum_age_seconds, 93600)
        self.assertEqual(configured.command_timeout_seconds, 1800)

        invalid = dict(environment, MYDICTIONARY_BACKUP_RETENTION_DAYS="1")
        with self.assertRaisesRegex(backup.BackupError, "outside"):
            backup.Config.from_env(invalid)

        invalid = dict(
            environment, MYDICTIONARY_BACKUP_COMMAND_TIMEOUT_SECONDS="10"
        )
        with self.assertRaisesRegex(backup.BackupError, "outside"):
            backup.Config.from_env(invalid)

        invalid = dict(
            environment,
            MYDICTIONARY_PGDUMP_DATABASE=(
                "dbname=mydictionary user=operator host=/tmp"
            ),
        )
        with self.assertRaisesRegex(backup.BackupError, "plain database name"):
            backup.Config.from_env(invalid)


if __name__ == "__main__":
    unittest.main()
