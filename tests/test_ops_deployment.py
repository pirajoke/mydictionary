import io
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
import tarfile
import tempfile
import unittest
from contextlib import ExitStack
from unittest.mock import MagicMock, call, patch

from ops import mydictionary_admin as admin_launcher
from ops import mydictionary_autodeploy as deployer


OLD_SHA = "a" * 40
NEW_SHA = "b" * 40


class OpsTestCase(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.temporary = tempfile.TemporaryDirectory(prefix="mydictionary-ops-")
        self.root = Path(self.temporary.name)
        (self.root / "config.yaml").write_text("token: test\n", encoding="utf-8")
        os.chmod(self.root / "config.yaml", 0o600)
        bootstrap = self.root / "bootstrap-python"
        bootstrap.write_text("", encoding="utf-8")
        for label in ("test.bot", "test.admin"):
            (self.root / f"{label}.plist").write_text("plist", encoding="utf-8")
        self.config = deployer.Config(
            app_root=self.root,
            repository_url="https://github.com/example/mydictionary.git",
            service_labels=("test.bot", "test.admin"),
            service_plists=(
                self.root / "test.bot.plist",
                self.root / "test.admin.plist",
            ),
            bootstrap_python=bootstrap,
            database_url="postgresql+psycopg://user@/mydictionary?host=/tmp",
            pg_dump_database="mydictionary",
            pg_dump_binary="pg_dump",
            pg_restore_binary="pg_restore",
            health_url="http://127.0.0.1:8791/health",
            heartbeat_path=self.root / "bot-heartbeat.json",
            expected_access_mode="allowlist",
            heartbeat_max_age_seconds=45,
            readiness_timeout_seconds=15,
            readiness_consecutive_checks=2,
            source_dir=self.root / ".deploy-source",
            releases_dir=self.root / "releases",
            current_link=self.root / "current",
            deployed_state_file=self.root / ".deployed-sha",
            holds_file=self.root / ".release-holds.json",
            recovery_file=self.root / ".deployment-recovery.json",
            lock_file=self.root / ".deploy.lock",
            config_file=self.root / "config.yaml",
            backup_dir=self.root / "backups",
        )
        self.old_release = self.config.releases_dir / OLD_SHA
        self.new_release = self.config.releases_dir / NEW_SHA
        self.old_release.mkdir(parents=True)
        self.new_release.mkdir(parents=True)

    def tearDown(self):
        self.stack.close()
        self.temporary.cleanup()

    def deploy_patches(self, **overrides):
        values = {
            "ensure_source_checkout": patch.object(deployer, "ensure_source_checkout"),
            "main_sha": patch.object(deployer, "main_sha", return_value=NEW_SHA),
            "deployed_sha": patch.object(deployer, "deployed_sha", return_value=OLD_SHA),
            "current_target": patch.object(
                deployer, "current_target", return_value=self.old_release
            ),
            "release_hold": patch.object(deployer, "release_hold", return_value=None),
            "is_fast_forward": patch.object(
                deployer, "is_fast_forward", return_value=True
            ),
            "changed_paths": patch.object(deployer, "changed_paths", return_value=()),
            "build_release": patch.object(
                deployer, "build_release", return_value=self.new_release
            ),
            "migration_head": patch.object(
                deployer, "migration_head", return_value="0005_pilot_access"
            ),
            "database_revision": patch.object(
                deployer, "database_revision", return_value="0005_pilot_access"
            ),
        }
        values.update(overrides)
        return values


class ConfigurationTest(OpsTestCase):
    def base_environment(self):
        return {
            "MYDICTIONARY_APP_ROOT": str(self.root),
            "MYDICTIONARY_REPOSITORY_URL": (
                "https://github.com/pirajoke/mydictionary.git"
            ),
            "MYDICTIONARY_SERVICE_LABELS": "test.bot,test.admin",
            "MYDICTIONARY_SERVICE_PLISTS": (
                f"{self.root / 'test.bot.plist'},{self.root / 'test.admin.plist'}"
            ),
            "MYDICTIONARY_BOOTSTRAP_PYTHON": str(self.config.bootstrap_python),
            "DATABASE_URL": self.config.database_url,
        }

    def test_configuration_is_loopback_and_allowlist_by_default(self):
        config = deployer.Config.from_env(self.base_environment())

        self.assertEqual(config.expected_access_mode, "allowlist")
        self.assertEqual(config.health_url, "http://127.0.0.1:8791/health")
        self.assertEqual(config.service_labels, ("test.bot", "test.admin"))

    def test_configuration_rejects_public_health_endpoint(self):
        environment = self.base_environment()
        environment["MYDICTIONARY_HEALTH_URL"] = "https://example.com/health"

        with self.assertRaisesRegex(deployer.DeploymentError, "loopback"):
            deployer.Config.from_env(environment)

    def test_configuration_requires_postgresql(self):
        environment = self.base_environment()
        environment["DATABASE_URL"] = "sqlite:////tmp/mydictionary.db"

        with self.assertRaisesRegex(deployer.DeploymentError, "PostgreSQL"):
            deployer.Config.from_env(environment)

    def test_configuration_accepts_plain_backup_database_name(self):
        environment = self.base_environment()
        environment["MYDICTIONARY_PGDUMP_DATABASE"] = "mydictionary"

        config = deployer.Config.from_env(environment)

        self.assertEqual(config.pg_dump_database, "mydictionary")

    def test_configuration_rejects_libpq_conninfo_as_database_name(self):
        environment = self.base_environment()
        environment["MYDICTIONARY_PGDUMP_DATABASE"] = (
            "dbname=mydictionary user=operator host=/tmp"
        )

        with self.assertRaisesRegex(deployer.DeploymentError, "plain database name"):
            deployer.Config.from_env(environment)


class AdminLauncherTest(OpsTestCase):
    def launcher_environment(self, *, ai_enabled="false"):
        release = self.root / "releases" / NEW_SHA
        python = release / ".venv" / "bin" / "python3"
        python.parent.mkdir(parents=True, exist_ok=True)
        python.write_text("", encoding="utf-8")
        current = self.root / "current"
        current.symlink_to(release, target_is_directory=True)
        secrets_file = self.root / "admin-secrets.json"
        secrets_file.write_text(
            json.dumps(
                {
                    "username": "owner",
                    "password_hash": "secret-password-hash",
                    "session_secret": "s" * 40,
                }
            ),
            encoding="utf-8",
        )
        os.chmod(secrets_file, 0o600)
        local_config = self.root / "local-config"
        local_config.mkdir(exist_ok=True)
        os.chmod(local_config, 0o700)
        return {
            "MYDICTIONARY_APP_ROOT": str(self.root),
            "DATABASE_URL": self.config.database_url,
            "AI_TUTOR_ENABLED": ai_enabled,
        }

    def test_launcher_uses_active_sha_shared_data_and_no_secret_arguments(self):
        executable, arguments, environment, working_directory = (
            admin_launcher.build_process(self.launcher_environment())
        )

        self.assertEqual(executable, working_directory / ".venv/bin/python3")
        self.assertEqual(environment["DATA_DIR"], str(self.root.resolve()))
        self.assertEqual(environment["RELEASE_SHA"], NEW_SHA)
        self.assertEqual(environment["AI_TUTOR_ENABLED"], "false")
        self.assertEqual(environment["AI_PROVIDER_CONFIGURED"], "false")
        self.assertEqual(environment["VOICE_TUTOR_ENABLED"], "false")
        self.assertEqual(
            environment["VOICE_TRANSCRIPTION_MODEL"], "gpt-4o-transcribe"
        )
        self.assertEqual(environment["TELEGRAM_STARS_ENABLED"], "false")
        self.assertEqual(environment["ADMIN_COOKIE_SECURE"], "true")
        rendered_arguments = " ".join(arguments)
        self.assertNotIn("secret-password-hash", rendered_arguments)
        self.assertNotIn("s" * 40, rendered_arguments)
        self.assertIn("127.0.0.1:8791", rendered_arguments)

    def test_launcher_refuses_to_enable_ai(self):
        with self.assertRaisesRegex(RuntimeError, "refuses to enable AI"):
            admin_launcher.build_process(self.launcher_environment(ai_enabled="true"))

    def test_launcher_forwards_non_secret_economics_diagnostics(self):
        source = self.launcher_environment()
        source.update(
            {
                "AI_MODEL": "gpt-5.6-luna",
                "AI_SERVICE_TIER": "default",
                "AI_PRICING_REVIEWED_ON": "2026-08-06",
                "AI_PRICING_MAX_AGE_DAYS": "30",
                "AI_ECONOMICS_SNAPSHOT_PATH": "config/launch-economics.json",
                "AI_ECONOMICS_SNAPSHOT_ID": "snapshot-test",
                "AI_ECONOMICS_SNAPSHOT_SHA256": "a" * 64,
                "AI_MAX_DAILY_REQUESTS_PER_USER": "5",
                "AI_MAX_PREFLIGHT_COST_MICRO_USD_PER_REQUEST": "5000",
                "AI_RETROSPECTIVE_BREAKER_MICRO_USD_PER_RESPONSE": "5000",
                "AI_MAX_PROJECT_COST_MICRO_USD_PER_DAY": "25000",
                "AI_MAX_PROJECT_COST_MICRO_USD_PER_MONTH": "100000",
                "AI_MAX_IN_FLIGHT_COST_MICRO_USD": "5000",
                "AI_MAX_PROVIDER_INPUT_CHARS": "12000",
                "AI_MAX_OUTPUT_TOKENS": "1000",
                "AI_METERING_JOURNAL_PATH": "/tmp/ai-metering.jsonl",
                "BILLING_ECONOMICS_REVIEWED_ON": "2026-08-06",
                "BILLING_ECONOMICS_MAX_AGE_DAYS": "30",
                "BILLING_PRIVATE_CHAT_TOPICS_ENABLED": "false",
                "BILLING_TERMS_APPROVED": "false",
                "OPENAI_API_KEY": "must-not-reach-admin",
                "AI_SAFETY_SALT": "must-not-reach-admin-either",
            }
        )

        _, _, environment, _ = admin_launcher.build_process(source)

        self.assertEqual(environment["AI_MODEL"], "gpt-5.6-luna")
        self.assertEqual(environment["AI_SERVICE_TIER"], "default")
        self.assertEqual(environment["AI_PROVIDER_CONFIGURED"], "true")
        self.assertEqual(environment["AI_MAX_DAILY_REQUESTS_PER_USER"], "5")
        self.assertEqual(
            environment["AI_ECONOMICS_SNAPSHOT_SHA256"], "a" * 64
        )
        self.assertEqual(
            environment["AI_MAX_PROJECT_COST_MICRO_USD_PER_MONTH"], "100000"
        )
        self.assertEqual(environment["BILLING_TERMS_APPROVED"], "false")
        self.assertNotIn("OPENAI_API_KEY", environment)
        self.assertNotIn("AI_SAFETY_SALT", environment)

    def test_launcher_forwards_bounded_one_time_key_enrollment(self):
        source = self.launcher_environment()
        target = self.root / "local-config" / "openai-gate2.key"
        expiry = datetime.now(timezone.utc) + timedelta(minutes=30)
        source.update(
            {
                "AI_KEY_ENROLLMENT_ENABLED": "true",
                "AI_KEY_ENROLLMENT_PATH": str(target),
                "AI_KEY_ENROLLMENT_EXPIRES_AT": expiry.isoformat(),
            }
        )

        _, _, environment, _ = admin_launcher.build_process(source)

        self.assertEqual(environment["AI_KEY_ENROLLMENT_ENABLED"], "true")
        self.assertEqual(environment["AI_KEY_ENROLLMENT_PATH"], str(target))
        self.assertEqual(
            environment["AI_KEY_ENROLLMENT_EXPIRES_AT"], expiry.isoformat()
        )
        self.assertNotIn("OPENAI_API_KEY", environment)

    def test_launcher_rejects_key_enrollment_outside_local_config(self):
        source = self.launcher_environment()
        source.update(
            {
                "AI_KEY_ENROLLMENT_ENABLED": "true",
                "AI_KEY_ENROLLMENT_PATH": str(self.root / "openai.key"),
                "AI_KEY_ENROLLMENT_EXPIRES_AT": (
                    datetime.now(timezone.utc) + timedelta(minutes=30)
                ).isoformat(),
            }
        )

        with self.assertRaisesRegex(RuntimeError, "must stay in local-config"):
            admin_launcher.build_process(source)

    def test_launcher_rejects_release_outside_versioned_tree(self):
        environment = self.launcher_environment()
        outside = self.root / NEW_SHA
        outside_python = outside / ".venv" / "bin" / "python3"
        outside_python.parent.mkdir(parents=True)
        outside_python.write_text("", encoding="utf-8")
        self.config.current_link.unlink()
        self.config.current_link.symlink_to(outside, target_is_directory=True)

        with self.assertRaisesRegex(RuntimeError, "versioned release tree"):
            admin_launcher.build_process(environment)


class ReadinessTest(OpsTestCase):
    def write_heartbeat(self, *, sha=NEW_SHA, access_mode="allowlist"):
        payload = {
            "schema_version": 1,
            "state": "ready",
            "heartbeat_at": deployer.utcnow().isoformat(),
            "release_sha": sha,
            "access_mode": access_mode,
        }
        self.config.heartbeat_path.write_text(json.dumps(payload), encoding="utf-8")

    def test_probe_requires_process_heartbeat_release_access_and_http(self):
        self.write_heartbeat()
        with (
            patch.object(deployer, "service_is_running", return_value=True),
            patch.object(deployer, "_http_health", return_value=True),
        ):
            self.assertEqual(
                deployer.readiness_probe(self.config, NEW_SHA),
                deployer.ProbeResult(True, "ready"),
            )

        self.write_heartbeat(sha=OLD_SHA)
        with (
            patch.object(deployer, "service_is_running", return_value=True),
            patch.object(deployer, "_http_health", return_value=True),
        ):
            self.assertEqual(
                deployer.readiness_probe(self.config, NEW_SHA).reason,
                "release_mismatch",
            )

        self.write_heartbeat(access_mode="public")
        with (
            patch.object(deployer, "service_is_running", return_value=True),
            patch.object(deployer, "_http_health", return_value=True),
        ):
            self.assertEqual(
                deployer.readiness_probe(self.config, NEW_SHA).reason,
                "access_mode_mismatch",
            )


class DeployPolicyTest(OpsTestCase):
    def enter_all(self, patches):
        return {name: self.stack.enter_context(value) for name, value in patches.items()}

    def test_unattended_release_with_migration_is_held_before_activation(self):
        patches = self.deploy_patches(
            migration_head=patch.object(
                deployer, "migration_head", return_value="0006_next"
            )
        )
        active = self.enter_all(patches)
        record = self.stack.enter_context(patch.object(deployer, "record_hold"))
        automatic = self.stack.enter_context(patch.object(deployer, "_automatic_deploy"))

        result = deployer.deploy(self.config)

        self.assertEqual(result, "held")
        record.assert_called_once()
        self.assertEqual(record.call_args.kwargs["kind"], "operator_required")
        self.assertEqual(record.call_args.kwargs["stage"], "migration_required")
        automatic.assert_not_called()
        active["build_release"].assert_called_once()

    def test_unattended_content_change_is_held(self):
        patches = self.deploy_patches(
            changed_paths=patch.object(
                deployer,
                "changed_paths",
                return_value=("content/basic_100.tsv", "words_ar_basic.json"),
            )
        )
        self.enter_all(patches)
        record = self.stack.enter_context(patch.object(deployer, "record_hold"))
        automatic = self.stack.enter_context(patch.object(deployer, "_automatic_deploy"))

        result = deployer.deploy(self.config)

        self.assertEqual(result, "held")
        self.assertEqual(record.call_args.kwargs["stage"], "content_review_required")
        automatic.assert_not_called()

    def test_content_contract_v2_pack_files_are_protected(self):
        paths = (
            "content/basic_100.tsv",
            "content/catalog.json",
            "words_en_basic.json",
            "words_fr_basic.json",
            "words_de_basic.json",
            "words_ja.json",
            "words_ar_basic.json",
            "words_zh_basic.json",
            "words_ru_basic.json",
            "words_es_basic.json",
        )

        self.assertEqual(deployer.protected_content_changes(paths), paths)

    def test_failed_sha_quarantine_skips_build_and_restart(self):
        self.config.lock_file.write_text("", encoding="utf-8")
        os.chmod(self.config.lock_file, 0o666)
        patches = self.deploy_patches(
            release_hold=patch.object(
                deployer,
                "release_hold",
                return_value={"kind": "failed", "stage": "readiness"},
            )
        )
        active = self.enter_all(patches)

        result = deployer.deploy(self.config)

        self.assertEqual(result, "held")
        active["build_release"].assert_not_called()
        self.assertEqual(self.config.lock_file.stat().st_mode & 0o777, 0o600)

    def test_deployed_sha_must_match_current_release(self):
        patches = self.deploy_patches(
            current_target=patch.object(
                deployer, "current_target", return_value=self.new_release
            )
        )
        active = self.enter_all(patches)

        with self.assertRaisesRegex(deployer.DeploymentError, "deployed SHA"):
            deployer.deploy(self.config)

        active["build_release"].assert_not_called()

    def test_candidate_validation_failure_is_quarantined(self):
        patches = self.deploy_patches(
            build_release=patch.object(
                deployer,
                "build_release",
                side_effect=deployer.CandidateValidationError("tests failed"),
            )
        )
        self.enter_all(patches)
        record = self.stack.enter_context(patch.object(deployer, "record_hold"))

        with self.assertRaises(deployer.CandidateValidationError):
            deployer.deploy(self.config)

        self.assertEqual(record.call_args.kwargs["kind"], "failed")
        self.assertEqual(record.call_args.kwargs["stage"], "candidate_validation")

    def test_code_readiness_failure_rolls_back_only_when_database_is_unchanged(self):
        activate = self.stack.enter_context(patch.object(deployer, "activate_release"))
        self.stack.enter_context(patch.object(deployer, "restart_services"))
        wait = self.stack.enter_context(
            patch.object(
                deployer,
                "wait_for_readiness",
                side_effect=[deployer.ReadinessError("unhealthy"), None],
            )
        )
        self.stack.enter_context(
            patch.object(
                deployer, "database_revision", return_value="0005_pilot_access"
            )
        )
        record = self.stack.enter_context(patch.object(deployer, "record_hold"))
        write = self.stack.enter_context(patch.object(deployer, "write_deployed_state"))

        with self.assertRaises(deployer.ReadinessError):
            deployer._automatic_deploy(
                self.config,
                target_sha=NEW_SHA,
                previous_sha=OLD_SHA,
                previous_release=self.old_release,
                release=self.new_release,
                previous_revision="0005_pilot_access",
            )

        self.assertEqual(
            activate.call_args_list,
            [call(self.config, self.new_release), call(self.config, self.old_release)],
        )
        self.assertEqual(wait.call_args_list[-1], call(self.config, OLD_SHA))
        self.assertEqual(record.call_args.kwargs["kind"], "failed")
        write.assert_not_called()

    def test_database_change_refuses_automatic_rollback(self):
        activate = self.stack.enter_context(patch.object(deployer, "activate_release"))
        self.stack.enter_context(patch.object(deployer, "restart_services"))
        self.stack.enter_context(
            patch.object(
                deployer,
                "wait_for_readiness",
                side_effect=deployer.ReadinessError("unhealthy"),
            )
        )
        self.stack.enter_context(
            patch.object(deployer, "database_revision", return_value="0006_next")
        )
        self.stack.enter_context(patch.object(deployer, "record_hold"))
        recovery = self.stack.enter_context(patch.object(deployer, "write_recovery_state"))

        with self.assertRaises(deployer.ManualRecoveryRequired):
            deployer._automatic_deploy(
                self.config,
                target_sha=NEW_SHA,
                previous_sha=OLD_SHA,
                previous_release=self.old_release,
                release=self.new_release,
                previous_revision="0005_pilot_access",
            )

        activate.assert_called_once_with(self.config, self.new_release)
        self.assertEqual(
            recovery.call_args.args[1]["status"], "manual_recovery_required"
        )

    def test_failed_database_probe_refuses_automatic_rollback(self):
        activate = self.stack.enter_context(patch.object(deployer, "activate_release"))
        self.stack.enter_context(patch.object(deployer, "restart_services"))
        self.stack.enter_context(
            patch.object(
                deployer,
                "wait_for_readiness",
                side_effect=deployer.ReadinessError("unhealthy"),
            )
        )
        self.stack.enter_context(
            patch.object(
                deployer,
                "database_revision",
                side_effect=RuntimeError("database unavailable"),
            )
        )
        self.stack.enter_context(patch.object(deployer, "record_hold"))
        recovery = self.stack.enter_context(
            patch.object(deployer, "write_recovery_state")
        )

        with self.assertRaises(deployer.ManualRecoveryRequired):
            deployer._automatic_deploy(
                self.config,
                target_sha=NEW_SHA,
                previous_sha=OLD_SHA,
                previous_release=self.old_release,
                release=self.new_release,
                previous_revision="0005_pilot_access",
            )

        activate.assert_called_once_with(self.config, self.new_release)
        self.assertEqual(
            recovery.call_args.args[1]["stage"],
            "readiness_database_probe_failed",
        )

    def test_failed_old_release_readiness_records_manual_recovery(self):
        activate = self.stack.enter_context(patch.object(deployer, "activate_release"))
        self.stack.enter_context(patch.object(deployer, "restart_services"))
        self.stack.enter_context(
            patch.object(
                deployer,
                "wait_for_readiness",
                side_effect=[
                    deployer.ReadinessError("candidate unhealthy"),
                    deployer.ReadinessError("old release unhealthy"),
                ],
            )
        )
        self.stack.enter_context(
            patch.object(
                deployer, "database_revision", return_value="0005_pilot_access"
            )
        )
        self.stack.enter_context(patch.object(deployer, "record_hold"))
        recovery = self.stack.enter_context(
            patch.object(deployer, "write_recovery_state")
        )

        with self.assertRaises(deployer.ManualRecoveryRequired):
            deployer._automatic_deploy(
                self.config,
                target_sha=NEW_SHA,
                previous_sha=OLD_SHA,
                previous_release=self.old_release,
                release=self.new_release,
                previous_revision="0005_pilot_access",
            )

        self.assertEqual(
            activate.call_args_list,
            [call(self.config, self.new_release), call(self.config, self.old_release)],
        )
        self.assertEqual(
            recovery.call_args.args[1]["stage"], "automatic_rollback_failed"
        )


class ServiceLifecycleTest(OpsTestCase):
    def test_stop_services_waits_for_async_launchctl_removal(self):
        launchctl = self.stack.enter_context(
            patch.object(
                deployer.subprocess,
                "run",
                return_value=MagicMock(returncode=0),
            )
        )
        loaded = self.stack.enter_context(
            patch.object(
                deployer,
                "service_is_loaded",
                side_effect=[True, False, False],
            )
        )
        self.stack.enter_context(
            patch.object(deployer, "SERVICE_TRANSITION_POLL_SECONDS", 0)
        )

        deployer.stop_services(self.config)

        domain = f"gui/{os.getuid()}"
        self.assertEqual(
            [entry.args[0] for entry in launchctl.call_args_list],
            [
                ["launchctl", "bootout", f"{domain}/test.admin"],
                ["launchctl", "bootout", f"{domain}/test.bot"],
            ],
        )
        self.assertEqual(loaded.call_count, 3)

    def test_stop_services_fails_if_registration_never_disappears(self):
        self.stack.enter_context(
            patch.object(
                deployer.subprocess,
                "run",
                return_value=MagicMock(returncode=0),
            )
        )
        self.stack.enter_context(
            patch.object(deployer, "service_is_loaded", return_value=True)
        )
        self.stack.enter_context(
            patch.object(deployer, "SERVICE_TRANSITION_TIMEOUT_SECONDS", 0)
        )

        with self.assertRaisesRegex(
            deployer.DeploymentError,
            "test.admin, test.bot",
        ):
            deployer.stop_services(self.config)

    def test_bootstrap_reloads_current_plist_after_stale_registration(self):
        launchctl = self.stack.enter_context(
            patch.object(
                deployer.subprocess,
                "run",
                return_value=MagicMock(returncode=0),
            )
        )
        self.stack.enter_context(
            patch.object(deployer, "service_is_loaded", return_value=True)
        )
        wait = self.stack.enter_context(
            patch.object(deployer, "wait_for_service_registration")
        )
        command = self.stack.enter_context(patch.object(deployer, "run"))
        config = MagicMock(
            service_labels=("test.admin",),
            service_plists=(self.root / "test.admin.plist",),
        )

        deployer.bootstrap_services(config)

        domain = f"gui/{os.getuid()}"
        launchctl.assert_called_once_with(
            ["launchctl", "bootout", f"{domain}/test.admin"],
            capture_output=True,
            text=True,
        )
        command.assert_called_once_with(
            [
                "launchctl",
                "bootstrap",
                domain,
                str(self.root / "test.admin.plist"),
            ]
        )
        self.assertEqual(
            wait.call_args_list,
            [
                call("test.admin", loaded=False),
                call("test.admin", loaded=True),
            ],
        )


class RecoveryAdoptionTest(OpsTestCase):
    def _record_manual_recovery(self, *, target_sha=NEW_SHA):
        backup = self.config.backup_dir / "mydictionary-reviewed.dump"
        backup.parent.mkdir()
        backup.write_bytes(b"reviewed backup")
        record = deployer.BackupRecord(
            backup,
            deployer._sha256_file(backup),
            "0005_pilot_access",
            "0006_next",
        )
        deployer.write_recovery_state(
            self.config,
            deployer._recovery_payload(
                status="manual_recovery_required",
                target_sha=target_sha,
                previous_sha=OLD_SHA,
                previous_revision=record.database_revision,
                target_revision=record.target_revision,
                backup=record,
                stage="migration_or_readiness_failed_contained",
            ),
        )
        deployer.record_hold(
            self.config,
            NEW_SHA,
            kind="failed",
            stage="operator_migration",
            error_type="ReadinessError",
            previous_sha=OLD_SHA,
        )
        return record

    def _patch_healthy_current_release(self):
        self.stack.enter_context(patch.object(deployer, "validate_config"))
        self.stack.enter_context(patch.object(deployer, "ensure_source_checkout"))
        self.stack.enter_context(
            patch.object(deployer, "main_sha", return_value=NEW_SHA)
        )
        self.stack.enter_context(
            patch.object(deployer, "current_target", return_value=self.new_release)
        )
        self.stack.enter_context(
            patch.object(deployer, "database_revision", return_value="0006_next")
        )
        self.stack.enter_context(
            patch.object(deployer, "migration_head", return_value="0006_next")
        )
        self.stack.enter_context(patch.object(deployer, "wait_for_readiness"))

    def test_adopt_completes_matching_verified_manual_recovery(self):
        record = self._record_manual_recovery()
        self._patch_healthy_current_release()
        command = self.stack.enter_context(patch.object(deployer, "run"))

        result = deployer.adopt_current_release(self.config)

        self.assertEqual(result, NEW_SHA)
        self.assertEqual(self.config.deployed_state_file.read_text().strip(), NEW_SHA)
        self.assertIsNone(deployer.release_hold(self.config, NEW_SHA))
        recovery = json.loads(self.config.recovery_file.read_text(encoding="utf-8"))
        self.assertEqual(recovery["status"], "completed")
        self.assertEqual(recovery["stage"], "ready_after_manual_adopt")
        command.assert_called_once_with(
            [self.config.pg_restore_binary, "--list", str(record.path)]
        )

    def test_adopt_refuses_mismatched_manual_recovery_and_keeps_hold(self):
        self._record_manual_recovery(target_sha=OLD_SHA)
        self._patch_healthy_current_release()

        with self.assertRaisesRegex(
            deployer.DeploymentError,
            "Recovery target does not match current release",
        ):
            deployer.adopt_current_release(self.config)

        self.assertFalse(self.config.deployed_state_file.exists())
        self.assertIsNotNone(deployer.release_hold(self.config, NEW_SHA))

    def test_adopt_refuses_tampered_recovery_backup_and_keeps_hold(self):
        record = self._record_manual_recovery()
        record.path.write_bytes(b"tampered backup")
        self._patch_healthy_current_release()

        with self.assertRaisesRegex(
            deployer.DeploymentError,
            "Recovery backup digest does not match",
        ):
            deployer.adopt_current_release(self.config)

        self.assertFalse(self.config.deployed_state_file.exists())
        self.assertIsNotNone(deployer.release_hold(self.config, NEW_SHA))


class OperatorMigrationTest(OpsTestCase):
    def test_operator_migration_backs_up_stops_migrates_and_proves_readiness(self):
        backup = deployer.BackupRecord(
            self.root / "backup.dump", "c" * 64, "0005_pilot_access", "0006_next"
        )
        validate = self.stack.enter_context(patch.object(deployer, "validate_config"))
        stop = self.stack.enter_context(patch.object(deployer, "stop_services"))
        backup_call = self.stack.enter_context(
            patch.object(deployer, "backup_database", return_value=backup)
        )
        activate = self.stack.enter_context(patch.object(deployer, "activate_release"))
        migrate = self.stack.enter_context(patch.object(deployer, "apply_migrations"))
        self.stack.enter_context(
            patch.object(deployer, "database_revision", return_value="0006_next")
        )
        bootstrap = self.stack.enter_context(patch.object(deployer, "bootstrap_services"))
        ready = self.stack.enter_context(patch.object(deployer, "wait_for_readiness"))
        deployed = self.stack.enter_context(patch.object(deployer, "write_deployed_state"))
        self.stack.enter_context(patch.object(deployer, "clear_hold"))
        recovery = self.stack.enter_context(patch.object(deployer, "write_recovery_state"))

        result = deployer._operator_migration_deploy(
            self.config,
            target_sha=NEW_SHA,
            previous_sha=OLD_SHA,
            previous_release=self.old_release,
            release=self.new_release,
            previous_revision="0005_pilot_access",
            target_revision="0006_next",
        )

        self.assertEqual(result, NEW_SHA)
        validate.assert_called_once_with(self.config, require_plists=True)
        stop.assert_called_once_with(self.config)
        backup_call.assert_called_once()
        activate.assert_called_once_with(self.config, self.new_release)
        migrate.assert_called_once_with(self.config, self.new_release)
        bootstrap.assert_called_once_with(self.config)
        ready.assert_called_once_with(self.config, NEW_SHA)
        deployed.assert_called_once_with(self.config, NEW_SHA)
        self.assertEqual(recovery.call_args.args[1]["status"], "completed")

    def test_migration_failure_never_reactivates_old_code(self):
        backup = deployer.BackupRecord(
            self.root / "backup.dump", "c" * 64, "0005_pilot_access", "0006_next"
        )
        self.stack.enter_context(patch.object(deployer, "validate_config"))
        stop = self.stack.enter_context(patch.object(deployer, "stop_services"))
        self.stack.enter_context(
            patch.object(deployer, "backup_database", return_value=backup)
        )
        activate = self.stack.enter_context(patch.object(deployer, "activate_release"))
        self.stack.enter_context(
            patch.object(deployer, "apply_migrations", side_effect=RuntimeError("boom"))
        )
        bootstrap = self.stack.enter_context(patch.object(deployer, "bootstrap_services"))
        self.stack.enter_context(patch.object(deployer, "record_hold"))
        recovery = self.stack.enter_context(patch.object(deployer, "write_recovery_state"))

        with self.assertRaises(deployer.ManualRecoveryRequired):
            deployer._operator_migration_deploy(
                self.config,
                target_sha=NEW_SHA,
                previous_sha=OLD_SHA,
                previous_release=self.old_release,
                release=self.new_release,
                previous_revision="0005_pilot_access",
                target_revision="0006_next",
            )

        activate.assert_called_once_with(self.config, self.new_release)
        bootstrap.assert_not_called()
        self.assertEqual(stop.call_count, 2)
        self.assertEqual(
            recovery.call_args.args[1]["status"], "manual_recovery_required"
        )
        self.assertEqual(
            recovery.call_args.args[1]["stage"],
            "migration_or_readiness_failed_contained",
        )

    def test_pre_migration_activation_failure_restores_previous_runtime(self):
        backup = deployer.BackupRecord(
            self.root / "backup.dump", "c" * 64, "0005_pilot_access", "0006_next"
        )
        self.stack.enter_context(patch.object(deployer, "validate_config"))
        self.stack.enter_context(patch.object(deployer, "stop_services"))
        self.stack.enter_context(
            patch.object(deployer, "backup_database", return_value=backup)
        )
        activate = self.stack.enter_context(
            patch.object(
                deployer,
                "activate_release",
                side_effect=[RuntimeError("activation failed"), None],
            )
        )
        bootstrap = self.stack.enter_context(
            patch.object(deployer, "bootstrap_services")
        )
        ready = self.stack.enter_context(patch.object(deployer, "wait_for_readiness"))
        migrate = self.stack.enter_context(patch.object(deployer, "apply_migrations"))
        record = self.stack.enter_context(patch.object(deployer, "record_hold"))
        recovery = self.stack.enter_context(
            patch.object(deployer, "write_recovery_state")
        )

        with self.assertRaisesRegex(RuntimeError, "activation failed"):
            deployer._operator_migration_deploy(
                self.config,
                target_sha=NEW_SHA,
                previous_sha=OLD_SHA,
                previous_release=self.old_release,
                release=self.new_release,
                previous_revision="0005_pilot_access",
                target_revision="0006_next",
            )

        self.assertEqual(
            activate.call_args_list,
            [call(self.config, self.new_release), call(self.config, self.old_release)],
        )
        bootstrap.assert_called_once_with(self.config)
        ready.assert_called_once_with(self.config, OLD_SHA)
        migrate.assert_not_called()
        self.assertEqual(record.call_args.kwargs["kind"], "operator_required")
        self.assertEqual(
            record.call_args.kwargs["stage"], "operator_pre_migration_retry"
        )
        self.assertEqual(recovery.call_args.args[1]["status"], "recovered")

    def test_backup_failure_is_retryable_after_previous_runtime_recovers(self):
        self.stack.enter_context(patch.object(deployer, "validate_config"))
        self.stack.enter_context(patch.object(deployer, "stop_services"))
        self.stack.enter_context(
            patch.object(
                deployer,
                "backup_database",
                side_effect=deployer.DeploymentError("pg_dump unavailable"),
            )
        )
        activate = self.stack.enter_context(patch.object(deployer, "activate_release"))
        self.stack.enter_context(patch.object(deployer, "bootstrap_services"))
        self.stack.enter_context(patch.object(deployer, "wait_for_readiness"))
        record = self.stack.enter_context(patch.object(deployer, "record_hold"))

        with self.assertRaisesRegex(deployer.DeploymentError, "pg_dump unavailable"):
            deployer._operator_migration_deploy(
                self.config,
                target_sha=NEW_SHA,
                previous_sha=OLD_SHA,
                previous_release=self.old_release,
                release=self.new_release,
                previous_revision="0005_pilot_access",
                target_revision="0006_next",
            )

        activate.assert_called_once_with(self.config, self.old_release)
        self.assertEqual(record.call_args.kwargs["kind"], "operator_required")
        self.assertEqual(
            record.call_args.kwargs["stage"], "operator_pre_migration_retry"
        )

    def test_partial_service_stop_is_restored_before_backup(self):
        self.stack.enter_context(patch.object(deployer, "validate_config"))
        self.stack.enter_context(
            patch.object(
                deployer,
                "stop_services",
                side_effect=deployer.DeploymentError("partial stop"),
            )
        )
        bootstrap = self.stack.enter_context(
            patch.object(deployer, "bootstrap_services")
        )
        ready = self.stack.enter_context(patch.object(deployer, "wait_for_readiness"))
        backup = self.stack.enter_context(patch.object(deployer, "backup_database"))

        with self.assertRaisesRegex(deployer.DeploymentError, "partial stop"):
            deployer._operator_migration_deploy(
                self.config,
                target_sha=NEW_SHA,
                previous_sha=OLD_SHA,
                previous_release=self.old_release,
                release=self.new_release,
                previous_revision="0005_pilot_access",
                target_revision="0006_next",
            )

        bootstrap.assert_called_once_with(self.config)
        ready.assert_called_once_with(self.config, OLD_SHA)
        backup.assert_not_called()

    def test_backup_uses_environment_not_database_command_argument(self):
        observed = []

        def fake_run(command, **kwargs):
            observed.append((command, kwargs))
            if command[0] == "pg_dump":
                output = Path(command[command.index("--file") + 1])
                output.write_bytes(b"valid custom dump")
            return MagicMock(stdout="")

        with patch.object(deployer, "run", side_effect=fake_run):
            backup = deployer.backup_database(
                self.config,
                target_sha=NEW_SHA,
                database_revision_value="0005_pilot_access",
                target_revision="0006_next",
            )

        dump_command, dump_options = observed[0]
        self.assertNotIn("mydictionary", dump_command)
        self.assertEqual(dump_options["env"]["PGDATABASE"], "mydictionary")
        self.assertEqual(self.config.backup_dir.stat().st_mode & 0o777, 0o700)
        self.assertEqual(backup.path.stat().st_mode & 0o777, 0o600)
        self.assertGreater(backup.path.stat().st_size, 0)
        self.assertEqual(len(backup.digest_sha256), 64)


class ReleaseStateTest(OpsTestCase):
    def test_build_release_creates_private_test_data_directory(self):
        target_sha = "c" * 40
        test_runs = []
        archive = io.BytesIO()
        with tarfile.open(fileobj=archive, mode="w") as bundle:
            for filename in (
                "bot.py",
                "tts.py",
                "requirements.txt",
                "requirements.lock",
                "alembic.ini",
            ):
                payload = b""
                member = tarfile.TarInfo(filename)
                member.size = len(payload)
                bundle.addfile(member, io.BytesIO(payload))

        def fake_run(command, *, cwd=None, env=None, text=True, **_kwargs):
            if command[0] == "git":
                return MagicMock(stdout=archive.getvalue())
            if command[1:3] == ["-m", "venv"]:
                release_python = Path(command[-1]) / "bin" / "python3"
                release_python.parent.mkdir(parents=True)
                release_python.write_text("", encoding="utf-8")
                return MagicMock(stdout="")
            if command[1:3] == ["-m", "unittest"]:
                test_data_dir = Path(env["DATA_DIR"])
                test_runs.append(test_data_dir)
                self.assertTrue(test_data_dir.is_dir())
                self.assertEqual(test_data_dir.stat().st_mode & 0o777, 0o700)
                self.assertEqual(
                    env["DATABASE_URL"],
                    f"sqlite:///{test_data_dir / 'candidate-tests.db'}",
                )
                self.assertEqual(cwd, test_data_dir.parent)
            return MagicMock(stdout="")

        with patch.object(deployer, "run", side_effect=fake_run):
            release = deployer.build_release(self.config, target_sha)

        self.assertEqual(release, self.config.releases_dir / target_sha)
        self.assertEqual(len(test_runs), 1)
        self.assertFalse((release / ".test-data").exists())
        self.assertEqual(
            (release / "config.yaml").resolve(), self.config.config_file.resolve()
        )

    def test_release_archive_rejects_path_traversal(self):
        archive = io.BytesIO()
        with tarfile.open(fileobj=archive, mode="w") as bundle:
            member = tarfile.TarInfo("../outside")
            payload = b"unsafe"
            member.size = len(payload)
            bundle.addfile(member, io.BytesIO(payload))

        with self.assertRaisesRegex(deployer.CandidateValidationError, "unsafe path"):
            deployer.safe_extract(archive.getvalue(), self.root / "extract")

    def test_current_target_rejects_release_outside_versioned_tree(self):
        outside = self.root / NEW_SHA
        outside.mkdir()
        self.config.current_link.symlink_to(outside, target_is_directory=True)

        with self.assertRaisesRegex(deployer.DeploymentError, "versioned release"):
            deployer.current_target(self.config)

    def test_database_environment_excludes_runtime_credentials(self):
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
            environment = deployer._database_env(self.config)

        self.assertEqual(environment["DATABASE_URL"], self.config.database_url)
        self.assertNotIn("BOT_TOKEN", environment)
        self.assertNotIn("OPENAI_API_KEY", environment)

    def test_migration_metadata_failure_is_candidate_validation_error(self):
        self.stack.enter_context(
            patch.object(
                deployer, "release_python", return_value=self.config.bootstrap_python
            )
        )
        self.stack.enter_context(
            patch.object(
                deployer,
                "run",
                side_effect=deployer.subprocess.CalledProcessError(1, ["python"]),
            )
        )

        with self.assertRaises(deployer.CandidateValidationError):
            deployer.migration_head(self.new_release)

    def test_failed_release_state_is_private_and_clear_requires_failed_kind(self):
        deployer.record_hold(
            self.config,
            NEW_SHA,
            kind="failed",
            stage="readiness",
            error_type="ReadinessError",
            previous_sha=OLD_SHA,
        )

        self.assertEqual(self.config.holds_file.stat().st_mode & 0o777, 0o600)
        state = json.loads(self.config.holds_file.read_text(encoding="utf-8"))
        self.assertEqual(state["releases"][NEW_SHA]["kind"], "failed")
        self.assertEqual(deployer.clear_failed_quarantine(self.config, NEW_SHA), NEW_SHA)
        self.assertEqual(self.config.lock_file.stat().st_mode & 0o777, 0o600)

        deployer.record_hold(
            self.config,
            NEW_SHA,
            kind="operator_required",
            stage="migration_required",
            error_type="OperatorApprovalRequired",
            previous_sha=OLD_SHA,
        )
        with self.assertRaisesRegex(deployer.DeploymentError, "Only failed"):
            deployer.clear_failed_quarantine(self.config, NEW_SHA)


if __name__ == "__main__":
    unittest.main()
