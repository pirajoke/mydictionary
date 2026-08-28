import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


class ScheduledBackupEntrypointTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(
            prefix="mydictionary-scheduled-backup-"
        )
        self.root = Path(self.temporary.name)
        self.calls = self.root / "docker-calls.jsonl"
        self.docker = self.root / "docker"
        self.docker.write_text(
            """#!/usr/bin/env python3
import json
import os
from pathlib import Path
import sys

log = Path(os.environ["FAKE_DOCKER_CALLS"])
with log.open("a", encoding="utf-8") as handle:
    handle.write(json.dumps(sys.argv[1:]) + "\\n")
if len(sys.argv) > 1 and sys.argv[1] == "inspect":
    print("true")
if (
    os.environ.get("FAKE_DOCKER_FAIL_CREATE") == "1"
    and len(sys.argv) > 1
    and sys.argv[1] == "exec"
    and "--check" not in sys.argv
):
    raise SystemExit(9)
""",
            encoding="utf-8",
        )
        self.docker.chmod(0o700)
        self.entrypoint = (
            Path(__file__).resolve().parents[1]
            / "ops"
            / "mydictionary_scheduled_backup.py"
        )

    def tearDown(self):
        self.temporary.cleanup()

    def _run(self, **overrides):
        environment = {
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
            "FAKE_DOCKER_CALLS": str(self.calls),
            "MYDICTIONARY_DOCKER_BINARY": str(self.docker),
            **overrides,
        }
        return subprocess.run(
            [sys.executable, str(self.entrypoint)],
            env=environment,
            capture_output=True,
            text=True,
            timeout=10,
        )

    def _calls(self):
        if not self.calls.exists():
            return []
        return [
            json.loads(line)
            for line in self.calls.read_text(encoding="utf-8").splitlines()
        ]

    def test_daily_entrypoint_runs_versioned_create_then_check_without_secrets(self):
        result = self._run(
            BOT_TOKEN="must-not-appear",
            DATABASE_URL="postgresql://must-not-appear",
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        calls = self._calls()
        self.assertEqual(len(calls), 3)
        self.assertEqual(
            calls[0],
            [
                "inspect",
                "-f",
                "{{.State.Running}}",
                "main-manager-emergency-mydictionary-admin-1",
            ],
        )
        expected_prefix = [
            "exec",
            "main-manager-emergency-mydictionary-admin-1",
            "env",
            "MYDICTIONARY_APP_ROOT=/app/state",
            "MYDICTIONARY_BACKUP_DIR=/app/state/backups",
            "MYDICTIONARY_PGDUMP_DATABASE=mydictionary",
            "python",
            "/app/ops/mydictionary_backup.py",
        ]
        self.assertEqual(calls[1], expected_prefix)
        self.assertEqual(calls[2], [*expected_prefix, "--check"])
        serialized = json.dumps(calls) + result.stdout + result.stderr
        self.assertNotIn("must-not-appear", serialized)
        self.assertNotIn("DATABASE_URL", serialized)
        self.assertNotIn("BOT_TOKEN", serialized)

    def test_daily_entrypoint_stops_before_check_when_create_fails(self):
        result = self._run(FAKE_DOCKER_FAIL_CREATE="1")

        self.assertNotEqual(result.returncode, 0)
        calls = self._calls()
        self.assertEqual(len(calls), 2)
        self.assertNotIn("--check", calls[-1])
        self.assertNotIn(str(self.docker), result.stderr)


if __name__ == "__main__":
    unittest.main()
