import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import call, patch

from ops.mydictionary_autodeploy import (
    Config,
    activate_release,
    changed_mutable_data,
    current_target,
    deploy,
    is_fast_forward,
)


class AutoDeployTest(unittest.TestCase):
    def test_config_uses_external_app_root_and_repository(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            app_root = Path(temp_dir)
            bootstrap_python = app_root / ".venv" / "bin" / "python3"
            with patch.dict(
                os.environ,
                {
                    "MYDICTIONARY_APP_ROOT": str(app_root),
                    "MYDICTIONARY_REPOSITORY_URL": "https://example.com/repo.git",
                    "MYDICTIONARY_BOOTSTRAP_PYTHON": str(bootstrap_python),
                },
                clear=False,
            ):
                config = Config.from_env()

            self.assertEqual(config.app_root, app_root.resolve())
            self.assertEqual(config.repository_url, "https://example.com/repo.git")
            self.assertEqual(config.data_dir, app_root.resolve())

    def test_activate_release_switches_current_symlink_atomically(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            app_root = Path(temp_dir)
            first = app_root / "releases" / "first"
            second = app_root / "releases" / "second"
            first.mkdir(parents=True)
            second.mkdir(parents=True)
            config = self._config(app_root)

            activate_release(config, first)
            self.assertEqual(current_target(config), first.resolve())
            activate_release(config, second)
            self.assertEqual(current_target(config), second.resolve())

    def test_mutable_dictionary_changes_block_automatic_deploy(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "source"
            source.mkdir()
            self._git(source, "init")
            self._git(source, "config", "user.email", "tests@example.com")
            self._git(source, "config", "user.name", "Tests")
            (source / "bot.py").write_text("print('one')\n", encoding="utf-8")
            (source / "words_ja.json").write_text("[]\n", encoding="utf-8")
            self._git(source, "add", "bot.py", "words_ja.json")
            self._git(source, "commit", "-m", "first")
            old_sha = self._git(source, "rev-parse", "HEAD").stdout.strip()

            (source / "words_ja.json").write_text("[{}]\n", encoding="utf-8")
            self._git(source, "add", "words_ja.json")
            self._git(source, "commit", "-m", "dictionary")
            new_sha = self._git(source, "rev-parse", "HEAD").stdout.strip()

            config = self._config(Path(temp_dir), source_dir=source)
            self.assertEqual(
                changed_mutable_data(config, old_sha, new_sha),
                ["words_ja.json"],
            )
            self.assertTrue(is_fast_forward(config, old_sha, new_sha))
            self.assertFalse(is_fast_forward(config, new_sha, old_sha))

    def test_failed_health_check_restores_previous_release(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            app_root = Path(temp_dir)
            old_release = app_root / "releases" / ("a" * 40)
            new_release = app_root / "releases" / ("b" * 40)
            old_release.mkdir(parents=True)
            new_release.mkdir(parents=True)
            config = self._config(app_root)

            module = "ops.mydictionary_autodeploy"
            with (
                patch(f"{module}.validate_config"),
                patch(f"{module}.ensure_source_checkout"),
                patch(f"{module}.main_sha", return_value="b" * 40),
                patch(f"{module}.deployed_sha", return_value="a" * 40),
                patch(f"{module}.current_target", return_value=old_release),
                patch(f"{module}.is_fast_forward", return_value=True),
                patch(f"{module}.changed_mutable_data", return_value=[]),
                patch(f"{module}.build_release", return_value=new_release),
                patch(f"{module}.activate_release") as activate,
                patch(f"{module}.restart_service"),
                patch(f"{module}.LOGGER.exception"),
                patch(
                    f"{module}.wait_for_service",
                    side_effect=[RuntimeError("unhealthy"), None],
                ),
                patch(f"{module}.write_state") as write_state,
            ):
                with self.assertRaisesRegex(RuntimeError, "unhealthy"):
                    deploy(config)

            self.assertEqual(
                activate.call_args_list,
                [call(config, new_release), call(config, old_release)],
            )
            write_state.assert_not_called()

    @staticmethod
    def _git(cwd: Path, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            ["git", *args],
            cwd=cwd,
            check=True,
            capture_output=True,
            text=True,
        )

    @staticmethod
    def _config(app_root: Path, source_dir: Path | None = None) -> Config:
        return Config(
            app_root=app_root,
            repository_url="https://example.com/repo.git",
            service_label="test.service",
            bootstrap_python=app_root / "python3",
            source_dir=source_dir or app_root / "source",
            releases_dir=app_root / "releases",
            current_link=app_root / "current",
            state_file=app_root / ".deployed-sha",
            lock_file=app_root / ".deploy.lock",
            config_file=app_root / "config.yaml",
            data_dir=app_root,
        )


if __name__ == "__main__":
    unittest.main()
