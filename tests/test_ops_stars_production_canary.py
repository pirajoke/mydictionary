import importlib.util
import inspect
import json
import os
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from mydictionary.runtime_secrets import RuntimeSecretError


ROOT = Path(__file__).resolve().parents[1]
ENTRYPOINT = ROOT / "ops" / "mydictionary_stars_production_canary.py"
RUNBOOK = ROOT / "docs" / "runbooks" / "telegram-stars-production-canary.md"
OWNER_ID = 7001
CANARY_AMOUNT_XTR = 10
CATALOG_AMOUNT_XTR = 69
PRIVATE_ORDER = "PRIVATE-CANARY-ORDER-ID"
PRIVATE_PAYMENT = "PRIVATE-CANARY-PAYMENT-ID"
PRIVATE_REFUND = "PRIVATE-CANARY-REFUND-ID"
PRIVATE_CHARGE = "PRIVATE-CANARY-CHARGE-ID"
PRIVATE_SECRET = "PRIVATE-CANARY-PAYLOAD-SECRET"
VALID_BOT_TOKEN = "123456789:" + ("A" * 32)
COMPOSE_PREFIX = (
    "docker compose --project-name main-manager-emergency "
    "-f /srv/main-manager/compose.yaml "
    "-f /srv/main-manager/deploy/mydictionary/compose.mydictionary.yaml "
    "--profile production-gated exec -T mydictionary-bot"
)
ADMIN_PROBE_PREFIX = (
    "docker compose --project-name main-manager-emergency "
    "-f /srv/main-manager/compose.yaml "
    "-f /srv/main-manager/deploy/mydictionary/compose.mydictionary.yaml "
    "--profile production-gated exec -T mydictionary-admin"
)


def load_entrypoint(testcase):
    testcase.assertTrue(
        ENTRYPOINT.is_file(),
        "missing reviewed production Stars canary operator entrypoint",
    )
    spec = importlib.util.spec_from_file_location(
        "mydictionary_stars_production_canary",
        ENTRYPOINT,
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def refunded_status():
    return {
        "public_checkout_enabled": False,
        "canary_enabled": False,
        "state": "refunded",
        "product_id": "ai-mini",
        "amount_xtr": CANARY_AMOUNT_XTR,
        "payment_completed": True,
        "refund_pending": False,
        "refund_completed": True,
    }


def private_values():
    return {
        "DATABASE_URL": "sqlite:////private/canary.sqlite3",
        "TELEGRAM_STARS_ENABLED": "false",
        "STARS_PRODUCTION_CANARY_ENABLED": "false",
        "STARS_PRODUCTION_CANARY_OWNER_ID": str(OWNER_ID),
        "BILLING_PAYLOAD_SECRET": PRIVATE_SECRET,
    }


class ProductionStarsCanaryOperatorContractTest(
    unittest.IsolatedAsyncioTestCase
):
    def assert_privacy_safe(self, value):
        rendered = json.dumps(value, ensure_ascii=False, sort_keys=True)
        for forbidden in (
            str(OWNER_ID),
            PRIVATE_ORDER,
            PRIVATE_PAYMENT,
            PRIVATE_REFUND,
            PRIVATE_CHARGE,
            PRIVATE_SECRET,
            "telegram_user_id",
            "charge_id",
            "order_id",
            "payment_id",
            "refund_id",
            "DATABASE_URL",
            "sqlite",
        ):
            self.assertNotIn(forbidden, rendered)

    def test_ac_11_parser_has_only_status_recover_receipt_and_dry_run_writes(self):
        entrypoint = load_entrypoint(self)

        parser = entrypoint.parser()
        subparsers = next(
            action
            for action in parser._actions
            if hasattr(action, "choices") and action.choices
        )
        self.assertEqual(set(subparsers.choices), {"status", "recover", "receipt"})
        recover_parser = subparsers.choices["recover"]
        recover_options = {
            option
            for action in recover_parser._actions
            for option in action.option_strings
        }
        self.assertEqual(recover_options, {"-h", "--help", "--execute"})
        self.assertFalse(parser.parse_args(["recover"]).execute)
        combined_help = parser.format_help() + recover_parser.format_help()
        runbook = RUNBOOK.read_text(encoding="utf-8")
        for forbidden_flag in (
            "--refund-id",
            "--user-id",
            "--owner-id",
            "--order-id",
            "--payment-id",
            "--charge-id",
        ):
            self.assertNotIn(forbidden_flag, combined_help)
            self.assertNotIn(forbidden_flag, runbook)
        with tempfile.TemporaryDirectory(prefix="stars-canary-ops-") as raw:
            output = Path(raw) / "receipt.json"
            self.assertFalse(
                parser.parse_args(["receipt", "--output", str(output)]).execute
            )

    def test_ac_11_status_output_is_fixed_and_privacy_safe(self):
        entrypoint = load_entrypoint(self)
        store = MagicMock()
        settings = SimpleNamespace(enabled=False, public_checkout_enabled=False)
        with (
            patch.object(
                entrypoint.ProductionStarsCanarySettings,
                "from_env",
                return_value=settings,
            ),
            patch.object(
                entrypoint,
                "read_production_stars_canary_status",
                return_value=refunded_status(),
            ) as read_status,
        ):
            result = entrypoint.status_report(store, private_values())

        read_status.assert_called_once_with(
            store=store,
            canary_settings=settings,
        )
        self.assertEqual(result, refunded_status())
        self.assert_privacy_safe(result)

    async def test_ac_11_recover_requires_execute_and_uses_reconciliation_first_service(self):
        entrypoint = load_entrypoint(self)
        service = MagicMock()
        service.recover_current_refund = AsyncMock(return_value=True)
        service.recover_refund = AsyncMock(return_value=True)
        service.process_refund = AsyncMock(return_value=True)
        service.status.return_value = refunded_status()
        gateway = AsyncMock()

        self.assertEqual(
            set(inspect.signature(entrypoint.recover).parameters),
            {"service", "gateway", "execute"},
        )

        with self.assertRaisesRegex(RuntimeError, "--execute"):
            await entrypoint.recover(
                service,
                gateway=gateway,
                execute=False,
            )
        service.recover_current_refund.assert_not_awaited()
        service.recover_refund.assert_not_awaited()
        service.process_refund.assert_not_awaited()

        result = await entrypoint.recover(
            service,
            gateway=gateway,
            execute=True,
        )

        service.recover_current_refund.assert_awaited_once_with(gateway=gateway)
        service.recover_refund.assert_not_awaited()
        service.process_refund.assert_not_awaited()
        self.assertEqual(
            result,
            {"ok": True, "operation": "recover", "state": "refunded"},
        )
        self.assert_privacy_safe(result)

    async def test_ac_11_runtime_recover_passes_no_private_identifier_arguments(self):
        entrypoint = load_entrypoint(self)
        args = entrypoint.parser().parse_args(["recover", "--execute"])
        store = MagicMock()
        service = MagicMock()
        settings = SimpleNamespace(enabled=True, public_checkout_enabled=False)
        runtime = MagicMock()
        runtime.bot_kwargs.return_value = {}
        bot_api = MagicMock()
        gateway = MagicMock()
        safe_recover = AsyncMock(
            return_value={"ok": True, "operation": "recover", "state": "refunded"}
        )
        values = {
            **private_values(),
            "STARS_PRODUCTION_CANARY_ENABLED": "true",
            "BOT_TOKEN": PRIVATE_SECRET,
        }

        with (
            patch.object(entrypoint, "DatabaseStore", return_value=store),
            patch.object(
                entrypoint.ProductionStarsCanarySettings,
                "from_env",
                return_value=settings,
            ),
            patch.object(
                entrypoint.BillingSettings,
                "from_env",
                return_value=MagicMock(),
            ),
            patch.object(
                entrypoint,
                "ProductionStarsCanaryService",
                return_value=service,
            ),
            patch.object(
                entrypoint.TelegramRuntimeSettings,
                "from_env",
                return_value=runtime,
            ),
            patch.object(entrypoint, "Bot", return_value=bot_api),
            patch.object(
                entrypoint,
                "TelegramStarsGateway",
                return_value=gateway,
            ),
            patch.object(entrypoint, "recover", new=safe_recover),
        ):
            try:
                result = await entrypoint.run(args, values)
            except RuntimeError:
                result = None

        self.assertIsNotNone(
            result,
            "runtime must discover the protected recovery target without CLI IDs",
        )

        safe_recover.assert_awaited_once_with(
            service,
            gateway=gateway,
            execute=True,
        )
        private_names = {
            "user_id",
            "owner_id",
            "order_id",
            "payment_id",
            "refund_id",
            "charge_id",
        }
        self.assertTrue(private_names.isdisjoint(safe_recover.await_args.kwargs))
        store.close.assert_called_once_with()
        self.assert_privacy_safe(result)

    def test_ac_11_receipt_requires_execute_is_mode_0600_and_output_is_safe(self):
        entrypoint = load_entrypoint(self)
        now = datetime(2026, 8, 23, 13, 0, tzinfo=timezone.utc)
        with tempfile.TemporaryDirectory(prefix="stars-canary-ops-") as raw:
            root = Path(raw)
            os.chmod(root, 0o700)
            output = root / "receipt.json"
            with self.assertRaisesRegex(RuntimeError, "--execute"):
                entrypoint.write_receipt(
                    refunded_status(),
                    output,
                    execute=False,
                    completed_at=now,
                )
            self.assertFalse(output.exists())

            result = entrypoint.write_receipt(
                refunded_status(),
                output,
                execute=True,
                completed_at=now,
            )

            self.assertTrue(output.is_file())
            self.assertEqual(output.stat().st_mode & 0o777, 0o600)
            receipt = json.loads(output.read_text(encoding="utf-8"))

        self.assertEqual(receipt["environment"], "telegram_production_canary")
        self.assertEqual(receipt["status"], refunded_status())
        self.assertEqual(
            result,
            {"ok": True, "operation": "receipt", "state": "refunded"},
        )
        self.assert_privacy_safe(receipt)
        self.assert_privacy_safe(result)

    async def test_ac_11_recover_loads_protected_bot_token_file_without_exposure(self):
        entrypoint = load_entrypoint(self)
        args = entrypoint.parser().parse_args(["recover", "--execute"])
        store = MagicMock()
        service = MagicMock()
        runtime = MagicMock()
        runtime.bot_kwargs.return_value = {}
        bot_api = MagicMock()
        gateway = MagicMock()
        safe_recover = AsyncMock(
            return_value={"ok": True, "operation": "recover", "state": "refunded"}
        )
        with tempfile.TemporaryDirectory(prefix="stars-canary-token-") as raw:
            token_file = Path(raw) / "bot-token"
            token_file.write_text(f"{VALID_BOT_TOKEN}\n", encoding="ascii")
            os.chmod(token_file, 0o600)
            values = {
                **private_values(),
                "STARS_PRODUCTION_CANARY_ENABLED": "true",
                "BOT_TOKEN": "",
                "BOT_TOKEN_FILE": str(token_file),
            }
            with (
                patch.object(entrypoint, "DatabaseStore", return_value=store),
                patch.object(
                    entrypoint.ProductionStarsCanarySettings,
                    "from_env",
                    return_value=SimpleNamespace(
                        enabled=True,
                        public_checkout_enabled=False,
                    ),
                ),
                patch.object(
                    entrypoint.BillingSettings,
                    "from_env",
                    return_value=MagicMock(),
                ),
                patch.object(
                    entrypoint,
                    "ProductionStarsCanaryService",
                    return_value=service,
                ),
                patch.object(
                    entrypoint.TelegramRuntimeSettings,
                    "from_env",
                    return_value=runtime,
                ),
                patch.object(entrypoint, "Bot", return_value=bot_api) as bot,
                patch.object(
                    entrypoint,
                    "TelegramStarsGateway",
                    return_value=gateway,
                ),
                patch.object(entrypoint, "recover", new=safe_recover),
            ):
                result = await entrypoint.run(args, values)

        bot.assert_called_once_with(token=VALID_BOT_TOKEN)
        safe_recover.assert_awaited_once_with(
            service,
            gateway=gateway,
            execute=True,
        )
        store.close.assert_called_once_with()
        self.assertNotIn(VALID_BOT_TOKEN, json.dumps(result, sort_keys=True))
        self.assert_privacy_safe(result)

    async def test_ac_11_recover_rejects_inline_and_file_token_conflict(self):
        entrypoint = load_entrypoint(self)
        args = entrypoint.parser().parse_args(["recover", "--execute"])
        with tempfile.TemporaryDirectory(prefix="stars-canary-token-") as raw:
            token_file = Path(raw) / "bot-token"
            token_file.write_text(f"{VALID_BOT_TOKEN}\n", encoding="ascii")
            os.chmod(token_file, 0o600)
            values = {
                **private_values(),
                "STARS_PRODUCTION_CANARY_ENABLED": "true",
                "BOT_TOKEN": VALID_BOT_TOKEN,
                "BOT_TOKEN_FILE": str(token_file),
            }
            with patch.object(entrypoint, "DatabaseStore") as database_store:
                with self.assertRaises(RuntimeSecretError):
                    await entrypoint.run(args, values)

        database_store.assert_not_called()

    async def test_ac_11_recover_rejects_unsafe_bot_token_file(self):
        entrypoint = load_entrypoint(self)
        args = entrypoint.parser().parse_args(["recover", "--execute"])
        with tempfile.TemporaryDirectory(prefix="stars-canary-token-") as raw:
            token_file = Path(raw) / "bot-token"
            token_file.write_text(f"{VALID_BOT_TOKEN}\n", encoding="ascii")
            os.chmod(token_file, 0o644)
            values = {
                **private_values(),
                "STARS_PRODUCTION_CANARY_ENABLED": "true",
                "BOT_TOKEN": "",
                "BOT_TOKEN_FILE": str(token_file),
            }
            with patch.object(entrypoint, "DatabaseStore") as database_store:
                with self.assertRaises(RuntimeSecretError):
                    await entrypoint.run(args, values)

        database_store.assert_not_called()

    def test_ac_11_runbook_uses_exact_ovh_bot_container_operator_commands(self):
        runbook = RUNBOOK.read_text(encoding="utf-8")
        self.assertIn(
            f"STARS_PRODUCTION_CANARY_AMOUNT_XTR={CANARY_AMOUNT_XTR}",
            runbook,
        )
        self.assertNotIn(
            f"STARS_PRODUCTION_CANARY_AMOUNT_XTR={CATALOG_AMOUNT_XTR}",
            runbook,
        )
        self.assertIn(f"{CATALOG_AMOUNT_XTR} XTR", runbook)
        self.assertIn("20 credits", runbook)
        expected_commands = (
            f"{COMPOSE_PREFIX} python "
            "ops/mydictionary_stars_production_canary.py status",
            f"{COMPOSE_PREFIX} python "
            "ops/mydictionary_stars_production_canary.py recover --execute",
            f"{COMPOSE_PREFIX} python "
            "ops/mydictionary_stars_production_canary.py receipt "
            "--output /app/state/telegram-stars-production-canary-receipt.json "
            "--execute",
        )
        for command in expected_commands:
            self.assertIn(command, runbook)
        self.assertNotIn(".venv/bin/python", runbook)
        self.assertNotIn("<new-private-receipt-path>", runbook)

    def test_ac_11_runbook_probe_uses_working_database_and_runtime_overrides(self):
        runbook = RUNBOOK.read_text(encoding="utf-8")
        console = runbook.split("## Exact read-only pre/post probe", 1)[1].split(
            "```console", 1
        )[1].split("```", 1)[0]
        commands = [line.strip() for line in console.splitlines() if line.strip()]

        revision = next(
            (line for line in commands if "alembic_version" in line),
            "",
        )
        self.assertTrue(revision.startswith(ADMIN_PROBE_PREFIX))
        self.assertIn("DatabaseStore(", revision)
        self.assertIn("migrate=False", revision)
        self.assertIn("version_num", revision)
        self.assertNotIn("alembic current", console)

        monitor = next(
            (line for line in commands if "ops/mydictionary_monitor.py" in line),
            "",
        )
        backup = next(
            (line for line in commands if "ops/mydictionary_backup.py --check" in line),
            "",
        )
        for command in (monitor, backup):
            self.assertTrue(command.startswith(ADMIN_PROBE_PREFIX))
            self.assertIn("MYDICTIONARY_APP_ROOT=/app/state", command)
            self.assertIn("MYDICTIONARY_PGDUMP_DATABASE=mydictionary", command)
            self.assertIn("MYDICTIONARY_BACKUP_DIR=/app/state/backups", command)
        self.assertIn(
            "MYDICTIONARY_HEALTH_URL=http://127.0.0.1:8787/health",
            monitor,
        )
        self.assertIn(
            "curl --fail --silent --show-error --output /dev/null --write-out "
            "'loopback_health_http=%{http_code}\\n' "
            "http://127.0.0.1:8787/health",
            commands,
        )
        self.assertIn(
            "curl --fail --silent --show-error --output /dev/null --write-out "
            "'public_health_http=%{http_code}\\n' "
            "https://mydictionary.meshly.fr/health",
            commands,
        )
        self.assertNotIn(".venv/bin/python", console)


if __name__ == "__main__":
    unittest.main()
