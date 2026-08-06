from pathlib import Path
import tempfile
import unittest

from ops import mydictionary_monitor as monitor


class MonitorTest(unittest.TestCase):
    def test_alerts_after_threshold_then_deduplicates_and_recovers(self):
        failed = (
            monitor.CheckResult("bot_heartbeat", False, "heartbeat_stale"),
            monitor.CheckResult("admin_health", True, "ready"),
        )
        first = monitor.evaluate(
            failed, monitor.MonitorState(), failure_threshold=2
        )
        second = monitor.evaluate(failed, first.state, failure_threshold=2)
        third = monitor.evaluate(failed, second.state, failure_threshold=2)
        recovered = monitor.evaluate(
            (monitor.CheckResult("all", True, "ready"),),
            third.state,
            failure_threshold=2,
        )

        self.assertIsNone(first.notification)
        self.assertIn("heartbeat_stale", second.notification)
        self.assertIsNone(third.notification)
        self.assertIn("восстановлен", recovered.notification)
        self.assertTrue(recovered.healthy)

    def test_state_round_trip_is_private_and_rejects_symlink(self):
        with tempfile.TemporaryDirectory(prefix="mydictionary-monitor-") as directory:
            root = Path(directory)
            state_path = root / "state.json"
            expected = monitor.MonitorState(2, "abc123")

            monitor.save_state(state_path, expected)

            self.assertEqual(monitor.load_state(state_path), expected)
            self.assertEqual(state_path.stat().st_mode & 0o777, 0o600)
            state_path.unlink()
            target = root / "target.json"
            target.write_text("{}", encoding="utf-8")
            state_path.symlink_to(target)
            with self.assertRaises(monitor.MonitorConfigurationError):
                monitor.save_state(state_path, expected)

    def test_configuration_requires_local_health_and_explicit_alert_secrets(self):
        base = {"MYDICTIONARY_APP_ROOT": "/tmp/mydictionary"}
        with self.assertRaises(monitor.MonitorConfigurationError):
            monitor.Config.from_env(
                {**base, "MYDICTIONARY_HEALTH_URL": "https://example.com/health"}
            )
        with self.assertRaises(monitor.MonitorConfigurationError):
            monitor.Config.from_env(
                {**base, "MYDICTIONARY_MONITOR_ALERTS_ENABLED": "true"}
            )

        config = monitor.Config.from_env(base)

        self.assertFalse(config.alerts_enabled)
        self.assertEqual(config.health_url, "http://127.0.0.1:8791/health")
