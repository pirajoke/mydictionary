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

    def test_cli_derives_private_libpq_contract_from_database_url(self):
        observed_pgpass: list[tuple[Path, int, str]] = []

        def production_container_run(command, **kwargs):
            self.commands.append((command, kwargs))
            environment = kwargs["env"]
            pgpass_value = environment.get("PGPASSFILE")
            if pgpass_value:
                pgpass_path = Path(pgpass_value)
                observed_pgpass.append(
                    (
                        pgpass_path,
                        pgpass_path.stat().st_mode & 0o777,
                        pgpass_path.read_text(encoding="utf-8"),
                    )
                )
            if command[0] == "psql":
                return MagicMock(stdout="0017_admin_auth_recovery\n")
            if command[0] == "pg_dump":
                destination = Path(command[command.index("--file") + 1])
                destination.write_bytes(b"isolated custom PostgreSQL backup")
            return MagicMock(stdout="")

        with (
            patch.dict(
                os.environ,
                {
                    "MYDICTIONARY_APP_ROOT": str(self.root),
                    "MYDICTIONARY_PGDUMP_DATABASE": "mydictionary",
                    "DATABASE_URL": (
                        "postgresql+psycopg://backup-user:"
                        "db%3Asecret%5Cvalue@mydictionary-db:5432/mydictionary"
                    ),
                    "BOT_TOKEN": "must-not-reach-libpq",
                },
                clear=True,
            ),
            patch("sys.argv", ["mydictionary_backup.py"]),
            patch.object(backup, "run", side_effect=production_container_run),
        ):
            result = backup.main()

        self.assertEqual(result, 0)
        database_commands = [
            item for item in self.commands if item[0][0] in {"psql", "pg_dump"}
        ]
        self.assertEqual(len(database_commands), 2)
        for command, options in database_commands:
            environment = options["env"]
            self.assertEqual(environment.get("PGHOST"), "mydictionary-db")
            self.assertEqual(environment.get("PGPORT"), "5432")
            self.assertEqual(environment.get("PGUSER"), "backup-user")
            self.assertEqual(environment.get("PGDATABASE"), "mydictionary")
            self.assertNotIn("DATABASE_URL", environment)
            self.assertNotIn("PGPASSWORD", environment)
            self.assertNotIn("BOT_TOKEN", environment)
            self.assertFalse(any("db:secret" in part for part in command))
        self.assertEqual(len(observed_pgpass), 2)
        for pgpass_path, mode, content in observed_pgpass:
            self.assertEqual(mode, 0o600)
            self.assertEqual(
                content,
                "mydictionary-db:5432:mydictionary:"
                "backup-user:db\\:secret\\\\value\n",
            )
            self.assertFalse(pgpass_path.exists())

    def test_cli_refuses_database_url_for_a_different_database(self):
        runner = MagicMock(return_value=MagicMock(stdout="0017_admin_auth_recovery\n"))
        with (
            patch.dict(
                os.environ,
                {
                    "MYDICTIONARY_APP_ROOT": str(self.root),
                    "MYDICTIONARY_PGDUMP_DATABASE": "mydictionary",
                    "DATABASE_URL": (
                        "postgresql+psycopg://backup-user:secret@"
                        "mydictionary-db:5432/unrelated"
                    ),
                },
                clear=True,
            ),
            patch("sys.argv", ["mydictionary_backup.py"]),
            patch.object(backup, "run", runner),
        ):
            result = backup.main()

        self.assertEqual(result, 1)
        runner.assert_not_called()
        self.assertFalse((self.root / "backups").exists())

    def test_cli_preserves_explicit_unix_socket_contract(self):
        observed_environments: list[dict[str, str]] = []

        def socket_run(command, **kwargs):
            observed_environments.append(dict(kwargs["env"]))
            if command[0] == "psql":
                return MagicMock(stdout="0017_admin_auth_recovery\n")
            if command[0] == "pg_dump":
                destination = Path(command[command.index("--file") + 1])
                destination.write_bytes(b"isolated socket backup")
            return MagicMock(stdout="")

        with (
            patch.dict(
                os.environ,
                {
                    "MYDICTIONARY_APP_ROOT": str(self.root),
                    "MYDICTIONARY_PGDUMP_DATABASE": "mydictionary",
                    "DATABASE_URL": (
                        "postgresql+psycopg://socket-user@/"
                        "mydictionary?host=%2Fvar%2Frun%2Fpostgresql"
                    ),
                    "PGHOST": "/var/run/postgresql",
                    "PGUSER": "socket-user",
                },
                clear=True,
            ),
            patch("sys.argv", ["mydictionary_backup.py"]),
            patch.object(backup, "run", side_effect=socket_run),
        ):
            result = backup.main()

        self.assertEqual(result, 0)
        self.assertGreaterEqual(len(observed_environments), 2)
        for environment in observed_environments[:2]:
            self.assertEqual(environment.get("PGHOST"), "/var/run/postgresql")
            self.assertEqual(environment.get("PGUSER"), "socket-user")
            self.assertNotIn("DATABASE_URL", environment)

    def test_cli_removes_temporary_pgpass_after_database_failure(self):
        observed_pgpass: list[Path] = []

        def failing_database_run(command, **kwargs):
            pgpass_path = Path(kwargs["env"]["PGPASSFILE"])
            observed_pgpass.append(pgpass_path)
            self.assertTrue(pgpass_path.is_file())
            self.assertEqual(pgpass_path.stat().st_mode & 0o777, 0o600)
            raise subprocess.CalledProcessError(1, command)

        with (
            patch.dict(
                os.environ,
                {
                    "MYDICTIONARY_APP_ROOT": str(self.root),
                    "MYDICTIONARY_PGDUMP_DATABASE": "mydictionary",
                    "DATABASE_URL": (
                        "postgresql+psycopg://backup-user:secret@"
                        "mydictionary-db:5432/mydictionary"
                    ),
                },
                clear=True,
            ),
            patch("sys.argv", ["mydictionary_backup.py"]),
            patch.object(backup, "run", side_effect=failing_database_run),
        ):
            result = backup.main()

        self.assertEqual(result, 1)
        self.assertEqual(len(observed_pgpass), 1)
        self.assertFalse(observed_pgpass[0].exists())
        self.assertFalse((self.root / ".backup-state.json").exists())

    def test_cli_rejects_connection_query_values_that_change_the_target(self):
        urls = (
            "postgresql+psycopg://backup-user:secret@db:5432/"
            "mydictionary?port=6543",
            "postgresql+psycopg://backup-user:secret@db:5432/"
            "mydictionary?dbname=unrelated",
            "postgresql+psycopg://backup-user:secret@db:5432/"
            "mydictionary?password=other",
            "postgresql+psycopg://backup-user:secret@db:5432/"
            "mydictionary?host=other-db",
        )
        for database_url in urls:
            with self.subTest(database_url=database_url):
                runner = MagicMock()
                with (
                    patch.dict(
                        os.environ,
                        {
                            "MYDICTIONARY_APP_ROOT": str(self.root),
                            "MYDICTIONARY_PGDUMP_DATABASE": "mydictionary",
                            "DATABASE_URL": database_url,
                        },
                        clear=True,
                    ),
                    patch("sys.argv", ["mydictionary_backup.py"]),
                    patch.object(backup, "run", runner),
                ):
                    result = backup.main()
                self.assertEqual(result, 1)
                runner.assert_not_called()

    def test_cli_rejects_password_url_mixed_with_inherited_pgpassfile(self):
        inherited_pgpass = self.root / "inherited.pgpass"
        inherited_pgpass.write_text(
            "db:5432:mydictionary:backup-user:old-password\n",
            encoding="utf-8",
        )
        os.chmod(inherited_pgpass, 0o600)
        runner = MagicMock()
        with (
            patch.dict(
                os.environ,
                {
                    "MYDICTIONARY_APP_ROOT": str(self.root),
                    "MYDICTIONARY_PGDUMP_DATABASE": "mydictionary",
                    "DATABASE_URL": (
                        "postgresql+psycopg://backup-user:new-password@"
                        "db:5432/mydictionary"
                    ),
                    "PGPASSFILE": str(inherited_pgpass),
                },
                clear=True,
            ),
            patch("sys.argv", ["mydictionary_backup.py"]),
            patch.object(backup, "run", runner),
        ):
            result = backup.main()

        self.assertEqual(result, 1)
        runner.assert_not_called()
        self.assertEqual(
            inherited_pgpass.read_text(encoding="utf-8"),
            "db:5432:mydictionary:backup-user:old-password\n",
        )


if __name__ == "__main__":
    unittest.main()
